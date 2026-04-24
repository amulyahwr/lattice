"""Access resolution — the trust broker.

Computes whether an agent SHOULD and CAN access a source,
using semantic matching + clearance + domain overlap.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text
from backend.models.schemas import AccessLog, Agent, AgentPermission, Source

# Classification hierarchy — higher index = more restricted
CLASSIFICATION_LEVELS = {
    "public": 0,
    "internal": 1,
    "confidential": 2,
    "restricted": 3,
}


def check_clearance(agent_clearance: str, source_classification: str) -> bool:
    """Can the agent's clearance level access this source's classification?"""
    agent_level = CLASSIFICATION_LEVELS.get(agent_clearance, 0)
    source_level = CLASSIFICATION_LEVELS.get(source_classification, 0)
    return agent_level >= source_level


def compute_domain_overlap(agent_domains: list[str], source_domains: list[str]) -> float:
    """Compute domain overlap score (0.0 to 1.0)."""
    if not agent_domains or not source_domains:
        return 0.0
    agent_set = set(agent_domains)
    source_set = set(source_domains)
    overlap = agent_set & source_set
    # Jaccard-like but weighted toward source coverage
    if not source_set:
        return 0.0
    return len(overlap) / len(source_set)


def compute_semantic_match(
    purpose_embedding: list[float],
    summary_embedding: list[float],
) -> float:
    """Compute cosine similarity between agent purpose and source summary."""
    if not purpose_embedding or not summary_embedding:
        return 0.0

    dot = sum(a * b for a, b in zip(purpose_embedding, summary_embedding))
    norm_a = sum(a * a for a in purpose_embedding) ** 0.5
    norm_b = sum(b * b for b in summary_embedding) ** 0.5

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)


async def resolve_access(
    db: AsyncSession,
    agent: Agent,
    source: Source,
) -> dict:
    """
    Resolve whether an agent can access a source.

    Returns:
        {
            "granted": bool,
            "reason": str,
            "relevance_score": float,
            "clearance_ok": bool,
            "domain_overlap": float,
            "semantic_match": float,
            "override": str | None  # "manual_grant" | "manual_deny" | None
        }
    """
    # Step 0: Check manual overrides first
    override_result = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent.id,
            AgentPermission.source_id == source.id,
        )
    )
    override = override_result.scalar_one_or_none()

    if override:
        if override.permission_type == "deny":
            return {
                "granted": False,
                "reason": "Manually denied by admin",
                "relevance_score": 0.0,
                "clearance_ok": True,
                "domain_overlap": 0.0,
                "semantic_match": 0.0,
                "override": "manual_deny",
            }
        elif override.permission_type == "grant":
            return {
                "granted": True,
                "reason": "Manually granted by admin",
                "relevance_score": 1.0,
                "clearance_ok": True,
                "domain_overlap": 1.0,
                "semantic_match": 1.0,
                "override": "manual_grant",
            }

    # Step 1: Clearance check — CAN the agent see this?
    clearance_ok = check_clearance(
        agent.clearance or "internal",
        source.classification or "internal",
    )

    # Step 2: Domain overlap
    domain_overlap = compute_domain_overlap(
        agent.domains or [],
        source.domains or [],
    )

    # Step 3: Semantic match — SHOULD the agent see this?
    agent_purpose_emb = agent.purpose_embedding
    source_summary_emb = source.summary_embedding

    if agent_purpose_emb is not None and source_summary_emb is not None:
        semantic_match = compute_semantic_match(
            list(agent_purpose_emb),
            list(source_summary_emb),
        )
    else:
        semantic_match = 0.0

    # Step 4: Compute combined relevance
    # Weighted: semantic match is primary, domain overlap is secondary
    relevance_score = (semantic_match * 0.7) + (domain_overlap * 0.3)

    # Step 5: Decision
    if not clearance_ok:
        granted = False
        reason = f"Insufficient clearance: agent={agent.clearance}, source={source.classification}"
    elif relevance_score < 0.3:
        granted = False
        reason = f"Low relevance ({relevance_score:.2f}) — source not relevant to agent purpose"
    else:
        granted = True
        reason = f"Access computed: relevance={relevance_score:.2f}, clearance OK"

    return {
        "granted": granted,
        "reason": reason,
        "relevance_score": round(relevance_score, 4),
        "clearance_ok": clearance_ok,
        "domain_overlap": round(domain_overlap, 4),
        "semantic_match": round(semantic_match, 4),
        "override": None,
    }


async def get_accessible_source_ids(
    db: AsyncSession,
    agent: Agent,
) -> list[UUID]:
    """Get all source IDs this agent can access via computed resolution."""
    sources_result = await db.execute(select(Source))
    sources = sources_result.scalars().all()

    accessible = []
    for source in sources:
        result = await resolve_access(db, agent, source)
        if result["granted"]:
            accessible.append(source.id)

    return accessible


async def log_access(
    db: AsyncSession,
    agent_id: UUID,
    source_id: UUID,
    query: str | None,
    decision: str,
    reason: str,
    relevance_score: float | None = None,
):
    """Log an access decision for audit."""
    log = AccessLog(
        agent_id=agent_id,
        source_id=source_id,
        query=query,
        decision=decision,
        reason=reason,
        relevance_score=relevance_score,
    )
    db.add(log)
