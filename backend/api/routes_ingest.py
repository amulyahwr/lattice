"""Source ingestion routes — upload files, run compiler, return stats.

Evolved from routes_sources.py. Upload flow becomes:
receive file → choose connector → run compiler pipeline → return atom/frame stats.
"""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
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
    classification: str
    domains: list[str] = []
    compilation: dict  # atoms_created, frames_created, kinds, domains


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    classification: str
    domains: list[str] = []
    atom_count: int = 0


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
    classification: str = Query(default="internal", description="public|internal|confidential|restricted"),
    domains: str = Query(default="", description="Comma-separated domain tags"),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file, run the compiler pipeline, return compilation stats."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename required")

    file_bytes = await file.read()
    filename = file.filename.lower()

    # Choose connector
    if filename.endswith(".pdf"):
        connector = PDFConnector()
        source_type = "pdf"
    elif filename.endswith(".md"):
        connector = MarkdownConnector()
        source_type = "markdown"
    else:
        connector = TextConnector()
        source_type = "text"

    # Ingest via connector to get chunks
    chunks = await connector.ingest(file_bytes=file_bytes)
    if not chunks:
        raise HTTPException(status_code=400, detail="No content could be extracted")

    domain_list = [d.strip() for d in domains.split(",") if d.strip()] if domains else []

    # Create source record
    source = Source(
        id=uuid.uuid4(),
        name=file.filename,
        source_type=source_type,
        classification=classification,
        domains=domain_list,
    )
    db.add(source)
    await db.flush()

    # Run compiler pipeline
    chunk_texts = [c.content for c in chunks]
    compilation_stats = await compile_source(db, source, chunk_texts)

    await db.commit()

    return IngestResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.source_type,
        classification=source.classification or "internal",
        domains=source.domains or [],
        compilation=compilation_stats,
    )


@router.get("/", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    """List all sources with atom counts."""
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
                classification=source.classification or "internal",
                domains=source.domains or [],
                atom_count=atom_count,
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
    """List atoms from a specific source."""
    # Verify source exists
    result = await db.execute(
        select(Source).where(Source.id == uuid.UUID(source_id))
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Source not found")

    atoms = await get_atoms_by_source(db, uuid.UUID(source_id), limit, offset)
    return [AtomResponse(**a) for a in atoms]


@router.delete("/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a source and all its atoms."""
    from backend.models.atoms import Atom

    result = await db.execute(
        select(Source).where(Source.id == uuid.UUID(source_id))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    # Delete atoms first
    atoms_result = await db.execute(
        select(Atom).where(Atom.source_id == source.id)
    )
    for atom in atoms_result.scalars().all():
        await db.delete(atom)

    await db.delete(source)
    await db.commit()
    return {"status": "deleted", "source_id": source_id}
