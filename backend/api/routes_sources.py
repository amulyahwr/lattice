"""Source management routes — upload, manage, and get recommendations."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connectors.pdf import PDFConnector
from backend.engine.embeddings import embed_text, embed_texts
from backend.engine.recommendations import recommend_agents_for_source
from backend.engine.summarize import extractive_summary, suggest_domains
from backend.models.database import get_db
from backend.models.schemas import Chunk, Source

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    chunk_count: int
    summary: str | None = None
    classification: str | None = None
    domains: list[str] = []
    owner: str | None = None
    org_scope: list[str] = []


class RecommendationResponse(BaseModel):
    agent_id: str
    agent_name: str
    agent_purpose: str | None
    source_id: str
    source_name: str
    source_summary: str | None
    relevance_score: float
    semantic_match: float
    domain_overlap: float
    clearance_ok: bool
    status: str
    note: str


class SourceUpdateRequest(BaseModel):
    classification: str | None = None
    domains: list[str] | None = None
    owner: str | None = None
    org_scope: list[str] | None = None


@router.post("/upload/pdf", response_model=SourceResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF — chunks it, embeds it, generates summary + DNA."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()

    # Ingest via connector
    connector = PDFConnector()
    ingested_chunks = await connector.ingest(file_bytes=file_bytes)

    if not ingested_chunks:
        raise HTTPException(status_code=400, detail="No text could be extracted from PDF")

    # Generate summary from chunks
    chunk_texts = [c.content for c in ingested_chunks]
    summary = extractive_summary(chunk_texts)
    summary_embedding = embed_text(summary) if summary else None

    # Auto-suggest domains
    domains = suggest_domains(summary, "pdf")

    # Create source with DNA
    source = Source(
        id=uuid.uuid4(),
        name=file.filename,
        source_type="pdf",
        summary=summary,
        summary_embedding=summary_embedding,
        classification="internal",  # default — user can change
        domains=domains,
    )
    db.add(source)

    # Embed all chunks in batch
    embeddings = embed_texts(chunk_texts)

    for ingested, embedding in zip(ingested_chunks, embeddings):
        chunk = Chunk(
            id=uuid.uuid4(),
            source_id=source.id,
            content=ingested.content,
            chunk_index=ingested.chunk_index,
            embedding=embedding,
        )
        db.add(chunk)

    await db.commit()

    return SourceResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.source_type,
        chunk_count=len(ingested_chunks),
        summary=source.summary,
        classification=source.classification,
        domains=source.domains or [],
    )


@router.get("/", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    """List all data sources with their DNA."""
    result = await db.execute(select(Source))
    sources = result.scalars().all()

    responses = []
    for source in sources:
        chunk_count_result = await db.execute(
            select(Chunk.id).where(Chunk.source_id == source.id)
        )
        count = len(chunk_count_result.fetchall())
        responses.append(
            SourceResponse(
                id=str(source.id),
                name=source.name,
                source_type=source.source_type,
                chunk_count=count,
                summary=source.summary,
                classification=source.classification,
                domains=source.domains or [],
                owner=source.owner,
                org_scope=source.org_scope or [],
            )
        )

    return responses


@router.patch("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: str,
    update: SourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update a source's DNA (classification, domains, owner, org_scope)."""
    result = await db.execute(select(Source).where(Source.id == uuid.UUID(source_id)))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    if update.classification is not None:
        source.classification = update.classification
    if update.domains is not None:
        source.domains = update.domains
    if update.owner is not None:
        source.owner = update.owner
    if update.org_scope is not None:
        source.org_scope = update.org_scope

    await db.commit()

    chunk_count_result = await db.execute(
        select(Chunk.id).where(Chunk.source_id == source.id)
    )
    count = len(chunk_count_result.fetchall())

    return SourceResponse(
        id=str(source.id),
        name=source.name,
        source_type=source.source_type,
        chunk_count=count,
        summary=source.summary,
        classification=source.classification,
        domains=source.domains or [],
        owner=source.owner,
        org_scope=source.org_scope or [],
    )


@router.get("/{source_id}/recommendations", response_model=list[RecommendationResponse])
async def get_source_recommendations(
    source_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get agent recommendations for a source — which agents would benefit?"""
    result = await db.execute(select(Source).where(Source.id == uuid.UUID(source_id)))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    recommendations = await recommend_agents_for_source(db, source)
    return [RecommendationResponse(**r) for r in recommendations]


@router.delete("/{source_id}")
async def delete_source(source_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a source and all its chunks."""
    result = await db.execute(select(Source).where(Source.id == uuid.UUID(source_id)))
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    await db.delete(source)
    await db.commit()
    return {"status": "deleted", "source_id": source_id}
