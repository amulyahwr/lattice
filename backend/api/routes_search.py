"""Search routes — query context as an agent with computed access."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_current_agent
from backend.engine.search import search_context
from backend.models.database import get_db
from backend.models.schemas import Agent

router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(..., description="Natural language query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results")


class SearchResult(BaseModel):
    chunk_id: str
    content: str
    chunk_index: int
    source_id: str
    source_name: str
    source_type: str
    source_classification: str | None = None
    relevance_score: float


class SearchResponse(BaseModel):
    query: str
    agent: str
    agent_clearance: str | None = None
    results: list[SearchResult]
    total: int


@router.post("/", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    agent: Agent = Depends(get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Search for relevant context — access resolved dynamically via trust broker."""
    results = await search_context(
        db=db,
        query=request.query,
        agent=agent,
        top_k=request.top_k,
    )

    return SearchResponse(
        query=request.query,
        agent=agent.name,
        agent_clearance=agent.clearance,
        results=[SearchResult(**r) for r in results],
        total=len(results),
    )
