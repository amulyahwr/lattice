#!/usr/bin/env python3
"""End-to-end product smoke test.

Ingests a fixed 3-session personal memory corpus with real LLM calls, then
runs 12 queries covering all category types from the LongMemEval yardstick.
Each answer is judged by a lightweight LLM call.

Run:
    uv run python scripts/e2e.py

Required env vars:
    LLM_PROVIDER   (default: ollama)
    LLM_MODEL      e.g. qwen3:4b, gpt-4o
    LATTICE_DIR    (default: ~/.lattice-e2e — isolated from your main lattice)

Optional:
    LLM_API_KEY    (required for non-ollama providers)
    INGEST_MODEL   override for ingest stage
    SYNTHESIS_MODEL override for synthesis stage
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import textwrap
import tempfile
from datetime import date, timedelta
from pathlib import Path

# Resolve project root and add to path so we can run from any directory.
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lattice.db import LatticeDB
from lattice.ingest import ingest
from lattice.selection import select
from lattice.synthesis import synthesize
from lattice.llm import complete


# ── corpus ───────────────────────────────────────────────────────────────────
# Three sessions recorded at different times. Each session is a block of text
# that a real user might drop into the inbox.

_TODAY = date.today()
_T = lambda days_ago: (_TODAY - timedelta(days=days_ago)).isoformat()  # noqa: E731

SESSIONS = [
    {
        "id": "session-preferences",
        "observed_at": _T(60),
        "text": textwrap.dedent(f"""\
            User: I've been drinking dark roast coffee every morning for years.
            User: My favourite editor is Neovim. I use it for everything.
            User: I'm vegetarian. I've been vegetarian since 2019.
            User: I have a peanut allergy — it's severe, I carry an EpiPen.
            User: I prefer working in the mornings. I'm not a night person.
        """),
        "metadata": {"source": "chat", "date": f"{_T(60)} 09:00"},
    },
    {
        "id": "session-fitness",
        "observed_at": _T(30),
        "text": textwrap.dedent(f"""\
            User: I started training for a half-marathon last month.
            User: My current weekly mileage is about 30 km.
            User: I run three times a week — Tuesday, Thursday, Saturday.
            User: I signed up for the city half-marathon on {_T(0)}.
            User: My target finish time is under 2 hours.
        """),
        "metadata": {"source": "chat", "date": f"{_T(30)} 08:30"},
    },
    {
        "id": "session-update",
        "observed_at": _T(5),
        "text": textwrap.dedent(f"""\
            User: I switched from Neovim to VS Code last week. I'm giving it a fair try.
            User: I've bumped my weekly mileage up to 40 km to prepare for race day.
            User: I've been doing my long runs on Sunday now instead of Saturday.
        """),
        "metadata": {"source": "chat", "date": f"{_T(5)} 10:00"},
    },
]

# ── queries ───────────────────────────────────────────────────────────────────
# 12 queries spanning all LME-yardstick categories. Each has:
#   - question: what the user asks
#   - must_contain: keywords the correct answer must mention (case-insensitive)
#   - must_not_contain: words that signal a wrong answer
#   - category: for reporting

QUERIES = [
    # single-session-user
    {
        "question": "What coffee do I drink?",
        "must_contain": ["dark roast"],
        "must_not_contain": [],
        "category": "single-session-user",
    },
    {
        "question": "Do I have any food allergies?",
        "must_contain": ["peanut"],
        "must_not_contain": [],
        "category": "single-session-user",
    },
    {
        "question": "What diet do I follow?",
        "must_contain": ["vegetarian"],
        "must_not_contain": [],
        "category": "single-session-user",
    },
    # single-session-preference
    {
        "question": "Am I a morning person or a night person?",
        "must_contain": ["morning"],
        "must_not_contain": ["night person"],
        "category": "single-session-preference",
    },
    {
        "question": "What is my target finish time for the half-marathon?",
        "must_contain": ["2 hour", "two hour", "120"],
        "must_not_contain": [],
        "category": "single-session-preference",
    },
    # knowledge-update (editor changed)
    {
        "question": "What code editor do I currently use?",
        "must_contain": ["vs code", "vscode"],
        "must_not_contain": [],
        "category": "knowledge-update",
    },
    # temporal-reasoning
    {
        "question": "When did I become vegetarian?",
        "must_contain": ["2019"],
        "must_not_contain": [],
        "category": "temporal-reasoning",
    },
    {
        "question": "When is my half-marathon race?",
        "must_contain": [_T(0)[:7]],  # at least the year-month
        "must_not_contain": [],
        "category": "temporal-reasoning",
    },
    # multi-session (combines data across sessions)
    {
        "question": "How has my weekly running mileage changed over time?",
        "must_contain": ["30", "40"],
        "must_not_contain": [],
        "category": "multi-session",
    },
    {
        "question": "Which days do I do my long runs now?",
        "must_contain": ["sunday"],
        "must_not_contain": [],
        "category": "multi-session",
    },
    # single-session-assistant (recommendation)
    {
        "question": "Given my allergy, what snacks should I avoid?",
        "must_contain": ["peanut"],
        "must_not_contain": [],
        "category": "single-session-assistant",
    },
    # abstention (not in corpus)
    {
        "question": "What programming languages do I use?",
        "must_contain": [],
        "must_not_contain": [],
        "category": "abstention",
        "expect_no_info": True,
    },
]


# ── judge ─────────────────────────────────────────────────────────────────────

def _judge(question: str, answer: str, must_contain: list[str],
           must_not_contain: list[str], expect_no_info: bool) -> tuple[bool, str]:
    """Keyword-first judge: fast, no extra LLM call for most questions.

    Falls back to LLM only when keyword check is ambiguous.
    """
    answer_lower = answer.lower()

    if expect_no_info:
        no_info_signals = ["no information", "no relevant", "not found", "don't have",
                           "no record", "couldn't find", "i don't know"]
        passed = any(s in answer_lower for s in no_info_signals)
        reason = "correctly signals no info" if passed else "expected no-info signal but got an answer"
        return passed, reason

    for kw in must_not_contain:
        if kw.lower() in answer_lower:
            return False, f"contains forbidden term '{kw}'"

    if must_contain:
        matched = [kw for kw in must_contain if kw.lower() in answer_lower]
        if matched:
            return True, f"contains '{matched[0]}'"
        # keyword miss → ask LLM to judge
        prompt = (
            f"Question: {question}\n"
            f"Answer: {answer}\n\n"
            f"Does this answer correctly address the question? "
            f"Reply with a single JSON object: {{\"pass\": true/false, \"reason\": \"...\"}}"
        )
        try:
            raw = complete([{"role": "user", "content": prompt}])
            obj = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
            return bool(obj.get("pass")), str(obj.get("reason", "llm judged"))
        except Exception as exc:
            return False, f"keyword miss; llm judge failed: {exc}"

    return True, "no keyword constraints"


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    lattice_dir = os.environ.get("LATTICE_DIR")
    _tmp_dir = None
    if not lattice_dir:
        _tmp_dir = tempfile.mkdtemp(prefix="lattice-e2e-")
        lattice_dir = _tmp_dir
        print(f"LATTICE_DIR not set — using temp dir: {lattice_dir}")

    print(f"\n=== lattice e2e smoke test ===")
    print(f"provider : {os.environ.get('LLM_PROVIDER', 'ollama')}")
    print(f"model    : {os.environ.get('LLM_MODEL', '(not set)')}")
    print(f"dir      : {lattice_dir}\n")

    db = LatticeDB(lattice_dir=Path(lattice_dir))

    # ── ingest ────────────────────────────────────────────────────────────────
    print("── ingest ───────────────────────────────────────")
    total_atoms = 0
    for s in SESSIONS:
        result = ingest(s["text"], metadata=s["metadata"], db=db)
        created = result["atoms_created"]
        total_atoms += created
        print(f"  {s['id']}: {created} atoms created")
    print(f"  total: {total_atoms} atoms\n")

    if total_atoms == 0:
        print("ERROR: ingest produced 0 atoms — check LLM config")
        sys.exit(1)

    # ── query + judge ─────────────────────────────────────────────────────────
    print("── queries ──────────────────────────────────────")
    results: list[dict] = []
    by_category: dict[str, list[bool]] = {}

    for q in QUERIES:
        atoms = select(q["question"], db=db)
        synth = synthesize(q["question"], atoms)
        answer = synth.answer

        passed, reason = _judge(
            question=q["question"],
            answer=answer,
            must_contain=q.get("must_contain", []),
            must_not_contain=q.get("must_not_contain", []),
            expect_no_info=q.get("expect_no_info", False),
        )

        mark = "✓" if passed else "✗"
        cat = q["category"]
        by_category.setdefault(cat, []).append(passed)
        results.append({"question": q["question"], "category": cat,
                        "passed": passed, "reason": reason,
                        "atoms_retrieved": len(atoms), "answer": answer})

        short_answer = answer[:120].replace("\n", " ")
        print(f"  {mark} [{cat}] {q['question']}")
        print(f"      atoms={len(atoms)}  reason={reason}")
        print(f"      answer: {short_answer}...")
        print()

    # ── summary ───────────────────────────────────────────────────────────────
    print("── summary ──────────────────────────────────────")
    total = len(results)
    passed_total = sum(r["passed"] for r in results)
    print(f"  overall: {passed_total}/{total} ({100*passed_total//total}%)")
    for cat, bools in sorted(by_category.items()):
        n = len(bools)
        p = sum(bools)
        print(f"  {cat}: {p}/{n}")

    print()
    if _tmp_dir:
        shutil.rmtree(_tmp_dir, ignore_errors=True)

    sys.exit(0 if passed_total == total else 1)


if __name__ == "__main__":
    main()
