"""Atom explorer routes — search, detail, neighborhood.

Admin endpoints for browsing the atom store. Uses ALL_BITS role mask
so the explorer sees all atoms regardless of classification.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import Atom, AtomSource, Source
from backend.models.database import get_db
from backend.serving.l3_search import search_atoms

router = APIRouter(prefix="/atoms", tags=["atoms"])

_ALL_BITS = 0xFF  # Admin explorer — see everything


# ── Response models ──


class SourceRef(BaseModel):
    source_id: str
    source_name: str
    source_type: str
    is_primary: bool


class AtomResponse(BaseModel):
    atom_id: str
    content: str
    raw_content: str | None = None
    kind: str
    domain: list[str] = []
    confidence: float = 1.0
    access_mask: int = 0
    links: list[dict] = []
    canonical: dict | None = None
    freshness: str | None = None
    compiled_at: str | None = None
    version: int = 1
    source_name: str | None = None
    source_type: str | None = None
    relevance_score: float | None = None
    sources: list[SourceRef] = []


class NeighborEntry(BaseModel):
    atom: AtomResponse
    relation: str


class NeighborhoodResponse(BaseModel):
    center: AtomResponse
    neighbors: list[NeighborEntry]


# ── Helper ──


async def _get_sources(db: AsyncSession, atom_id: uuid.UUID) -> list[SourceRef]:
    rows = (
        await db.execute(
            select(AtomSource, Source.name.label("source_name"), Source.source_type)
            .join(Source, AtomSource.source_id == Source.id)
            .where(AtomSource.atom_id == atom_id)
        )
    ).fetchall()
    return [
        SourceRef(
            source_id=str(row.AtomSource.source_id),
            source_name=row.source_name,
            source_type=row.source_type,
            is_primary=row.AtomSource.is_primary,
        )
        for row in rows
    ]


def _atom_to_response(a: Atom, sources: list[SourceRef] | None = None) -> AtomResponse:
    return AtomResponse(
        atom_id=str(a.id),
        content=a.content,
        raw_content=a.raw_content,
        kind=a.kind,
        domain=a.domain or [],
        confidence=a.confidence or 1.0,
        access_mask=a.access_mask or 0,
        links=a.links or [],
        canonical=a.canonical,
        freshness=a.freshness.isoformat() if a.freshness else None,
        compiled_at=a.compiled_at.isoformat() if a.compiled_at else None,
        version=a.version or 1,
        sources=sources or [],
    )


# ── Routes ──


@router.get("/", response_model=list[AtomResponse])
async def list_atoms(
    search: str | None = Query(default=None, description="Semantic search query"),
    kind: str | None = Query(default=None, description="Filter by kind"),
    domain: str | None = Query(default=None, description="Filter by domain tag"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List or search atoms.

    Semantic search when `search` is provided; direct DB listing otherwise.
    """
    if search and search.strip():
        results = await search_atoms(
            db=db,
            query=search.strip(),
            role_mask=_ALL_BITS,
            top_k=limit,
            domain_filter=domain,
        )
        if kind:
            results = [r for r in results if r["kind"] == kind]
        return [
            AtomResponse(
                atom_id=r["atom_id"],
                content=r["content"],
                raw_content=r.get("raw_content"),
                kind=r["kind"],
                domain=r.get("domain") or [],
                confidence=r.get("confidence") or 1.0,
                access_mask=r.get("access_mask") or 0,
                links=r.get("links") or [],
                freshness=r.get("freshness"),
                version=r.get("version") or 1,
                source_name=r.get("source_name"),
                source_type=r.get("source_type"),
                relevance_score=r.get("relevance_score"),
            )
            for r in results
        ]

    # Direct DB listing
    stmt = select(Atom)
    if kind:
        stmt = stmt.where(Atom.kind == kind)
    if domain:
        stmt = stmt.where(Atom.domain.any(domain))
    stmt = stmt.order_by(Atom.compiled_at.desc()).limit(limit).offset(offset)

    atoms = (await db.execute(stmt)).scalars().all()
    return [_atom_to_response(a) for a in atoms]


@router.get("/graph", response_model=dict)
async def get_full_graph(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Get all atoms with their relationships for full graph visualization."""
    # Fetch atoms
    stmt = select(Atom).order_by(Atom.compiled_at.desc()).limit(limit)
    atoms = (await db.execute(stmt)).scalars().all()

    # Build nodes and edges
    nodes = []
    edges = []
    edge_set = set()  # To avoid duplicate edges

    for atom in atoms:
        nodes.append(
            {
                "id": str(atom.id),
                "content": atom.content,
                "kind": atom.kind,
                "domain": atom.domain or [],
                "confidence": atom.confidence or 1.0,
            }
        )

        # Add edges from this atom's links
        for link in atom.links or []:
            try:
                target_id = link.get("target_id")
                relation = link.get("relation", "related")

                # Create edge key to avoid duplicates
                edge_key = f"{atom.id}-{target_id}"
                if edge_key not in edge_set:
                    edges.append(
                        {
                            "source": str(atom.id),
                            "target": str(target_id),
                            "relation": relation,
                        }
                    )
                    edge_set.add(edge_key)
            except (KeyError, ValueError):
                continue

    return {"nodes": nodes, "edges": edges}


@router.get("/{atom_id}", response_model=AtomResponse)
async def get_atom(atom_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single atom with full metadata and all source references."""
    try:
        uid = uuid.UUID(atom_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid atom ID")

    atom = (await db.execute(select(Atom).where(Atom.id == uid))).scalar_one_or_none()

    if not atom:
        raise HTTPException(status_code=404, detail="Atom not found")

    sources = await _get_sources(db, atom.id)
    return _atom_to_response(atom, sources)


@router.get("/{atom_id}/neighborhood", response_model=NeighborhoodResponse)
async def get_atom_neighborhood(atom_id: str, db: AsyncSession = Depends(get_db)):
    """Get an atom and all atoms it links to (one hop out)."""
    try:
        uid = uuid.UUID(atom_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid atom ID")

    center = (await db.execute(select(Atom).where(Atom.id == uid))).scalar_one_or_none()

    if not center:
        raise HTTPException(status_code=404, detail="Atom not found")

    center_sources = await _get_sources(db, center.id)
    center_response = _atom_to_response(center, center_sources)

    neighbors: list[NeighborEntry] = []
    for link in center.links or []:
        try:
            target_id = uuid.UUID(link["target_id"])
        except (KeyError, ValueError):
            continue

        neighbor = (
            await db.execute(select(Atom).where(Atom.id == target_id))
        ).scalar_one_or_none()

        if neighbor:
            neighbors.append(
                NeighborEntry(
                    atom=_atom_to_response(neighbor),
                    relation=link.get("relation", "topical"),
                )
            )

    return NeighborhoodResponse(center=center_response, neighbors=neighbors)
