"""Vector search over chunks."""

from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text
from backend.models.schemas import AgentPermission, Chunk, Source


async def search_context(
    db: AsyncSession,
    query: str,
    agent_id: UUID,
    top_k: int = 5,
) -> list[dict]:
    """
    Search for relevant context chunks scoped to the agent's permissions.

    Returns ranked results with content, source info, and similarity score.
    """
    # Get sources this agent can access
    perm_result = await db.execute(
        select(AgentPermission.source_id).where(AgentPermission.agent_id == agent_id)
    )
    allowed_source_ids = [row[0] for row in perm_result.fetchall()]

    if not allowed_source_ids:
        return []

    # Generate query embedding
    query_embedding = embed_text(query)

    # Vector similarity search with pgvector
    # Using cosine distance (<=> operator)
    stmt = (
        select(
            Chunk.id,
            Chunk.content,
            Chunk.chunk_index,
            Chunk.source_id,
            Source.name.label("source_name"),
            Source.source_type,
            Chunk.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .join(Source, Chunk.source_id == Source.id)
        .where(Chunk.source_id.in_(allowed_source_ids))
        .order_by("distance")
        .limit(top_k)
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "chunk_id": str(row.id),
            "content": row.content,
            "chunk_index": row.chunk_index,
            "source_id": str(row.source_id),
            "source_name": row.source_name,
            "source_type": row.source_type,
            "relevance_score": round(1 - row.distance, 4),  # Convert distance to similarity
        }
        for row in rows
    ]
