"""Recommendation engine — match agents to sources and vice versa."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.access import check_clearance, compute_domain_overlap, compute_semantic_match
from backend.models.schemas import Agent, Source


async def recommend_agents_for_source(
    db: AsyncSession,
    source: Source,
) -> list[dict]:
    """
    Given a new source, find which agents would benefit from access.

    Returns a ranked list of agent recommendations.
    """
    agents_result = await db.execute(select(Agent))
    agents = agents_result.scalars().all()

    recommendations = []
    for agent in agents:
        rec = _compute_recommendation(agent, source)
        if rec["relevance_score"] > 0.2:  # Only show somewhat relevant matches
            recommendations.append(rec)

    recommendations.sort(key=lambda r: r["relevance_score"], reverse=True)
    return recommendations


async def recommend_sources_for_agent(
    db: AsyncSession,
    agent: Agent,
) -> list[dict]:
    """
    Given a new agent, find which existing sources are relevant.

    Returns a ranked list of source recommendations.
    """
    sources_result = await db.execute(select(Source))
    sources = sources_result.scalars().all()

    recommendations = []
    for source in sources:
        rec = _compute_recommendation(agent, source)
        if rec["relevance_score"] > 0.2:
            recommendations.append(rec)

    recommendations.sort(key=lambda r: r["relevance_score"], reverse=True)
    return recommendations


def _compute_recommendation(agent: Agent, source: Source) -> dict:
    """Compute a recommendation score between an agent and source."""
    # Semantic match
    if agent.purpose_embedding is not None and source.summary_embedding is not None:
        semantic_match = compute_semantic_match(
            list(agent.purpose_embedding),
            list(source.summary_embedding),
        )
    else:
        semantic_match = 0.0

    # Domain overlap
    domain_overlap = compute_domain_overlap(
        agent.domains or [],
        source.domains or [],
    )

    # Clearance check
    clearance_ok = check_clearance(
        agent.clearance or "internal",
        source.classification or "internal",
    )

    # Combined relevance
    relevance_score = (semantic_match * 0.7) + (domain_overlap * 0.3)

    # Determine status
    if not clearance_ok:
        status = "needs_clearance_upgrade"
        note = f"Relevant but agent clearance ({agent.clearance}) < source classification ({source.classification})"
    elif relevance_score >= 0.75:
        status = "strong_match"
        note = "High relevance — recommended for auto-grant"
    elif relevance_score >= 0.5:
        status = "moderate_match"
        note = "Moderate relevance — review recommended"
    elif relevance_score >= 0.2:
        status = "weak_match"
        note = "Low relevance — may not be useful"
    else:
        status = "no_match"
        note = "Not relevant"

    return {
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "agent_purpose": agent.purpose,
        "source_id": str(source.id),
        "source_name": source.name,
        "source_summary": source.summary,
        "relevance_score": round(relevance_score, 4),
        "semantic_match": round(semantic_match, 4),
        "domain_overlap": round(domain_overlap, 4),
        "clearance_ok": clearance_ok,
        "status": status,
        "note": note,
    }
