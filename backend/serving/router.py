"""Query Router — L3 pgvector search with access filter and token trim.

Simplified serving path: query → embed → pgvector search → bitmask filter → token budget trim.
"""

from __future__ import annotations

import time

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

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
) -> dict:
    """Route a context query through L3 search with access control.

    Flow:
    1. L3 pgvector search with bitmask pre-filter
    2. Trim to agent's max_tokens budget
    3. Log access

    Returns:
        {
            "atoms": [...],
            "cache_tier": str,
            "latency_ms": float,
            "atoms_served": int,
            "atoms_filtered": int,
            "total_tokens": int,
        }
    """
    start = time.monotonic()
    agent_domains = agent.domains or []
    role_mask = agent.role_mask or 0
    max_tokens = agent.max_tokens or 4000

    # ── Pre-flight: skip expensive search if agent has no accessible atoms ──
    domain_filter = list(set(agent_domains)) if agent_domains else None

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

    # ── L3: pgvector Search ──
    raw_results = await search_atoms(
        db=db,
        query=query,
        role_mask=role_mask,
        top_k=top_k * 2,  # fetch extra for token trimming
        domain_filter=domain_filter,
        min_relevance=0.3,
    )

    # Trim to token budget
    atoms = []
    filtered = 0
    token_budget = max_tokens

    for result in raw_results:
        atom_tokens = count_tokens(result["content"])
        if token_budget - atom_tokens >= 0:
            atoms.append(result)
            token_budget -= atom_tokens
        else:
            # Over budget — stop adding
            break

    latency = (time.monotonic() - start) * 1000
    total_tokens = max_tokens - token_budget

    # Count filtered (atoms that existed but agent couldn't see — already filtered in L3)
    await _log_access(db, agent, query, "granted", len(atoms), filtered, latency)

    return {
        "atoms": atoms,
        "cache_tier": "L3",
        "latency_ms": round(latency, 2),
        "atoms_served": len(atoms),
        "atoms_filtered": filtered,
        "total_tokens": total_tokens,
    }


async def compare_context(
    db: AsyncSession,
    query: str,
    agents: list[AgentProfile],
    top_k: int = 10,
) -> list[dict]:
    """Run the same query for multiple agents, showing how context differs.

    Returns a list of results, one per agent.
    """
    results = []
    for agent in agents:
        result = await query_context(db, query, agent, top_k)
        result["agent_id"] = str(agent.id)
        result["agent_name"] = agent.name
        result["role_mask"] = agent.role_mask
        results.append(result)
    return results


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
        cache_tier="L3",  # Always L3 in simplified architecture
        latency_ms=round(latency_ms, 2),
    )
    db.add(log)
