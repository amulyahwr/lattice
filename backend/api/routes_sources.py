"""Source management routes — upload and manage data sources."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.connectors.pdf import PDFConnector
from backend.engine.embeddings import embed_texts
from backend.models.database import get_db
from backend.models.schemas import AgentPermission, Chunk, Source

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceResponse(BaseModel):
    id: str
    name: str
    source_type: str
    chunk_count: int


@router.post("/upload/pdf", response_model=SourceResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF file, chunk it, embed it, and store it."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()

    # Ingest via connector
    connector = PDFConnector()
    ingested_chunks = await connector.ingest(file_bytes=file_bytes)

    if not ingested_chunks:
        raise HTTPException(status_code=400, detail="No text could be extracted from PDF")

    # Create source record
    source = Source(
        id=uuid.uuid4(),
        name=file.filename,
        source_type="pdf",
    )
    db.add(source)

    # Embed all chunks in batch
    texts = [c.content for c in ingested_chunks]
    embeddings = embed_texts(texts)

    # Create chunk records
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
    )


@router.get("/", response_model=list[SourceResponse])
async def list_sources(db: AsyncSession = Depends(get_db)):
    """List all data sources."""
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
            )
        )

    return responses


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
