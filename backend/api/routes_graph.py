"""Graph API routes — query and traverse the knowledge graph."""

import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.graph import get_entity_neighborhood, get_graph_stats, search_entities
from backend.models.database import get_db

router = APIRouter(prefix="/graph", tags=["graph"])


class EntityResponse(BaseModel):
    id: str
    name: str
    type: str
    properties: dict = {}
    mention_count: int | None = None
    source_id: str | None = None
    relevance_score: float | None = None


class RelationshipResponse(BaseModel):
    id: str
    from_entity_id: str
    to_entity_id: str
    type: str
    weight: float
    direction: str
    properties: dict = {}


class NeighborhoodResponse(BaseModel):
    entity: EntityResponse | None
    relationships: list[RelationshipResponse]
    connected_entities: list[EntityResponse]


class GraphStatsResponse(BaseModel):
    total_entities: int
    total_relationships: int
    entities_by_type: dict[str, int]
    relationships_by_type: dict[str, int]


@router.get("/stats", response_model=GraphStatsResponse)
async def graph_stats(db: AsyncSession = Depends(get_db)):
    """Get high-level knowledge graph statistics."""
    stats = await get_graph_stats(db)
    return GraphStatsResponse(**stats)


@router.get("/search", response_model=list[EntityResponse])
async def search(
    q: str = Query(..., description="Search query"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search entities in the knowledge graph by semantic similarity."""
    results = await search_entities(db, query=q, entity_type=entity_type, limit=limit)
    return [EntityResponse(**r) for r in results]


@router.get("/entity/{entity_id}", response_model=NeighborhoodResponse)
async def get_neighborhood(
    entity_id: str,
    depth: int = Query(1, ge=1, le=3),
    db: AsyncSession = Depends(get_db),
):
    """Get an entity and its neighborhood — connected entities and relationships."""
    result = await get_entity_neighborhood(
        db, uuid.UUID(entity_id), depth=depth
    )

    entity = EntityResponse(**result["entity"]) if result["entity"] else None
    relationships = [RelationshipResponse(**r) for r in result["relationships"]]
    connected = [EntityResponse(**e) for e in result["connected_entities"]]

    return NeighborhoodResponse(
        entity=entity,
        relationships=relationships,
        connected_entities=connected,
    )
