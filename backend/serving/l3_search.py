"""L3 Search — pgvector cosine similarity search on atoms.

Evolved from engine/search.py. Queries atoms (not chunks), applies
bitmask access filter before vector search for efficiency.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text
from backend.models.atoms import Atom, AtomSource, Source


async def search_atoms(
    db: AsyncSession,
    query: str,
    role_mask: int,
    top_k: int = 20,
    domain_filter: list[str] | None = None,
    min_relevance: float = 0.0,
) -> list[dict]:
    """Search atoms by semantic similarity with access filtering.

    Joins through AtomSource to get primary source metadata.
    Returns a `sources` list per atom covering all contributing sources.
    """
    query_embedding = embed_text(query)

    # Primary source subquery for display metadata
    primary_source = (
        select(AtomSource.atom_id, Source.name, Source.source_type)
        .join(Source, AtomSource.source_id == Source.id)
        .where(AtomSource.is_primary.is_(True))
        .subquery()
    )

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
            Atom.freshness,
            Atom.version,
            primary_source.c.name.label("source_name"),
            primary_source.c.source_type,
            Atom.dense_vec.cosine_distance(query_embedding).label("distance"),
        )
        .outerjoin(primary_source, Atom.id == primary_source.c.atom_id)
        .where(Atom.access_mask.bitwise_and(role_mask) != 0)
        .order_by("distance")
        .limit(top_k)
    )

    if domain_filter:
        # Atom must be tagged with at least one of the agent's focus domains
        stmt = stmt.where(Atom.domain.overlap(domain_filter))

    result = await db.execute(stmt)
    rows = result.fetchall()

    atoms = []
    for row in rows:
        relevance = round(1 - row.distance, 4)
        if relevance < min_relevance:
            continue
        atoms.append({
            "atom_id": str(row.id),
            "content": row.content,
            "raw_content": row.raw_content,
            "kind": row.kind,
            "domain": row.domain or [],
            "confidence": row.confidence,
            "access_mask": row.access_mask,
            "links": row.links or [],
            "source_name": row.source_name,
            "source_type": row.source_type,
            "freshness": row.freshness.isoformat() if row.freshness else None,
            "version": row.version,
            "relevance_score": relevance,
        })
    return atoms


async def count_atoms_by_source(db: AsyncSession, source_id) -> int:
    """Count atoms linked to a source via atom_sources."""
    result = await db.execute(
        select(func.count(AtomSource.atom_id)).where(AtomSource.source_id == source_id)
    )
    return result.scalar() or 0


async def get_atoms_by_source(
    db: AsyncSession,
    source_id,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """Get atoms linked to a source via atom_sources."""
    result = await db.execute(
        select(Atom)
        .join(AtomSource, Atom.id == AtomSource.atom_id)
        .where(AtomSource.source_id == source_id)
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
