import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lattice.client import DaemonClient
from lattice.config import Config
from lattice.db import LatticeDB
from lattice.selection import select
from lattice.synthesis import stream_synthesis

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Lattice")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

_db: LatticeDB | None = None


def _get_db() -> LatticeDB:
    global _db
    if _db is None:
        _db = LatticeDB(Config.from_env().lattice_dir)
    return _db


class IngestRequest(BaseModel):
    text: str
    source_id: str = "http"
    metadata: dict[str, Any] = {}


class QueryRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str              # "up" | "down"
    reason: str | None = None  # "wrong_sources" | "inaccurate" | "incomplete" | "off_topic"


@app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/ingest")
async def api_ingest(req: IngestRequest):
    metadata = {**req.metadata, "observed_at": datetime.now(timezone.utc).isoformat()}
    try:
        atom_ids = DaemonClient().ingest(req.text, req.source_id, metadata=metadata)
    except (RuntimeError, OSError):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "daemon unavailable"},
        )
    return {"ok": True, "atom_ids": atom_ids}


@app.post("/api/query")
async def api_query(req: QueryRequest) -> StreamingResponse:
    db = _get_db()

    def _generate():
        atoms = select(req.question, db=db)
        yield f'data: {json.dumps({"type": "atoms", "atoms": atoms})}\n\n'
        yield from stream_synthesis(req.question, atoms)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/feedback")
async def api_feedback(req: FeedbackRequest):
    cfg = Config.from_env()
    feedback_path = cfg.lattice_dir / "feedback.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": req.question,
        "answer": req.answer,
        "rating": req.rating,
        "reason": req.reason,
    }
    with feedback_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
    return {"ok": True}


@app.get("/api/atoms/recent")
async def api_atoms_recent(limit: int = 20):
    db = _get_db()
    atoms = [a for a in db.all() if not a.is_superseded]
    atoms.sort(
        key=lambda a: a.observed_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    atoms = atoms[:limit]
    return [
        {
            "atom_id": a.atom_id,
            "subject": a.subject,
            "kind": a.kind,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "source_id": a.source_id,
        }
        for a in atoms
    ]
