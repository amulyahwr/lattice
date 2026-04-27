"""Source ingestion routes — upload files, run compiler, return stats."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.pipeline import compile_source
from backend.connectors.pdf import PDFConnector
from backend.connectors.text import MarkdownConnector, TextConnector
from backend.models.atoms import Source
from backend.models.database import get_db
from backend.serving.l3_search import count_atoms_by_source, get_atoms_by_source

router = APIRouter(prefix="/sources", tags=["sources"])


class IngestResponse(BaseModel):
    id: str
    name: str
    source_type: str
    compilation: dict


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    domains: list[str] = []
    atom_count: int = 0
    created_at: str | None = None


class AtomResponse(BaseModel):
    atom_id: str
    content: str
    raw_content: str | None = None
    kind: str
    domain: list[str] = []
    confidence: float | None = None
    access_mask: int = 0
    links: list[dict] = []
    freshness: str | None = None
    version: int = 1


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file, run the compiler pipeline, return compilation stats."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    file_bytes = await file.read()
    filename = file.filename.lower()

    if filename.endswith(".pdf"):
        connector = PDFConnector()
        source_type = "pdf"
    elif filename.endswith(".md"):
        connector = MarkdownConnector()
        source_type = "markdown"
    else:
        connector = TextConnector()
        source_type = "text"

    try:
        chunks = await connector.ingest(file_bytes=file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="No content could be extracted") from exc
    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be extracted")

    source = Source(
        id=uuid.uuid4(),
        name=file.filename,
        source_type=source_type,
    )
    db.add(source)
    await db.flush()

    chunk_texts = [c.content for c in chunks]
    compilation_stats = await compile_source(db, source, chunk_texts)

    # Write detected domains back to the source record for display
    source.domains = compilation_stats.get("domains", [])

    await db.commit()

    return IngestResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.source_type,
        compilation=compilation_stats,
    )


@router.get("/", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Source).order_by(Source.created_at.desc()))
    sources = result.scalars().all()

    responses = []
    for source in sources:
        atom_count = await count_atoms_by_source(db, source.id)
        responses.append(
            SourceResponse(
                id=str(source.id),
                name=source.name,
                source_type=source.source_type,
                domains=source.domains or [],
                atom_count=atom_count,
                created_at=source.created_at.isoformat() if source.created_at else None,
            )
        )

    return responses


@router.get("/{source_id}/atoms", response_model=list[AtomResponse])
async def list_source_atoms(
    source_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Source).where(Source.id == uuid.UUID(source_id)))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    atoms = await get_atoms_by_source(db, uuid.UUID(source_id), limit, offset)
    return [AtomResponse(**a) for a in atoms]


@router.delete("/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    from backend.models.atoms import Atom, AtomSource

    source_uuid = uuid.UUID(source_id)
    result = await db.execute(select(Source).where(Source.id == source_uuid))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    linked = (
        await db.execute(select(AtomSource.atom_id).where(AtomSource.source_id == source_uuid))
    ).scalars().all()

    for row in await db.execute(select(AtomSource).where(AtomSource.source_id == source_uuid)):
        await db.delete(row[0])

    await db.flush()

    for atom_id in linked:
        remaining = (
            await db.execute(
                select(func.count(AtomSource.source_id)).where(AtomSource.atom_id == atom_id)
            )
        ).scalar() or 0
        if remaining == 0:
            atom = (await db.execute(select(Atom).where(Atom.id == atom_id))).scalar_one_or_none()
            if atom:
                await db.delete(atom)

    await db.delete(source)
    await db.commit()
    return {"status": "deleted", "source_id": source_id}
