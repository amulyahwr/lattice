from __future__ import annotations

import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Optional

from pydantic import BaseModel

from lattice.db import LatticeDB
from lattice.llm import complete
from lattice.models import Atom
from lattice.parsers import Segment, infer_source_type, parse


class _ExtractedAtom(BaseModel):
    subject: str
    kind: str
    source: str
    content: str
    valid_from: Optional[str] = None
    valid_until: Optional[str] = None


class _AtomList(BaseModel):
    atoms: list[_ExtractedAtom]


class _SupersessionResult(BaseModel):
    superseded_atom_id: str | None


_SYSTEM = """\
You are a knowledge extraction agent. Read a piece of text and extract all durable facts, \
decisions, constraints, goals, events, and preferences into discrete atoms.

Rules for each atom:
  - content    : a single self-contained statement. Do NOT reference "the text" or "the document" — \
write as a standalone fact a reader could understand without the original source.
  - kind       : a short descriptive label, e.g. fact, decision, constraint, goal, event, preference, belief
  - subject    : short canonical noun phrase identifying what the atom is about, \
e.g. "Project Alpha deadline", "auth module", "database schema", "deployment process", "API rate limit"
  - source     : where this came from — use the value from the caller's metadata if provided, \
otherwise infer: "document" for prose/notes/docs, "code" for code snippets, "conversation" for chat logs

Subject naming rules:
  - Use the most general term that still uniquely identifies the topic.
  - Use CONSISTENT subject phrasing across atoms — e.g. always "auth module" not sometimes "authentication" \
or "auth system". Consistent subjects enable supersession when the same fact is updated later.
  - valid_from / valid_until: only set if the text explicitly implies temporal bounds (e.g. "valid until end of Q2", \
"starting next Monday"). Otherwise null.
  - Resolve relative dates (e.g. "last Tuesday", "next month") to ISO 8601 (YYYY-MM-DD) using today's date.
  - Do NOT extract generic advice or universally-applicable facts that apply to everyone.

Return a JSON object with an `atoms` key containing an array of atom objects. \
Each atom must have exactly these keys: subject, kind, source, content, valid_from, valid_until.
"""

_CHAT_ADDENDUM = """\

Source-specific rules for chat/conversation (User: / Assistant: / System: turns):
  - USER turns are the primary source — extract personal facts, events, decisions, and preferences \
from them. These are things the specific person did, owns, experienced, or prefers.
  - ASSISTANT turns: extract ONLY when a specific proper noun is named for this user. \
The item must be a brand, product, venue, person, or title with a real name — not a generic category or technique.
    ✓ EXTRACT as kind=recommendation: "I recommend Notion for notes", "Try the Honda Civic", \
"Alberta Street Pub is great for you", "Read 'On The Line' by Joseph Piqué" \
→ subject = "<ProperName> recommendation"
    ✗ DO NOT EXTRACT: generic techniques ("use puns", "try self-deprecation"), generic categories \
("joint supplements", "dental chews", "healthy treats"), generic advice \
("maintain a healthy weight", "drink more water", "exercise regularly"), \
tips that apply to anyone regardless of who they are.
    (b) A statement that directly references the user's own situation or preference (e.g. \
"Since you prefer X…", "Given that you bought Y…") → extract normally with the appropriate kind.
  - If in doubt whether something is a proper noun recommendation vs generic advice — DO NOT extract it.
  - Personal events in USER turns (e.g. "I just bought a car", "I downloaded Ibotta", \
"I attended a class") must be captured as kind="event" atoms with the subject being the event \
(e.g. "Ibotta adoption", "car purchase", "baking class attendance").
  - Preserve explicit dates verbatim in atom content (e.g. "on January 10th", "on March 3rd"). \
Do not drop them. When the user says "today", "this morning", or "tonight", replace with the ISO \
date provided in "Today's date:" at the top of this prompt.
"""

_MARKDOWN_ADDENDUM = """\

Source-specific rules for markdown documents:
  - Use the nearest heading as context for the subject — prefer scoped subjects like \
"Auth module rate limit" over bare "rate limit".
  - Extract decisions and constraints from bullet lists and callout blocks.
"""

_CODE_ADDENDUM = """\

Source-specific rules for code:
  - Focus on interfaces, contracts, and public API shapes — not implementation details.
  - Extract constraints, invariants, and documented behaviour (e.g. "function X requires Y to be non-null").
  - Skip boilerplate, imports, and auto-generated code.
"""


def _source_addendum(source_type: str) -> str:
    if source_type == "chat":
        return _CHAT_ADDENDUM
    if source_type == "markdown":
        return _MARKDOWN_ADDENDUM
    if source_type == "code":
        return _CODE_ADDENDUM
    return ""

_SUPERSESSION_SYSTEM = """\
You are deciding whether a new fact supersedes an existing fact about the same subject. \
Supersession means the new fact contradicts or replaces the old one — not merely adds to it.
Return a JSON object: {"superseded_atom_id": "<atom_id>"} if superseded, or {"superseded_atom_id": null} if not.
"""

_SUPERSESSION_MULTI_SYSTEM = """\
You are deciding whether a new fact supersedes any of the existing facts listed below. \
Supersession means the new fact contradicts or replaces an old one — not merely adds to it.
Return a JSON object: {"superseded_atom_id": "<atom_id>"} for the one superseded fact, \
or {"superseded_atom_id": null} if none are superseded.
"""


# ── date resolution ───────────────────────────────────────────────────────────

_RELATIVE_PATTERNS: list[tuple[re.Pattern, Any]] = [
    (re.compile(r'\b(\d+)\s+days?\s+ago\b', re.IGNORECASE),
     lambda m, ref: (ref - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")),
    (re.compile(r'\b(\d+)\s+weeks?\s+ago\b', re.IGNORECASE),
     lambda m, ref: (ref - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d")),
    (re.compile(r'\b(\d+)\s+months?\s+ago\b', re.IGNORECASE),
     lambda m, ref: (ref - timedelta(days=int(m.group(1)) * 30)).strftime("%Y-%m-%d")),
    (re.compile(r'\blast\s+year\b', re.IGNORECASE),
     lambda _, ref: str(ref.year - 1)),
    (re.compile(r'\blast\s+week\b', re.IGNORECASE),
     lambda _, ref: (ref - timedelta(weeks=1)).strftime("%Y-%m-%d")),
    (re.compile(r'\blast\s+month\b', re.IGNORECASE),
     lambda _, ref: (ref - timedelta(days=30)).strftime("%Y-%m-%d")),
    (re.compile(r'\byesterday\b', re.IGNORECASE),
     lambda _, ref: (ref - timedelta(days=1)).strftime("%Y-%m-%d")),
    (re.compile(r'\btoday\b', re.IGNORECASE),
     lambda _, ref: ref.strftime("%Y-%m-%d")),
]

_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_WEEKDAY_PATTERN = re.compile(
    r'\blast\s+(' + '|'.join(_WEEKDAY_NAMES) + r')\b', re.IGNORECASE
)


def _resolve_dates(content: str, ref: datetime) -> str:
    """Replace relative date expressions in atom content with absolute ISO dates."""
    for pattern, resolver in _RELATIVE_PATTERNS:
        content = pattern.sub(lambda m, _r=ref, _res=resolver: _res(m, _r), content)

    def _resolve_weekday(m: re.Match) -> str:
        day_name = m.group(1).lower()
        target_dow = _WEEKDAY_NAMES.index(day_name)
        days_back = (ref.weekday() - target_dow) % 7
        if days_back == 0:
            days_back = 7
        return (ref - timedelta(days=days_back)).strftime("%Y-%m-%d")

    content = _WEEKDAY_PATTERN.sub(_resolve_weekday, content)
    return content


# ── helpers ───────────────────────────────────────────────────────────────────

def _today() -> datetime:
    return datetime.now(tz=timezone.utc)


def _parse_datetime(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    text = str(val)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            d = date.fromisoformat(text[:10])
            return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        except ValueError:
            pass

    for fmt in ("%Y/%m/%d (%a) %H:%M", "%Y/%m/%d %H:%M", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _normalized_content(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _segments_for_source(source: str, metadata: dict) -> list[Segment]:
    source_type = infer_source_type(source, metadata)
    return parse(source, source_type)


def _extract_atoms(segment: _Segment, metadata: dict, ref: datetime) -> list[dict]:
    text = segment.text
    if segment.context:
        text = f"Context: {segment.context}\n\n{text}"
    system = _SYSTEM + _source_addendum(segment.source_type)
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": f"Today's date: {ref.date().isoformat()}\n\n---\n\n{text}",
        },
    ]
    raw = complete(messages, text_format=_AtomList)
    atoms_data: list[dict] = json.loads(raw)["atoms"]

    source_override = metadata.get("source")
    for a in atoms_data:
        if source_override:
            a["source"] = source_override
        a["content"] = _resolve_dates(a["content"], ref)
        a["metadata"] = metadata
        a["segment_id"] = segment.segment_id
        a["source_type"] = segment.source_type
        a["source_span"] = {"start": segment.start, "end": segment.end}
    return atoms_data


def _detect_supersession(db: LatticeDB, new_atom: Atom) -> str | None:
    # Fast path: subject registry
    existing_id = db.lookup_subject(new_atom.subject)
    if existing_id:
        try:
            existing = db.read(existing_id)
            if existing.is_superseded:
                return None
        except Exception:
            return None

        messages = [
            {"role": "system", "content": _SUPERSESSION_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"New fact: {new_atom.content}\n\n"
                    f"Existing fact [{existing_id}]: {existing.content}"
                ),
            },
        ]
        raw = complete(messages, text_format=_SupersessionResult)
        superseded_id = json.loads(raw).get("superseded_atom_id")
        if not superseded_id:
            return None
        return existing_id if superseded_id == existing_id else None

    # Slow path: scan by subject (handles hand-edited atoms)
    existing = [a for a in db.by_subject(new_atom.subject) if not a.is_superseded]
    if not existing:
        # Fuzzy path: find semantically similar subjects via token overlap
        threshold = int(os.environ.get("LATTICE_SUBJECT_FUZZY_THRESHOLD", "80"))
        fuzzy_ids = db.fuzzy_subject_candidates(new_atom.subject, threshold)
        fuzzy_candidates = []
        for aid in fuzzy_ids:
            try:
                a = db.read(aid)
                if not a.is_superseded:
                    fuzzy_candidates.append(a)
            except Exception:
                pass
        if not fuzzy_candidates:
            return None
        existing = fuzzy_candidates

    candidates_text = "\n".join(f"[{a.atom_id}] {a.content}" for a in existing)
    messages = [
        {"role": "system", "content": _SUPERSESSION_MULTI_SYSTEM},
        {
            "role": "user",
            "content": (
                f"New fact: {new_atom.content}\n\n"
                f"Existing facts about '{new_atom.subject}':\n{candidates_text}"
            ),
        },
    ]
    raw = complete(messages, text_format=_SupersessionResult)
    superseded_id = json.loads(raw).get("superseded_atom_id")
    if not superseded_id:
        return None
    valid_ids = {a.atom_id for a in existing}
    return superseded_id if superseded_id in valid_ids else None


def ingest(source: str, metadata: dict | None = None, db: LatticeDB | None = None) -> dict:
    if db is None:
        db = LatticeDB()
    metadata = metadata or {}
    source_id = str(metadata.get("source_id") or uuid.uuid4())
    observed_at = _parse_datetime(
        metadata.get("observed_at") or metadata.get("date") or metadata.get("timestamp")
    )
    ref = observed_at or _today()

    segments = _segments_for_source(source, metadata)
    workers = max(1, int(os.environ.get("LATTICE_INGEST_WORKERS", "1")))
    if workers == 1 or len(segments) == 1:
        nested_atoms = [_extract_atoms(segment, metadata, ref) for segment in segments]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            nested_atoms = list(pool.map(lambda s: _extract_atoms(s, metadata, ref), segments))
    atoms_data = [a for atoms in nested_atoms for a in atoms]
    created_ids: list[str] = []
    duplicate_ids: list[str] = []

    for data in atoms_data:
        content = data["content"]
        content_hash = _hash_text(content)
        normalized_hash = _hash_text(_normalized_content(content))
        duplicate = db.find_by_normalized_hash(normalized_hash)
        if duplicate is not None:
            duplicate_ids.append(duplicate.atom_id)
            continue

        atom = Atom(
            kind=data.get("kind", "fact"),
            source=data.get("source", "document"),
            subject=data["subject"],
            content=content,
            valid_from=_parse_date(data.get("valid_from")),
            valid_until=_parse_date(data.get("valid_until")),
            ingested_at=ref,
            observed_at=observed_at,
            source_id=source_id,
            source_title=metadata.get("title") or metadata.get("source_title"),
            session_id=metadata.get("session_id"),
            segment_id=data.get("segment_id"),
            source_type=data.get("source_type"),
            source_span=data.get("source_span"),
            content_hash=content_hash,
            normalized_content_hash=normalized_hash,
            metadata=data.get("metadata", {}),
        )

        old_id = _detect_supersession(db, atom)
        if old_id:
            db.supersede(old_id, atom)
        else:
            db.write(atom)

        if atom.subject:
            db.register_subject(atom.subject, atom.atom_id)

        created_ids.append(atom.atom_id)

    return {
        "atoms_created": len(created_ids),
        "atom_ids": created_ids,
        "duplicates_skipped": len(duplicate_ids),
        "duplicate_atom_ids": duplicate_ids,
        "source_id": source_id,
        "segments_processed": len(segments),
    }
