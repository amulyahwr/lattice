import json
import time
from datetime import date, datetime, timezone
from hashlib import sha1
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
from lattice.synthesis import stream_synthesis, synthesize

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Lattice")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

_db: LatticeDB | None = None


def _get_db() -> LatticeDB:
    global _db
    if _db is None:
        _db = LatticeDB(Config.from_env().lattice_dir)
    return _db


# ── usage telemetry ───────────────────────────────────────────────────────────

def _record_usage(
    question: str,
    selection_ms: int,
    synthesis_ms: int,
    atom_count: int,
    channel: str = "web",
) -> None:
    cfg = Config.from_env()
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "query_hash": sha1(question.encode()).hexdigest(),
        "selection_ms": selection_ms,
        "synthesis_ms": synthesis_ms,
        "atom_count": atom_count,
        "channel": channel,
    }
    with (cfg.lattice_dir / "usage.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _load_usage() -> list[dict]:
    path = Config.from_env().lattice_dir / "usage.jsonl"
    if not path.exists():
        return []
    records = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _compute_streak(records: list[dict]) -> int:
    today = _utc_today()
    days_with_queries: set[date] = set()
    for r in records:
        try:
            d = date.fromisoformat(r["ts"][:10])
            days_with_queries.add(d)
        except (KeyError, ValueError):
            pass
    if today not in days_with_queries:
        return 0
    streak = 0
    current = today
    while current in days_with_queries:
        streak += 1
        current = date.fromordinal(current.toordinal() - 1)
    return streak


# ── models ────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    text: str
    source_id: str = "http"
    metadata: dict[str, Any] = {}


class QueryRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str
    reason: str | None = None


# ── routes ────────────────────────────────────────────────────────────────────

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
        t0 = time.monotonic()
        atoms = select(req.question, db=db)
        sel_ms = int((time.monotonic() - t0) * 1000)

        yield f'data: {json.dumps({"type": "atoms", "atoms": atoms})}\n\n'
        yield from stream_synthesis(req.question, atoms)

        # synthesis_ms is 0 for streaming — generator is lazy, timing not meaningful here
        _record_usage(req.question, sel_ms, 0, len(atoms), channel="web")

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/answer")
async def api_answer(req: QueryRequest):
    db = _get_db()
    t0 = time.monotonic()
    atoms = select(req.question, db=db)
    sel_ms = int((time.monotonic() - t0) * 1000)
    if not atoms:
        return {"ok": True, "answer": None, "atom_count": 0}
    t1 = time.monotonic()
    result = synthesize(req.question, atoms)
    syn_ms = int((time.monotonic() - t1) * 1000)
    _record_usage(req.question, sel_ms, syn_ms, len(atoms), channel="telegram")
    return {"ok": True, "answer": result.answer, "atom_count": len(atoms)}


@app.get("/api/usage/summary")
async def api_usage_summary():
    records = _load_usage()
    today = _utc_today().isoformat()
    seven_days_ago = date.fromordinal(_utc_today().toordinal() - 6).isoformat()

    today_count = sum(1 for r in records if r.get("ts", "")[:10] == today)
    week_count = sum(1 for r in records if r.get("ts", "")[:10] >= seven_days_ago)

    latencies = [
        r.get("selection_ms", 0) + r.get("synthesis_ms", 0)
        for r in records
        if "selection_ms" in r and "synthesis_ms" in r
    ]
    avg_latency_ms = int(sum(latencies) / len(latencies)) if latencies else 0

    streak = _compute_streak(records)

    return {
        "today": today_count,
        "last_7_days": week_count,
        "avg_latency_ms": avg_latency_ms,
        "streak": streak,
    }


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
