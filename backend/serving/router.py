"""Query Router — multi-hypothesis L3 search with access filter and token trim.

Flow: query → process_query (kinds + k hypotheses + canonical)
      → intent-adaptive routing (adjusts deep_rerank, search_top_k, min_relevance)
      → pgvector per hypothesis + BM25 → RRF fusion → heuristic re-score
      → optional LLM re-rank → token trim → log.
"""

from __future__ import annotations

import time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.query_processor import process_query
from backend.models.atoms import AccessLog, AgentProfile, Atom
from backend.serving.l3_search import search_atoms


def count_tokens(text: str) -> int:
    """Estimate token count (rough approximation: 1 token ≈ 4 chars)."""
    return len(text) // 4


# ── Intent-adaptive routing ───────────────────────────────────────────────────

# Per-kind defaults. Mixed-intent queries merge these configs:
#   deep_rerank  — auto-enable for precision-critical kinds
#   top_k_factor — multiplier on the caller's top_k for the search candidate pool
#   min_relevance — relevance floor passed to search_atoms
#   strip_period  — True for timeless kinds (procedure, fact) so the period filter
#                   doesn't exclude valid atoms
_INTENT_CONFIG: dict[str, dict] = {
    "metric":    {"deep_rerank": True,  "top_k_factor": 2, "min_relevance": 0.35, "strip_period": False},
    "event":     {"deep_rerank": False, "top_k_factor": 3, "min_relevance": 0.25, "strip_period": False},
    "decision":  {"deep_rerank": True,  "top_k_factor": 2, "min_relevance": 0.30, "strip_period": False},
    "procedure": {"deep_rerank": False, "top_k_factor": 2, "min_relevance": 0.28, "strip_period": True},
    "fact":      {"deep_rerank": False, "top_k_factor": 2, "min_relevance": 0.28, "strip_period": True},
}


def _apply_intent_routing(
    kinds: list[str],
    query_canonical: dict | None,
    caller_deep_rerank: bool,
    top_k: int,
) -> tuple[dict | None, bool, int, float]:
    """Resolve search configuration from query intent kinds.

    Returns (query_canonical, deep_rerank, search_top_k, min_relevance).
    Caller's deep_rerank is never downgraded — only upgraded.
    For mixed intents, takes the most permissive recall params and highest precision floor.
    """
    configs = [_INTENT_CONFIG[k] for k in kinds if k in _INTENT_CONFIG]
    if not configs:
        return query_canonical, caller_deep_rerank, top_k * 2, 0.3

    auto_rerank    = any(c["deep_rerank"]   for c in configs)
    top_k_factor   = max(c["top_k_factor"]  for c in configs)
    min_relevance  = min(c["min_relevance"] for c in configs)  # most permissive floor
    strip_period   = all(c["strip_period"]  for c in configs)  # only strip when ALL kinds are timeless

    resolved_canonical = query_canonical
    if strip_period and resolved_canonical:
        stripped = {k: v for k, v in resolved_canonical.items() if k != "period"}
        resolved_canonical = stripped or None

    return (
        resolved_canonical,
        caller_deep_rerank or auto_rerank,
        top_k * top_k_factor,
        min_relevance,
    )


async def query_context(
    db: AsyncSession,
    query: str,
    agent: AgentProfile,
    top_k: int = 10,
    smart_search: bool = True,
    deep_rerank: bool = False,
) -> dict:
    """Route a context query through multi-hypothesis L3 search with access control.

    Flow:
    1. process_query → kinds + k hypotheses + canonical (if smart_search=True)
    2. Intent-adaptive routing — adjusts deep_rerank, search_top_k, min_relevance from kinds
    3. pgvector per hypothesis + BM25 with optional canonical period pre-filter
    4. RRF fusion + confidence × freshness re-scoring
    5. Optional LLM re-ranking (deep_rerank=True adds ~1–3s latency)
    6. Token budget trim
    7. Access log

    Returns:
        {"atoms": [...], "cache_tier": str, "latency_ms": float,
         "atoms_served": int, "atoms_filtered": int, "total_tokens": int}
    """
    hypotheses = [query]
    query_canonical: dict | None = None
    search_top_k = top_k * 2
    min_relevance = 0.3

    if smart_search:
        processed = await process_query(query)
        hypotheses = processed.hypotheses
        query_canonical, deep_rerank, search_top_k, min_relevance = _apply_intent_routing(
            processed.kinds, processed.canonical, deep_rerank, top_k
        )

    return await _query_context_core(
        db, query, hypotheses, agent, top_k, query_canonical, deep_rerank,
        search_top_k=search_top_k, min_relevance=min_relevance,
    )


async def compare_context(
    db: AsyncSession,
    query: str,
    agents: list[AgentProfile],
    top_k: int = 10,
) -> list[dict]:
    """Run the same query for multiple agents, showing how context differs.

    Calls process_query once and reuses hypotheses across all agents.
    """
    processed = await process_query(query)

    results = []
    for agent in agents:
        result = await _query_context_core(
            db, query, processed.hypotheses, agent, top_k, processed.canonical, False
        )
        result["agent_id"] = str(agent.id)
        result["agent_name"] = agent.name
        result["role_mask"] = agent.role_mask
        results.append(result)
    return results


async def _query_context_core(
    db: AsyncSession,
    query: str,
    hypotheses: list[str],
    agent: AgentProfile,
    top_k: int,
    query_canonical: dict | None,
    deep_rerank: bool,
    search_top_k: int | None = None,
    min_relevance: float = 0.3,
) -> dict:
    """Inner search + trim + log. Separated so compare_context shares one process_query call."""
    start = time.monotonic()
    agent_domains = agent.domains or []
    role_mask = agent.role_mask or 0
    max_tokens = agent.max_tokens or 4000
    domain_filter = list(set(agent_domains)) if agent_domains else None
    resolved_search_top_k = search_top_k if search_top_k is not None else top_k * 2

    # ── Pre-flight: skip if agent has no accessible atoms ────────────────────
    preflight_stmt = (
        select(func.count())
        .select_from(Atom)
        .where(Atom.access_mask.bitwise_and(role_mask) != 0)
    )
    if domain_filter:
        preflight_stmt = preflight_stmt.where(Atom.domain.overlap(domain_filter))

    has_accessible = (await db.execute(preflight_stmt.limit(1))).scalar()

    if not has_accessible:
        latency = (time.monotonic() - start) * 1000
        await _log_access(db, agent, query, "granted", 0, 0, latency)
        return {
            "atoms": [],
            "cache_tier": "L3",
            "latency_ms": round(latency, 2),
            "atoms_served": 0,
            "atoms_filtered": 0,
            "total_tokens": 0,
        }

    # ── Multi-hypothesis search + RRF + re-ranking ───────────────────────────
    raw_results = await search_atoms(
        db=db,
        hypotheses=hypotheses,
        role_mask=role_mask,
        top_k=resolved_search_top_k,
        domain_filter=domain_filter,
        min_relevance=min_relevance,
        query_canonical=query_canonical,
        deep_rerank=deep_rerank,
        raw_query=query,
    )

    # ── Token budget trim ─────────────────────────────────────────────────────
    atoms: list[dict] = []
    token_budget = max_tokens

    for result in raw_results:
        atom_tokens = count_tokens(result["content"])
        if token_budget - atom_tokens >= 0:
            atoms.append(result)
            token_budget -= atom_tokens
        else:
            break

    latency = (time.monotonic() - start) * 1000
    total_tokens = max_tokens - token_budget

    await _log_access(db, agent, query, "granted", len(atoms), 0, latency)

    return {
        "atoms": atoms,
        "cache_tier": "L3",
        "latency_ms": round(latency, 2),
        "atoms_served": len(atoms),
        "atoms_filtered": 0,
        "total_tokens": total_tokens,
    }


async def _log_access(
    db: AsyncSession,
    agent: AgentProfile,
    query: str,
    decision: str,
    atoms_served: int,
    atoms_filtered: int,
    latency_ms: float,
) -> None:
    """Log an access event for audit."""
    log = AccessLog(
        agent_id=agent.id,
        query=query,
        decision=decision,
        atoms_served=atoms_served,
        atoms_filtered=atoms_filtered,
        cache_tier="L3",
        latency_ms=round(latency_ms, 2),
    )
    db.add(log)
