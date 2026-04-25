"""Frame Matcher — match agents to relevant frames.

Evolved from engine/recommendations.py. Uses domain overlap and role_mask
compatibility to find frames an agent would benefit from.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import AgentProfile, Frame


async def match_frames_for_agent(
    db: AsyncSession,
    agent: AgentProfile,
    limit: int = 10,
) -> list[dict]:
    """Find frames relevant to an agent based on domain overlap and role mask.

    Returns ranked list of frame matches.
    """
    result = await db.execute(select(Frame).order_by(Frame.access_count.desc()))
    frames = result.scalars().all()

    matches: list[dict] = []
    agent_domains = set(agent.domains or [])

    for frame in frames:
        # Access check: agent must have at least one matching bit
        if not (agent.role_mask & frame.access_mask):
            continue

        # Domain relevance
        domain_match = 1.0 if frame.domain in agent_domains else 0.0
        if frame.domain == "general":
            domain_match = 0.3  # General frames are weakly relevant

        # Popularity bonus
        popularity = min(frame.access_count / 100.0, 1.0) if frame.access_count else 0.0

        relevance = (domain_match * 0.7) + (popularity * 0.3)

        if relevance > 0.1:
            matches.append({
                "frame_id": str(frame.id),
                "frame_name": frame.name,
                "domain": frame.domain,
                "atom_count": len(frame.atom_ids) if frame.atom_ids else 0,
                "token_count": frame.token_count,
                "relevance_score": round(relevance, 4),
                "access_ok": True,
            })

    matches.sort(key=lambda m: m["relevance_score"], reverse=True)
    return matches[:limit]
