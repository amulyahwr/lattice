import json
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from lattice.client import DaemonClient
from lattice.config import Config
from lattice.db import LatticeDB
from lattice.selection import select
from lattice.synthesis import stream_synthesis, synthesize
from lattice.telemetry import compute_streak, load_usage, record_grace_day, record_usage

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Lattice")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

_db: LatticeDB | None = None
_cfg: Config | None = None


def set_config(cfg: Config) -> None:
    """Called by the daemon at startup to inject a pre-built Config."""
    global _cfg, _db
    _cfg = cfg
    _db = LatticeDB(cfg.lattice_dir)


def _get_cfg() -> Config:
    if _cfg is not None:
        return _cfg
    return Config.from_env()  # not cached — picks up env changes (test isolation)


def _get_db() -> LatticeDB:
    if _db is not None:
        return _db
    return LatticeDB(_get_cfg().lattice_dir)  # not cached — new DB per test call


# ── models ────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    text: str
    source_id: str = "http"
    url: str | None = None    # browser extension: page URL → overrides source_id
    title: str | None = None  # browser extension: page title → stored as source_title
    metadata: dict[str, Any] = {}


class QueryRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str
    reason: str | None = None
    atom_ids: list[str] | None = None
    dismissed_atom_ids: list[str] | None = None
    citation_map: dict[str, str] | None = None


# ── routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/ingest")
async def api_ingest(req: IngestRequest):
    source_id = req.url or req.source_id
    metadata = {**req.metadata, "observed_at": datetime.now(timezone.utc).isoformat()}
    if req.title:
        metadata["source_title"] = req.title
    try:
        result = DaemonClient().ingest_full(req.text, source_id, metadata=metadata)
    except (RuntimeError, OSError):
        return JSONResponse(
            status_code=503,
            content={"ok": False, "error": "daemon unavailable"},
        )
    return {"ok": True, "atom_ids": result.get("atom_ids", [])}


@app.post("/api/ingest-file")
async def api_ingest_file(file: UploadFile = File(...)):
    """Accept any file and ingest its text. PDF, .docx, and plain text supported."""
    import tempfile, os
    suffix = Path(file.filename or "upload").suffix.lower() or ".txt"
    data = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        from lattice.util import extract_file_text
        try:
            text, source_id = extract_file_text(tmp_path)
            if file.filename:
                source_id = source_id.replace(os.path.basename(tmp_path), file.filename)
        except ImportError as exc:
            return JSONResponse(status_code=501, content={"ok": False, "error": str(exc)})
        except ValueError as exc:
            return JSONResponse(status_code=422, content={"ok": False, "error": str(exc)})

        metadata = {"observed_at": datetime.now(timezone.utc).isoformat()}
        try:
            result = DaemonClient().ingest_full(text, source_id, metadata=metadata)
        except (RuntimeError, OSError):
            return JSONResponse(status_code=503, content={"ok": False, "error": "daemon unavailable"})
        return {
            "ok": True,
            "atom_ids": result.get("atom_ids", []),
            "atoms_new": result.get("atoms_new", 0),
            "atoms_updated": result.get("atoms_updated", 0),
            "duplicates_skipped": result.get("duplicates_skipped", 0),
            "filename": file.filename,
        }
    finally:
        os.unlink(tmp_path)


@app.post("/api/query")
async def api_query(req: QueryRequest) -> StreamingResponse:
    db = _get_db()

    cfg = _get_cfg()

    def _generate():
        t0 = time.monotonic()
        atoms = select(req.question, db=db, cfg=cfg)
        sel_ms = int((time.monotonic() - t0) * 1000)
        for i, a in enumerate(atoms):
            a["src_key"] = f"{i + 1}"

        yield f'data: {json.dumps({"type": "atoms", "atoms": atoms})}\n\n'
        yield from stream_synthesis(req.question, atoms, cfg)

        # synthesis_ms is 0 for streaming — generator is lazy, timing not meaningful here
        record_usage(req.question, sel_ms, 0, len(atoms), channel="web", cfg=cfg)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/answer")
async def api_answer(req: QueryRequest):
    db = _get_db()
    cfg = _get_cfg()
    t0 = time.monotonic()
    atoms = select(req.question, db=db, cfg=cfg)
    sel_ms = int((time.monotonic() - t0) * 1000)
    if not atoms:
        return {"ok": True, "answer": None, "atom_count": 0}
    for i, a in enumerate(atoms):
        a["src_key"] = f"{i + 1}"
    t1 = time.monotonic()
    result = synthesize(req.question, atoms, cfg)
    syn_ms = int((time.monotonic() - t1) * 1000)
    record_usage(req.question, sel_ms, syn_ms, len(atoms), channel="telegram", cfg=cfg)
    atom_meta = [
        {
            "atom_id": a.get("atom_id"),
            "src_key": a.get("src_key"),
            "ingested_at": a.get("ingested_at"),
            "subject": a.get("subject"),
            "source_title": a.get("source_title"),
            "source_id": a.get("source_id"),
            "content_preview": (a.get("content") or "")[:80],
        }
        for a in atoms
    ]
    return {"ok": True, "answer": result.answer, "atom_count": len(atoms), "atoms": atom_meta, "pii_protected": result.pii_protected}


@app.get("/api/usage/summary")
async def api_usage_summary():
    cfg = _get_cfg()
    records = load_usage(cfg)
    today = datetime.now(timezone.utc).date().isoformat()
    seven_days_ago = date.fromordinal(datetime.now(timezone.utc).date().toordinal() - 6).isoformat()

    today_count = sum(1 for r in records if r.get("ts", "")[:10] == today and r.get("type") != "grace_day_used")
    week_count = sum(1 for r in records if r.get("ts", "")[:10] >= seven_days_ago and r.get("type") != "grace_day_used")

    latencies = [
        r.get("selection_ms", 0) + r.get("synthesis_ms", 0)
        for r in records
        if "selection_ms" in r and "synthesis_ms" in r
    ]
    avg_latency_ms = int(sum(latencies) / len(latencies)) if latencies else 0

    streak, grace_day_active = compute_streak(records)

    db = _get_db()
    atom_count = len([a for a in db.all() if not a.is_superseded])

    return {
        "today": today_count,
        "last_7_days": week_count,
        "avg_latency_ms": avg_latency_ms,
        "streak": streak,
        "grace_day_active": grace_day_active,
        "atom_count": atom_count,
    }


@app.post("/api/feedback")
async def api_feedback(req: FeedbackRequest):
    cfg = _get_cfg()
    feedback_path = cfg.lattice_dir / "feedback.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": req.question,
        "answer": req.answer,
        "rating": req.rating,
        "reason": req.reason,
        "atom_ids": req.atom_ids or [],
        "dismissed_atom_ids": req.dismissed_atom_ids or [],
        "citation_map": req.citation_map or {},
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
            "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
            "source_id": a.source_id,
        }
        for a in atoms
    ]


@app.get("/api/topic/depth")
async def api_topic_depth(subject: str):
    """Return atom count for a subject (used by topic depth cards)."""
    db = _get_db()
    norm = subject.lower().strip()
    count = sum(
        1 for a in db.all()
        if not a.is_superseded and (a.subject or "").lower().strip() == norm
    )
    return {"subject": subject, "count": count}


@app.get("/api/usage/weekly")
async def api_usage_weekly():
    """Weekly memory report data — atoms saved, recalls, topics, new topics this week."""
    db = _get_db()
    cfg = _get_cfg()
    records = load_usage(cfg)
    today = datetime.now(timezone.utc).date()
    week_ago = date.fromordinal(today.toordinal() - 6)
    week_ago_iso = week_ago.isoformat()

    # Recalls this week (from usage.jsonl)
    recalls_this_week = sum(
        1 for r in records
        if r.get("ts", "")[:10] >= week_ago_iso and r.get("type") != "grace_day_used"
    )

    # Atoms: split into this week vs older
    all_atoms = [a for a in db.all() if not a.is_superseded]
    this_week_atoms = [
        a for a in all_atoms
        if a.ingested_at and a.ingested_at.date() >= week_ago
    ]
    older_atoms = [
        a for a in all_atoms
        if not a.ingested_at or a.ingested_at.date() < week_ago
    ]

    older_subjects = {(a.subject or "").lower().strip() for a in older_atoms if a.subject}
    this_week_subjects = list(dict.fromkeys(
        a.subject for a in this_week_atoms if a.subject
    ))
    new_topics = [s for s in this_week_subjects if s.lower().strip() not in older_subjects]

    # Top topic: most frequent subject this week
    from collections import Counter
    subject_counts = Counter(a.subject for a in this_week_atoms if a.subject)
    top_topic = subject_counts.most_common(1)[0][0] if subject_counts else None

    streak, _ = compute_streak(records)

    return {
        "atoms_this_week": len(this_week_atoms),
        "recalls_this_week": recalls_this_week,
        "topics_this_week": len(set(this_week_subjects)),
        "new_topics": new_topics[:3],
        "top_topic": top_topic,
        "streak": streak,
    }
