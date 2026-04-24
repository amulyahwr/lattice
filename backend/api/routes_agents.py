"""Agent management routes — create agents and manage permissions."""

import secrets
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.schemas import Agent, AgentPermission, Source

router = APIRouter(prefix="/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    name: str


class AgentResponse(BaseModel):
    id: str
    name: str
    api_key: str
    source_ids: list[str] = []


class GrantAccessRequest(BaseModel):
    source_id: str


@router.post("/", response_model=AgentResponse)
async def create_agent(
    request: CreateAgentRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new agent with a generated API key."""
    api_key = f"lat_{secrets.token_urlsafe(32)}"
    agent = Agent(
        id=uuid.uuid4(),
        name=request.name,
        api_key=api_key,
    )
    db.add(agent)
    await db.commit()

    return AgentResponse(id=str(agent.id), name=agent.name, api_key=agent.api_key, source_ids=[])


@router.get("/", response_model=list[AgentResponse])
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all agents with their granted source IDs."""
    result = await db.execute(select(Agent))
    agents = result.scalars().all()

    responses = []
    for agent in agents:
        perm_result = await db.execute(
            select(AgentPermission.source_id).where(AgentPermission.agent_id == agent.id)
        )
        source_ids = [str(row[0]) for row in perm_result.fetchall()]
        responses.append(AgentResponse(id=str(agent.id), name=agent.name, api_key=agent.api_key, source_ids=source_ids))
    return responses


@router.post("/{agent_id}/grant")
async def grant_access(
    agent_id: str,
    request: GrantAccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """Grant an agent access to a source."""
    # Verify agent exists
    agent_result = await db.execute(select(Agent).where(Agent.id == uuid.UUID(agent_id)))
    if not agent_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify source exists
    source_result = await db.execute(select(Source).where(Source.id == uuid.UUID(request.source_id)))
    if not source_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    existing = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == uuid.UUID(agent_id),
            AgentPermission.source_id == uuid.UUID(request.source_id),
        )
    )
    if existing.scalar_one_or_none():
        return {"status": "already_granted", "agent_id": agent_id, "source_id": request.source_id}

    permission = AgentPermission(
        id=uuid.uuid4(),
        agent_id=uuid.UUID(agent_id),
        source_id=uuid.UUID(request.source_id),
    )
    db.add(permission)
    await db.commit()

    return {"status": "granted", "agent_id": agent_id, "source_id": request.source_id}


@router.delete("/{agent_id}/revoke/{source_id}")
async def revoke_access(
    agent_id: str,
    source_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Revoke an agent's access to a source."""
    result = await db.execute(
        select(AgentPermission).where(
            AgentPermission.agent_id == uuid.UUID(agent_id),
            AgentPermission.source_id == uuid.UUID(source_id),
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Permission not found")

    await db.delete(perm)
    await db.commit()
    return {"status": "revoked", "agent_id": agent_id, "source_id": source_id}
