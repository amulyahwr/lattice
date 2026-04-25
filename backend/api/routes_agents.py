"""Agent management routes — create, list, update agents with role masks.

Evolved from old routes_agents.py. Drops grant/deny/revoke (bitmask replaces
per-source permissions). Adds role_mask and max_tokens to agent profile.
"""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import AccessLog, AgentProfile
from backend.models.database import get_db

router = APIRouter(prefix="/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    name: str
    purpose: str = Field(default="", description="What this agent does")
    domains: list[str] = Field(default_factory=list, description="Domain tags")
    role_mask: int = Field(default=0, description="64-bit access bitmask")
    max_tokens: int = Field(default=4000, description="Token budget per query")
    freshness_req: str = Field(default="24h", description="Freshness requirement")


class AgentResponse(BaseModel):
    id: str
    name: str
    api_key: str
    purpose: str | None = None
    domains: list[str] = []
    role_mask: int = 0
    max_tokens: int = 4000
    freshness_req: str = "24h"
    created_at: str | None = None


class AgentUpdateRequest(BaseModel):
    purpose: str | None = None
    domains: list[str] | None = None
    role_mask: int | None = None
    max_tokens: int | None = None
    freshness_req: str | None = None


class AgentStatsResponse(BaseModel):
    agent_id: str
    agent_name: str
    total_queries: int = 0
    avg_latency_ms: float = 0.0
    total_atoms_served: int = 0
    total_atoms_filtered: int = 0
    cache_hit_rate: float = 0.0  # L2 hits / total queries


@router.post("/", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent with profile and role mask."""
    api_key = f"lat_{secrets.token_urlsafe(32)}"

    agent = AgentProfile(
        id=uuid.uuid4(),
        name=request.name,
        api_key=api_key,
        purpose=request.purpose,
        domains=request.domains,
        role_mask=request.role_mask,
        max_tokens=request.max_tokens,
        freshness_req=request.freshness_req,
    )
    db.add(agent)
    await db.commit()

    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        api_key=agent.api_key,
        purpose=agent.purpose,
        domains=agent.domains or [],
        role_mask=agent.role_mask or 0,
        max_tokens=agent.max_tokens or 4000,
        freshness_req=agent.freshness_req or "24h",
        created_at=agent.created_at.isoformat() if agent.created_at else None,
    )


@router.get("/", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all agents with their profiles."""
    result = await db.execute(select(AgentProfile).order_by(AgentProfile.created_at.desc()))
    agents = result.scalars().all()

    return [
        AgentResponse(
            id=str(a.id),
            name=a.name,
            api_key=a.api_key,
            purpose=a.purpose,
            domains=a.domains or [],
            role_mask=a.role_mask or 0,
            max_tokens=a.max_tokens or 4000,
            freshness_req=a.freshness_req or "24h",
            created_at=a.created_at.isoformat() if a.created_at else None,
        )
        for a in agents
    ]


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    update: AgentUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update an agent's profile."""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == uuid.UUID(agent_id))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if update.purpose is not None:
        agent.purpose = update.purpose
    if update.domains is not None:
        agent.domains = update.domains
    if update.role_mask is not None:
        agent.role_mask = update.role_mask
    if update.max_tokens is not None:
        agent.max_tokens = update.max_tokens
    if update.freshness_req is not None:
        agent.freshness_req = update.freshness_req

    await db.commit()

    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        api_key=agent.api_key,
        purpose=agent.purpose,
        domains=agent.domains or [],
        role_mask=agent.role_mask or 0,
        max_tokens=agent.max_tokens or 4000,
        freshness_req=agent.freshness_req or "24h",
        created_at=agent.created_at.isoformat() if agent.created_at else None,
    )


@router.get("/{agent_id}/stats", response_model=AgentStatsResponse)
async def get_agent_stats(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get per-agent performance stats."""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == uuid.UUID(agent_id))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Query access logs for stats
    logs_result = await db.execute(
        select(
            func.count(AccessLog.id).label("total_queries"),
            func.avg(AccessLog.latency_ms).label("avg_latency"),
            func.sum(AccessLog.atoms_served).label("total_served"),
            func.sum(AccessLog.atoms_filtered).label("total_filtered"),
        ).where(AccessLog.agent_id == agent.id)
    )
    row = logs_result.fetchone()

    total_queries = row.total_queries or 0
    avg_latency = float(row.avg_latency or 0)
    total_served = row.total_served or 0
    total_filtered = row.total_filtered or 0

    # Cache hit rate (L2 hits / total)
    l2_result = await db.execute(
        select(func.count(AccessLog.id)).where(
            AccessLog.agent_id == agent.id,
            AccessLog.cache_tier == "L2",
        )
    )
    l2_hits = l2_result.scalar() or 0
    cache_hit_rate = l2_hits / total_queries if total_queries > 0 else 0.0

    return AgentStatsResponse(
        agent_id=str(agent.id),
        agent_name=agent.name,
        total_queries=total_queries,
        avg_latency_ms=round(avg_latency, 2),
        total_atoms_served=total_served,
        total_atoms_filtered=total_filtered,
        cache_hit_rate=round(cache_hit_rate, 4),
    )


@router.delete("/{agent_id}")
async def delete_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete an agent."""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.id == uuid.UUID(agent_id))
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    await db.delete(agent)
    await db.commit()
    return {"status": "deleted", "agent_id": agent_id}
