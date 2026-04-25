"""L3 Search — pgvector cosine similarity search on atoms.

Evolved from engine/search.py. Queries atoms (not chunks), applies
bitmask access filter before vector search for efficiency.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text
from backend.models.atoms import Atom, Source


async def search_atoms(
    db: AsyncSession,
    query: str,
    role_mask: int,
    top_k: int = 20,
    domain_filter: str | None = None,
) -> list[dict]:
    """Search atoms by semantic similarity with access filtering.

    Args:
        db: Database session
        query: Natural language query
        role_mask: Agent's role bitmask for access control
        top_k: Maximum results
        domain_filter: Optional domain to restrict search

    Returns:
        List of atom dicts with relevance scores.
    """
    query_embedding = embed_text(query)

    stmt = (
        select(
            Atom.id,
            Atom.content,
            Atom.raw_content,
            Atom.kind,
            Atom.domain,
            Atom.confidence,
            Atom.access_mask,
            Atom.links,
            Atom.source_id,
            Atom.freshness,
            Atom.version,
            Source.name.label("source_name"),
            Source.source_type,
            Source.classification.label("source_classification"),
            Atom.dense_vec.cosine_distance(query_embedding).label("distance"),
        )
        .join(Source, Atom.source_id == Source.id)
        .where(Atom.access_mask.bitwise_and(role_mask) != 0)
        .order_by("distance")
        .limit(top_k)
    )

    if domain_filter:
        stmt = stmt.where(Atom.domain.any(domain_filter))

    result = await db.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "atom_id": str(row.id),
            "content": row.content,
            "raw_content": row.raw_content,
            "kind": row.kind,
            "domain": row.domain or [],
            "confidence": row.confidence,
            "access_mask": row.access_mask,
            "links": row.links or [],
            "source_id": str(row.source_id),
            "source_name": row.source_name,
            "source_type": row.source_type,
            "source_classification": row.source_classification,
            "freshness": row.freshness.isoformat() if row.freshness else None,
            "version": row.version,
            "relevance_score": round(1 - row.distance, 4),
        }
        for row in rows
    ]


async def count_atoms_by_source(db: AsyncSession, source_id) -> int:
    """Count atoms belonging to a source."""
    from sqlalchemy import func

    result = await db.execute(
        select(func.count(Atom.id)).where(Atom.source_id == source_id)
    )
    return result.scalar() or 0


async def get_atoms_by_source(
    db: AsyncSession,
    source_id,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get atoms belonging to a source."""
    result = await db.execute(
        select(Atom)
        .where(Atom.source_id == source_id)
        .order_by(Atom.compiled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    atoms = result.scalars().all()

    return [
        {
            "atom_id": str(a.id),
            "content": a.content,
            "raw_content": a.raw_content,
            "kind": a.kind,
            "domain": a.domain or [],
            "confidence": a.confidence,
            "access_mask": a.access_mask,
            "links": a.links or [],
            "freshness": a.freshness.isoformat() if a.freshness else None,
            "version": a.version,
        }
        for a in atoms
    ]
