"""API dependencies — auth, db sessions, etc."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import get_db
from backend.models.schemas import Agent


async def get_current_agent(
    x_api_key: str = Header(..., description="Agent API key"),
    db: AsyncSession = Depends(get_db),
) -> Agent:
    """Authenticate an agent via API key."""
    result = await db.execute(select(Agent).where(Agent.api_key == x_api_key))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return agent
