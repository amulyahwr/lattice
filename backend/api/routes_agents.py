"""Agent management routes — create agents with identity profiles and manage access."""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text
from backend.engine.recommendations import recommend_sources_for_agent
from backend.models.database import get_db
from backend.models.schemas import Agent, AgentPermission, Source

router = APIRouter(prefix="/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    name: str
    purpose: str = Field(..., description="What this agent does — its reason for existing")
    deployed_by: str | None = None
    clearance: str = Field(default="internal", description="Max classification: public|internal|confidential|restricted")
    domains: list[str] = Field(default_factory=list, description="Domain tags this agent operates in")
    org_scope: list[str] = Field(default_factory=list, description="Organizational units this agent belongs to")


class AgentResponse(BaseModel):
    id: str
    name: str
    api_key: str
    purpose: str | None = None
    deployed_by: str | None = None
    clearance: str | None = None
    domains: list[str] = []
    org_scope: list[str] = []
    source_ids: list[str] = []


class RecommendationResponse(BaseModel):
    agent_id: str
    agent_name: str
    agent_purpose: str | None
    source_id: str
    source_name: str
    source_summary: str | None
    relevance_score: float
    semantic_match: float
    domain_overlap: float
    clearance_ok: bool
    status: str
    note: str


class GrantAccessRequest(BaseModel):
    source_id: str


class AgentUpdateRequest(BaseModel):
    purpose: str | None = None
    deployed_by: str | None = None
    clearance: str | None = None
    domains: list[str] | None = None
    org_scope: list[str] | None = None


@router.post("/", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent with an identity profile."""
    api_key = f"lat_{secrets.token_urlsafe(32)}"

    # Embed the purpose for semantic matching
    purpose_embedding = embed_text(request.purpose) if request.purpose else None

    agent = Agent(
        id=uuid.uuid4(),
        name=request.name,
        api_key=api_key,
        purpose=request.purpose,
        purpose_embedding=purpose_embedding,
        deployed_by=request.deployed_by,
        clearance=request.clearance,
        domains=request.domains,
        org_scope=request.org_scope,
    )
    db.add(agent)
    await db.commit()

    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        api_key=agent.api_key,
        purpose=agent.purpose,
        deployed_by=agent.deployed_by,
        clearance=agent.clearance,
        domains=agent.domains or [],
        org_scope=agent.org_scope or [],
        source_ids=[],
    )


@router.get("/", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all agents with their identity profiles."""
    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    responses = []
    for agent in agents:
        perm_result = await db.execute(
            select(AgentPermission.source_id).where(
                AgentPermission.agent_id == agent.id,
                AgentPermission.permission_type == "grant",
            )
        )
        source_ids = [str(row[0]) for row in perm_result.fetchall()]

        responses.append(
            AgentResponse(
                id=str(agent.id),
                name=agent.name,
                api_key=agent.api_key,
                purpose=agent.purpose,
                deployed_by=agent.deployed_by,
                clearance=agent.clearance,
                domains=agent.domains or [],
                org_scope=agent.org_scope or [],
                source_ids=source_ids,
            )
        )

    return responses


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    update: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's identity profile."""
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if update.purpose is not None:
        agent.purpose = update.purpose
        agent.purpose_embedding = embed_text(update.purpose)
    if update.deployed_by is not None:
        agent.deployed_by = update.deployed_by
    if update.clearance is not None:
        agent.clearance = update.clearance
    if update.domains is not None:
        agent.domains = update.domains
    if update.org_scope is not None:
        agent.org_scope = update.org_scope

    await db.commit()

    perm_result = await db.execute(
        select(AgentPermission.source_id).where(
            AgentPermission.agent_id == agent.id,
            AgentPermission.permission_type == "grant",
        )
    )
    source_ids = [str(row[0]) for row in perm_result.fetchall()]

    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        api_key=agent.api_key,
        purpose=agent.purpose,
        deployed_by=agent.deployed_by,
        clearance=agent.clearance,
        domains=agent.domains or [],
        org_scope=agent.org_scope or [],
        source_ids=source_ids,
    )


@router.get("/{agent_id}/recommendations", response_model=list[RecommendationResponse])
async def get_agent_recommendations(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get source recommendations for an agent — which sources are relevant?"""
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    recommendations = await recommend_sources_for_agent(db, agent)
    return [RecommendationResponse(**r) for r in recommendations]


@router.post("/{agent_id}/grant")
async def grant_access(
    agent_id: str,
    request: GrantAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually grant an agent access to a source (override)."""
    agent_result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    source_result = await db.execute(select(Source).where(Source.id == uuid.UUID(request.source_id)))
    if not source_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    # Check for existing permission
    existing = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == uuid.UUID(agent_id),
            AgentPermission.source_id == uuid.UUID(request.source_id),
        )
    )
    perm = existing.scalar_one_or_none()

    if perm:
        perm.permission_type = "grant"
    else:
        perm = AgentPermission(
            id=uuid.uuid4(),
            agent_id=uuid.UUID(agent_id),
            source_id=uuid.UUID(request.source_id),
            permission_type="grant",
        )
        db.add(perm)

    await db.commit()
    return {"status": "granted", "agent_id": agent_id, "source_id": request.source_id}


@router.post("/{agent_id}/deny")
async def deny_access(
    agent_id: str,
    request: GrantAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """Manually deny an agent access to a source (override — even if computed access would allow it)."""
    agent_result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    source_result = await db.execute(select(Source).where(Source.id == uuid.UUID(request.source_id)))
    if not source_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    existing = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == uuid.UUID(agent_id),
            AgentPermission.source_id == uuid.UUID(request.source_id),
        )
    )
    perm = existing.scalar_one_or_none()

    if perm:
        perm.permission_type = "deny"
    else:
        perm = AgentPermission(
            id=uuid.uuid4(),
            agent_id=uuid.UUID(agent_id),
            source_id=uuid.UUID(request.source_id),
            permission_type="deny",
        )
        db.add(perm)

    await db.commit()
    return {"status": "denied", "agent_id": agent_id, "source_id": request.source_id}


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent and all its permissions."""
    result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)
    await db.commit()
    return {"status": "deleted", "agent_id": agent_id}


@router.delete("/{agent_id}/revoke/{source_id}")
async def revoke_override(
    agent_id: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove a manual override — revert to computed access."""
    result = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == uuid.UUID(agent_id),
            AgentPermission.source_id == uuid.UUID(source_id),
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="No override found")

    await db.delete(perm)
    await db.commit()
    return {"status": "reverted_to_computed", "agent_id": agent_id, "source_id": source_id}
