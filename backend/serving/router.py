"""Query Router — L2 check → L3 fallback → access filter → token trim.

The serving hot path. Routes queries through the cache tiers and applies
access control via bitmask AND operations.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import AccessLog, AgentProfile, Frame
from backend.serving.frame_builder import count_tokens
from backend.serving.l2_cache import l2_cache
from backend.serving.l3_search import search_atoms


async def query_context(
    db: AsyncSession,
    query: str,
    agent: AgentProfile,
    top_k: int = 10,
) -> dict:
    """Route a context query through the cache tiers.

    Flow:
    1. Check L2 frame cache (domain match + role_mask)
    2. Fall through to L3 pgvector search
    3. Filter atoms by access_mask
    4. Trim to agent's max_tokens budget
    5. Log access

    Returns:
        {
            "atoms": [...],
            "cache_tier": "L2" | "L3",
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

    # ── L2: Frame Cache ──
    for domain in agent_domains:
        cached = l2_cache.get_by_domain(domain, role_mask)
        if cached:
            # Filter individual atoms by access_mask
            atoms = []
            filtered = 0
            token_budget = max_tokens

            for i, (content, mask) in enumerate(
                zip(cached.atom_contents, cached.atom_access_masks)
            ):
                if mask & role_mask:
                    atom_tokens = count_tokens(content)
                    if token_budget - atom_tokens >= 0:
                        atoms.append({
                            "atom_id": str(cached.atom_ids[i]),
                            "content": content,
                            "access_mask": mask,
                        })
                        token_budget -= atom_tokens
                else:
                    filtered += 1

            # Update frame access stats
            await _update_frame_access(db, cached.frame_id)

            latency = (time.monotonic() - start) * 1000
            total_tokens = max_tokens - token_budget

            await _log_access(
                db, agent, query, "granted", len(atoms), filtered, "L2", latency
            )

            return {
                "atoms": atoms,
                "cache_tier": "L2",
                "latency_ms": round(latency, 2),
                "atoms_served": len(atoms),
                "atoms_filtered": filtered,
                "total_tokens": total_tokens,
            }

    # ── L3: pgvector Search ──
    raw_results = await search_atoms(
        db=db, query=query, role_mask=role_mask, top_k=top_k * 2  # Fetch extra for token trimming
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
    await _log_access(
        db, agent, query, "granted", len(atoms), filtered, "L3", latency
    )

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


async def _update_frame_access(db: AsyncSession, frame_id) -> None:
    """Update frame access stats on cache hit."""
    from sqlalchemy import select

    result = await db.execute(select(Frame).where(Frame.id == frame_id))
    frame = result.scalar_one_or_none()
    if frame:
        frame.access_count = (frame.access_count or 0) + 1
        frame.last_accessed = datetime.now(timezone.utc)


async def _log_access(
    db: AsyncSession,
    agent: AgentProfile,
    query: str,
    decision: str,
    atoms_served: int,
    atoms_filtered: int,
    cache_tier: str,
    latency_ms: float,
) -> None:
    """Log an access event for audit."""
    log = AccessLog(
        agent_id=agent.id,
        query=query,
        decision=decision,
        atoms_served=atoms_served,
        atoms_filtered=atoms_filtered,
        cache_tier=cache_tier,
        latency_ms=round(latency_ms, 2),
    )
    db.add(log)
