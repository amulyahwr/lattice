"""Vector search over chunks — now with computed access resolution."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.access import get_accessible_source_ids, log_access
from backend.engine.embeddings import embed_text
from backend.models.schemas import Agent, Chunk, Source


async def search_context(
    db: AsyncSession,
    query: str,
    agent: Agent,
    top_k: int = 5,
) -> list[dict]:
    """
    Search for relevant context chunks using computed access resolution.

    Access is determined by:
    1. Manual overrides (grant/deny)
    2. Clearance check (agent clearance >= source classification)
    3. Semantic relevance (agent purpose vs source summary)
    4. Domain overlap
    """
    # Compute accessible sources for this agent
    allowed_source_ids = await get_accessible_source_ids(db, agent)

    if not allowed_source_ids:
        return []

    # Generate query embedding
    query_embedding = embed_text(query)

    # Vector similarity search with pgvector
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.chunk_index,
            Chunk.source_id,
            Source.name.label("source_name"),
            Source.source_type,
            Source.classification.label("source_classification"),
            Chunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(Source, Chunk.source_id == Source.id)
        .where(Chunk.source_id.in_(allowed_source_ids))
        .order_by("distance")
        .limit(top_k)
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    # Log access for audit
    accessed_source_ids = set()
    for row in rows:
        if row.source_id not in accessed_source_ids:
            await log_access(
                db=db,
                agent_id=agent.id,
                source_id=row.source_id,
                query=query,
                decision="granted",
                reason="Computed access — search result returned",
                relevance_score=round(1 - row.distance, 4),
            )
            accessed_source_ids.add(row.source_id)

    await db.commit()

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_index": row.chunk_index,
            "source_id": str(row.source_id),
            "source_name": row.source_name,
            "source_type": row.source_type,
            "source_classification": row.source_classification,
            "relevance_score": round(1 - row.distance, 4),
        }
        for row in rows
    ]
