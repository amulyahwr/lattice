"""API dependencies — auth, db sessions, cache access."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import AgentProfile
from backend.models.database import get_db
from backend.serving.l2_cache import L2Cache, l2_cache


async def get_current_agent(
    x_api_key: str = Header(..., description="Agent API key"),
    db: AsyncSession = Depends(get_db),
) -> AgentProfile:
    """Authenticate an agent via API key."""
    result = await db.execute(
        select(AgentProfile).where(AgentProfile.api_key == x_api_key)
    )
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return agent


def get_l2_cache() -> L2Cache:
    """Dependency to inject L2 cache."""
    return l2_cache
