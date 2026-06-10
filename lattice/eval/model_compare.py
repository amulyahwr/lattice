"""
Compare ingest classification quality across models on preference-failing questions.

Usage:
    uv run python -m lattice.eval.model_compare

Runs ingest on 2 preference-failing p34 questions (15 sessions each, parallelized)
using each model, then prints kind distribution and sample preference/habit atoms.

Requires .env.eval with LLM_API_KEY and LLM_BASE_URL set.
Models tested: gpt-4o-mini, anthropic/claude-3-5-haiku, qwen/qwen3.6-plus
"""
from __future__ import annotations

import json
import os
import random
import tempfile
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env.eval")

from lattice.config import Config
from lattice.db import LatticeDB
from lattice.eval.session_formatter import format_session
from lattice.ingest import ingest

# ── config ─────────────────────────────────────────────────────────────────────

_QUESTION_IDS = [
    "06f04340",  # "What should I serve for dinner with my homegrown ingredients?"
    "d24813b1",  # "Any tips on what to bake for a small gathering?"
]

_MODELS = [
    "openai/gpt-4o-mini",
    "anthropic/claude-3-5-haiku",
    "qwen/qwen3.6-plus",
]

_MAX_SESSIONS = 15       # answer sessions first, then random distractors up to this cap
_WORKERS = 3             # parallel session ingest workers per model (keep under OpenRouter rate limits)
_DATA_FILE = Path(__file__).parent / "data" / "longmemeval_s_cleaned.json"
_TARGET_KINDS = {"preference", "habit"}
_BAD_KINDS = {
    "advice", "tip", "suggestion", "recipe", "benefit", "experiment",
    "request", "interest", "lesson", "query", "challenge", "knowledge",
    "consider", "note",
}


def _load_question(data: list[dict], question_id: str) -> dict | None:
    for q in data:
        if q["question_id"] == question_id:
            return q
    return None


def _select_sessions(question: dict, max_sessions: int, seed: int = 42) -> list[tuple]:
    """Return up to max_sessions (session, session_id, observed_at) tuples.
    Answer sessions are always included first; remainder is random distractors.
    """
    sessions = question.get("haystack_sessions", [])
    session_ids = question.get("haystack_session_ids", [f"s{i}" for i in range(len(sessions))])
    dates = question.get("haystack_dates", [])
    answer_ids = set(question.get("answer_session_ids") or [])
    question_date = question.get("question_date", "")

    all_triples = [
        (s, sid, dates[i] if i < len(dates) else question_date)
        for i, (s, sid) in enumerate(zip(sessions, session_ids))
    ]

    answer_triples = [t for t in all_triples if t[1] in answer_ids]
    distractor_triples = [t for t in all_triples if t[1] not in answer_ids]

    rng = random.Random(seed)
    rng.shuffle(distractor_triples)
    remaining = max(0, max_sessions - len(answer_triples))
    return answer_triples + distractor_triples[:remaining]


def _ingest_one(session_triple: tuple, cfg: Config, db: LatticeDB) -> None:
    session, session_id, observed_at = session_triple
    formatted = format_session(session, session_id, observed_at)
    if not formatted.strip():
        return
    try:
        ingest(
            formatted,
            metadata={
                "source": "conversation",
                "source_id": session_id,
                "session_id": session_id,
                "observed_at": observed_at,
            },
            db=db,
            cfg=cfg,
        )
    except Exception:
        pass  # skip bad sessions; parse failures already logged as warnings


def _run_ingest(question: dict, model: str, tmp_dir: Path) -> list:
    cfg = Config(
        lattice_dir=tmp_dir,
        llm_provider="openai",
        llm_model=model,
        llm_base_url=os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_api_key=os.environ.get("LLM_API_KEY", ""),
        ingest_model=model,
        ingest_workers=1,  # parallelism handled at session level below
    )
    db = LatticeDB(lattice_dir=tmp_dir)
    triples = _select_sessions(question, _MAX_SESSIONS)
    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = [pool.submit(_ingest_one, t, cfg, db) for t in triples]
        for f in as_completed(futures):
            f.result()  # surface exceptions

    return list(db._atom_cache.values())


def _report(atoms: list, sessions_used: int) -> dict:
    kinds = Counter(a.kind for a in atoms)
    bad = sum(kinds[k] for k in _BAD_KINDS if k in kinds)
    target = sum(kinds[k] for k in _TARGET_KINDS if k in kinds)
    total = len(atoms)
    return {
        "total_atoms": total,
        "sessions_used": sessions_used,
        "kinds": dict(kinds.most_common()),
        "target_pct": round(100 * target / total, 1) if total else 0,
        "bad_kinds_count": bad,
        "sample": [
            {"kind": a.kind, "subject": a.subject, "content": a.content[:110]}
            for a in atoms if a.kind in _TARGET_KINDS
        ][:6],
    }


def main():
    print("Loading dataset...")
    with open(_DATA_FILE) as f:
        data = json.load(f)

    questions = [_load_question(data, qid) for qid in _QUESTION_IDS]
    questions = [q for q in questions if q]

    for question in questions:
        print(f"\n{'='*72}")
        print(f"Q: {question['question']}")
        print(f"{'='*72}")

        triples = _select_sessions(question, _MAX_SESSIONS)
        print(f"Sessions: {len(triples)} ({len([t for t in triples if t[1] in set(question.get('answer_session_ids') or [])])} answer + distractors)")

        for model in _MODELS:
            print(f"\n  [{model}]")
            with tempfile.TemporaryDirectory() as tmp_dir:
                try:
                    atoms = _run_ingest(question, model, Path(tmp_dir))
                    result = _report(atoms, len(triples))
                except Exception as e:
                    import traceback
                    print(f"  ERROR: {e}")
                    traceback.print_exc()
                    continue

            total = result["total_atoms"]
            target_pct = result["target_pct"]
            bad = result["bad_kinds_count"]
            top_kinds = sorted(result["kinds"].items(), key=lambda x: x[1], reverse=True)[:8]
            kind_str = "  ".join(f"{k}={v}" for k, v in top_kinds)

            print(f"  atoms={total}  preference+habit={target_pct}%  rogue={bad}")
            print(f"  kinds: {kind_str}")
            if result["sample"]:
                print("  sample preference/habit atoms:")
                for s in result["sample"]:
                    print(f"    [{s['kind']}] {s['subject']!r}: {s['content']}")


if __name__ == "__main__":
    main()
