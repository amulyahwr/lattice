"""Mock web server for UI development — no LLM, no GPU required.

Usage:
    uv run python -m lattice.web.mock

Serves the same static files as the real app but stubs all API endpoints
with hardcoded data so you can iterate on HTML/CSS/JS without a daemon.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Lattice (mock)")
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# ── fake data ────────────────────────────────────────────────────────────────

_FAKE_ATOMS = [
    {"atom_id": "a1", "subject": "Prefers dark roast coffee", "kind": "preference",
     "observed_at": "2026-05-30T08:00:00Z", "source_id": "a1",
     "source_title": "morning-notes.md",
     "content": "I always start the day with a dark roast. Light roast feels watery to me."},
    {"atom_id": "a2", "subject": "Uses Neovim as primary editor", "kind": "preference",
     "observed_at": "2026-05-29T14:30:00Z", "source_id": "a2",
     "source_title": "dev-setup.md",
     "content": "Switched from VS Code to Neovim six months ago. Modal editing changed how I think about text."},
    {"atom_id": "a3", "subject": "Running a half-marathon in June 2026", "kind": "goal",
     "observed_at": "2026-05-28T09:15:00Z", "source_id": "a3",
     "source_title": "training-log.md",
     "content": "Signed up for the SF half-marathon on June 14. Currently at 18km long runs."},
    {"atom_id": "a4", "subject": "Team standup is at 10am every weekday", "kind": "fact",
     "observed_at": "2026-05-27T10:00:00Z", "source_id": "a4",
     "source_title": "work-notes.md",
     "content": "Daily standup with the team at 10am PST. Async on Fridays."},
    {"atom_id": "a5", "subject": "Allergic to shellfish", "kind": "fact",
     "observed_at": "2026-05-26T18:00:00Z", "source_id": "a5",
     "source_title": "health.md",
     "content": "Shellfish allergy — shrimp, lobster, crab all cause hives. Carry antihistamines."},
]

_FAKE_ANSWER = (
    "Based on your memories, you prefer dark roast coffee [src:a1] and use Neovim "
    "as your primary editor [src:a2]. You're also training for a half-marathon in June 2026 [src:a3]."
)

_FAKE_TOKENS = _FAKE_ANSWER.split(" ")


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(_STATIC / "index.html")


@app.get("/health")
async def health():
    return {"ok": True}


class QueryRequest(BaseModel):
    question: str


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str
    reason: str | None = None


@app.post("/api/query")
async def api_query(req: QueryRequest) -> StreamingResponse:
    def _generate():
        # emit atoms first (simulates select() completing)
        time.sleep(0.4)
        yield f'data: {json.dumps({"type": "atoms", "atoms": _FAKE_ATOMS[:3]})}\n\n'

        # stream tokens one word at a time
        assembled = ""
        for i, token in enumerate(_FAKE_TOKENS):
            time.sleep(0.06)
            word = token if i == 0 else " " + token
            assembled += word
            yield f'data: {json.dumps({"type": "token", "text": word})}\n\n'

        # emit citations_applied with the full answer
        time.sleep(0.1)
        yield f'data: {json.dumps({"type": "citations_applied", "answer": _FAKE_ANSWER})}\n\n'

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/feedback")
async def api_feedback(req: FeedbackRequest):
    print(f"[mock] feedback: rating={req.rating!r} reason={req.reason!r} question={req.question!r}")
    return {"ok": True}


@app.get("/api/atoms/recent")
async def api_atoms_recent(limit: int = 20):
    return _FAKE_ATOMS[:limit]


# ── entrypoint ───────────────────────────────────────────────────────────────

def main():
    uvicorn.run("lattice.web.mock:app", host="127.0.0.1", port=7337, reload=True)


if __name__ == "__main__":
    main()
