"""Context query routes — query and compare context as agents.

Evolved from routes_search.py. Queries go through the Query Router
(L2 → L3) with bitmask access control and token budgeting.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_agent
from backend.models.atoms import AgentProfile
from backend.models.database import get_db
from backend.serving.router import compare_context, query_context

router = APIRouter(prefix="/context", tags=["context"])


class ContextQueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=10, ge=1, le=50, description="Max atoms to return")


class ContextQueryResponse(BaseModel):
    query: str
    agent_name: str
    atoms: list[dict]
    cache_tier: str
    latency_ms: float
    atoms_served: int
    atoms_filtered: int
    total_tokens: int


class CompareRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    agent_ids: list[str] = Field(..., description="Agent IDs to compare")
    top_k: int = Field(default=10, ge=1, le=50)


class CompareResult(BaseModel):
    agent_id: str
    agent_name: str
    role_mask: int
    atoms: list[dict]
    cache_tier: str
    latency_ms: float
    atoms_served: int
    atoms_filtered: int
    total_tokens: int


class CompareResponse(BaseModel):
    query: str
    results: list[CompareResult]


@router.post("/query", response_model=ContextQueryResponse)
async def context_query(
    request: ContextQueryRequest,
    agent: AgentProfile = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Query context as an authenticated agent.

    Routes through L2 (frame cache) → L3 (pgvector) with bitmask
    access filtering and token budget trimming.
    """
    result = await query_context(
        db=db,
        query=request.query,
        agent=agent,
        top_k=request.top_k,
    )

    await db.commit()

    return ContextQueryResponse(
        query=request.query,
        agent_name=agent.name,
        **result,
    )


@router.post("/compare", response_model=CompareResponse)
async def context_compare(
    request: CompareRequest,
    db: AsyncSession = Depends(get_db),
):
    """Compare context delivery for the same query across multiple agents.

    Shows how different agents see different context based on their
    role masks and domain subscriptions.
    """
    agents: list[AgentProfile] = []
    for agent_id in request.agent_ids:
        result = await db.execute(
            select(AgentProfile).where(AgentProfile.id == uuid.UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(
                status_code=404, detail=f"Agent {agent_id} not found"
            )
        agents.append(agent)

    results = await compare_context(
        db=db,
        query=request.query,
        agents=agents,
        top_k=request.top_k,
    )

    await db.commit()

    return CompareResponse(
        query=request.query,
        results=[CompareResult(**r) for r in results],
    )
