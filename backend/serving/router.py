"""Query Router — multi-hypothesis L3 search with access filter and token trim.

Flow: query → process_query (k hypotheses + canonical) → pgvector per hypothesis
      → RRF fusion → heuristic re-score → optional LLM re-rank → token trim → log.
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
    1. process_query → k hypotheses + canonical (if smart_search=True)
    2. pgvector search per hypothesis with optional canonical pre-filter
    3. RRF fusion + confidence × freshness re-scoring
    4. Optional LLM re-ranking (deep_rerank=True adds ~1–3s latency)
    5. Token budget trim
    6. Access log

    Returns:
        {"atoms": [...], "cache_tier": str, "latency_ms": float,
         "atoms_served": int, "atoms_filtered": int, "total_tokens": int}
    """
    hypotheses = [query]
    query_canonical: dict | None = None

    if smart_search:
        processed = await process_query(query)
        hypotheses = processed.hypotheses
        query_canonical = processed.canonical

    return await _query_context_core(
        db, query, hypotheses, agent, top_k, query_canonical, deep_rerank
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
) -> dict:
    """Inner search + trim + log. Separated so compare_context shares one process_query call."""
    start = time.monotonic()
    agent_domains = agent.domains or []
    role_mask = agent.role_mask or 0
    max_tokens = agent.max_tokens or 4000
    domain_filter = list(set(agent_domains)) if agent_domains else None

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
        top_k=top_k * 2,
        domain_filter=domain_filter,
        min_relevance=0.3,
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
