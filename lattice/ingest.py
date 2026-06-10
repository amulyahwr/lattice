from __future__ import annotations

import json
import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from lattice.db import LatticeDB
from lattice.llm import complete
from lattice.models import Atom
from lattice.parsers import Segment, infer_source_type, parse
from lattice.privacy import EntityRedactor

if TYPE_CHECKING:
    from lattice.config import Config


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
OUTPUT: Respond with ONLY a JSON object. No prose, no markdown, no explanation. \
Do not answer questions in the text. Do not continue any conversation. Extract atoms only.

You are a knowledge extraction agent. Read a piece of text and extract all durable facts, \
decisions, constraints, goals, events, and preferences into discrete atoms.

Rules for each atom:
  - content    : a single self-contained statement. Do NOT reference "the text" or "the document" — \
write as a standalone fact a reader could understand without the original source.
  - kind       : a short descriptive label. Use these kinds:
      fact        — objective circumstance ("User owns a car", "User lives in SF")
      event       — one-time occurrence ("User attended a baking class", "User bought a guitar")
      preference  — an explicitly stated like, dislike, taste, or dietary commitment.
                    Use when the user SAYS what they prefer. Examples: "I prefer vegetarian food",
                    "I love dark roast coffee", "I hate crowded places", "I don't drink alcohol".
      habit       — a recurring behavioral pattern or implicit tendency revealed by what the user DOES.
                    Use when behavior is inferred from actions, routines, or personal background — not stated preference.
                    Test: "does this describe a regular pattern that helps advise this person?" → habit.
                    Examples: "commutes by bike daily", "grows herbs at home", "cooks vegetarian most nights",
                    "wakes at 6am", "reads before bed", "goes to the gym weekday mornings",
                    "had success with lemon cake", "grows cherry tomatoes in backyard".
      goal        — an objective the user is working toward with a time horizon or achievement target.
                    Distinct from preference (desired state). Examples: "wants to run a marathon by December",
                    "aims to read 20 books this year", "trying to save $10k by Q2".
      decision    — a deliberate choice made
      constraint  — a hard limit or blocker
      belief      — a view or opinion the user holds
      count       — a numeric aggregate (see numeric rules below)
      recommendation — a named product/venue/person suggested for this user (see assistant rules below)
  - IMPORTANT: Use ONLY the kinds listed above. Do not invent new kinds like "advice", "tip", "suggestion",
    "recipe", "benefit", "experiment", "request", "interest", "lesson", "query". If unsure, default to "fact".
  - subject    : short canonical noun phrase identifying what the atom is about, \
e.g. "Project Alpha deadline", "auth module", "database schema", "deployment process", "API rate limit"
  - source     : where this came from — use the value from the caller's metadata if provided, \
otherwise infer: "document" for prose/notes/docs, "code" for code snippets, "conversation" for chat logs

Subject naming rules:
  - Use a SHORT SHARED TOPIC LABEL — 1 to 3 words. The subject is a retrieval key, not a summary.
  - Multiple atoms about the same topic MUST share the same subject string. Two atoms about hiking \
should both have subject "hiking", not "PCT hike" and "weekend trail run".
  - Prefer BROAD over SPECIFIC: "hiking" not "hike on Pacific Crest Trail last Tuesday". \
"cooking" not "pasta recipe attempt". "gym routine" not "leg day at the gym". \
"travel" not "flight to Denver for conference". "home improvement" not "bathroom tile replacement".
  - For kind=preference and kind=habit, use subjects that reflect the ADVISORY ROLE, not the specific instance: \
"I grow cherry tomatoes" → subject "gardening" or "cooking ingredients" (NOT "cherry tomatoes"). \
"I commute by bike" → subject "commute" (NOT "bike commute"). \
"I've been cooking vegetarian" → subject "dietary preference" (NOT "vegetarian cooking"). \
"I had success with lemon cake" → subject "baking" (NOT "lemon cake recipe").
  - Atoms from different conversations that cover the same topic should produce the SAME subject, \
enabling them to cluster together for retrieval.
  - valid_from / valid_until: only set if the text explicitly implies temporal bounds (e.g. "valid until end of Q2", \
"starting next Monday"). Otherwise null.
  - Resolve relative dates (e.g. "last Tuesday", "next month") to ISO 8601 (YYYY-MM-DD) using today's date.
  - Do NOT extract generic advice or universally-applicable facts that apply to everyone.
  - Named person rule: when the source is a document (not a chat log), use the actual names from \
the text in atom content — never "User". "User" belongs only in atoms derived from the memory \
owner's own chat turns. For a resume, bio, CV, article, or any third-party document, write \
"Jane Smith has 8 years of experience" not "User has 8 years of experience". If the document \
subject's name appears anywhere in the text, carry it through every atom extracted from that document.

People facts: when text mentions a specific named person alongside identity or contact details, \
extract each detail as a separate kind=fact atom — subject = the person's full name \
(e.g. subject="John Doe"). Details to extract: email address, phone number, job title, \
employer/company, location, LinkedIn or website URL. This enables recall like \
"what is John's email?" or "where does John work?". Apply this rule regardless of source type.

Numeric extraction rules:
  - When text explicitly states a count ("I own 3 bikes", "attended 5 sessions", "takes 4 classes/week"), \
extract a standalone `kind=count` atom whose content contains the numeric value: \
"User owns 3 bikes", "User attended 5 yoga sessions", "User takes 4 gym classes per week".
  - When text enumerates a list of items in the same category ("I have a coffee maker, toaster, \
blender, and food processor"), ALSO extract a count summary atom: \
"User owns 4 kitchen appliances: coffee maker, toaster, blender, food processor". \
Use `kind=count` and a subject matching the category (e.g. "kitchen appliances").
  - Count atoms must embed the numeric value in the content so synthesis can retrieve the answer \
directly without counting individual atoms.

Return a JSON object with an `atoms` key containing an array of atom objects. \
Each atom must have exactly these keys: subject, kind, source, content, valid_from, valid_until.
"""

_CHAT_ADDENDUM = """\

Source-specific rules for chat/conversation (User: / Assistant: / System: turns):
  - USER turns are the primary source — extract personal facts, events, decisions, and preferences \
from them. These are things the specific person did, owns, experienced, or prefers.
  - ASSISTANT turns: extract two categories:
    (a) Specific named recommendations — brand, product, venue, person, or titled work.
        ✓ kind=recommendation: "I recommend Notion for notes", "Try the Honda Civic", \
"Read 'Deep Work' by Cal Newport" → subject = "<ProperName> recommendation"
    (b) Specific facts or data the assistant stated that the user may plausibly ask about later — \
a named technique with specific steps, a quoted statistic, a concrete list (e.g. specific languages, \
specific ingredients, a sequence of items). Extract as kind=fact.
        Test: "Could the user reasonably ask 'what did you tell me about X?' and need this specific detail?"
        ✓ A specific list of options the assistant named for this user's situation
        ✓ A specific number or measurement the assistant provided in context
        ✗ Generic advice applicable to anyone ("drink more water", "exercise regularly")
        ✗ Generic techniques without specific names ("use puns", "try self-deprecation")
    (c) Any assistant statement that directly references the user's own situation \
("Since you prefer X…", "Given that you bought Y…") → extract with the appropriate kind.
  - When in doubt whether content is specific-and-recallable vs generic — DO NOT extract it.
  - Personal events in USER turns (e.g. "I just bought a car", "I downloaded Ibotta", \
"I attended a class") must be captured as kind="event" atoms with the subject being the event \
(e.g. "Ibotta adoption", "car purchase", "baking class attendance").
  - Preserve explicit dates verbatim in atom content (e.g. "on January 10th", "on March 3rd"). \
Do not drop them. When the user says "today", "this morning", or "tonight", replace with the ISO \
date provided in "Today's date:" at the top of this prompt.

Preference, habit, and fact in chat — the distinction matters for retrieval:
  User: "I grow tomatoes and herbs at home."
  → kind=habit  subject="gardening"  ✓    NOT: kind=fact  subject="cherry tomatoes"  ✗

  User: "I've been cooking mostly vegetarian meals lately."
  → kind=habit  subject="dietary preference"  ✓    (recurring behavior revealed by what user does)

  User: "I usually commute by bike."
  → kind=habit  subject="commute"  ✓    NOT: kind=fact  subject="bike commute"  ✗

  User: "I prefer not to eat spicy food."
  → kind=preference  subject="dietary preference"  ✓    (explicitly stated preference)

  User: "I love dark roast coffee."
  → kind=preference  subject="coffee"  ✓    (explicitly stated like)

  User: "I own a car."
  → kind=fact  subject="transport"  ✓    (objective circumstance, not a habit or preference)

  User: "I had success with the lemon cake recipe last time."
  → kind=habit  subject="baking"  ✓    NOT: kind=fact  subject="lemon cake"  ✗

  User: "I want to run a marathon by December."
  → kind=goal  subject="fitness goal"  ✓    (objective with time horizon)

Habit vs preference rule: use kind=habit when the user SHOWS a pattern through what they do \
("I usually...", "I've been...", "I grow...", "I go to the gym...", "I had success with..."). \
Use kind=preference when the user STATES what they like or dislike \
("I prefer...", "I love...", "I hate...", "I don't like...", "my favorite is...").

Subject examples for chat — note how broad subjects cluster across conversations:
  User: "I went hiking on the Pacific Crest Trail last weekend."
  → subject: "hiking"  ✓      NOT: "PCT hike last weekend"  ✗

  User: "I attended a baking class at the community center."
  → subject: "baking"  ✓      NOT: "community center baking class attendance"  ✗

  User: "I signed up for a gym membership at Planet Fitness."
  → subject: "gym"  ✓         NOT: "Planet Fitness membership signup"  ✗

  User: "I've been struggling with lower back pain lately."
  → subject: "health"  ✓      NOT: "lower back pain issue"  ✗

  User: "I bought a new couch for the living room."
  → subject: "home furnishings"  ✓   NOT: "living room couch purchase"  ✗

  User: "I'm planning a trip to Japan in April."
  → subject: "travel"  ✓      NOT: "Japan trip planning for April"  ✗

The same broad subject should appear on atoms from multiple conversations. That is the goal.

Numeric extraction in chat — examples:
  User: "I own three bikes — a road bike, a mountain bike, and a fixie."
  → Extract: "User owns 3 bikes: road bike, mountain bike, fixie."  kind=count  subject="bikes"
  → Also extract individual ownership atoms if they carry distinct facts.

  User: "I have a coffee maker, toaster, blender, and food processor in my kitchen."
  → Extract: "User owns 4 kitchen appliances: coffee maker, toaster, blender, food processor."  kind=count  subject="kitchen appliances"

  User: "I've attended 5 yoga sessions this month."
  → Extract: "User attended 5 yoga sessions this month."  kind=count  subject="yoga"
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

_PDF_ADDENDUM = """\

Source-specific rules for PDF documents:
  - Context shows the page number. Use it to scope subjects when a page covers a distinct topic.
  - Pages may be part of a continuous document — carry forward names, subjects, and context \
from the page content even if earlier pages are not visible.
"""

_PPTX_ADDENDUM = """\

Source-specific rules for presentation slides:
  - Context shows the slide number. Use it to understand document structure.
  - Each slide typically makes one main point — extract that as the primary atom.
  - Supporting bullet points are separate atoms only if they carry distinct, self-contained facts.
"""

_XLSX_ADDENDUM = """\

Source-specific rules for spreadsheet data:
  - Context shows the sheet name. Use it to scope subjects (e.g. include the sheet name in the \
subject when it adds meaning, such as "training log" or "budget").
  - If rows represent distinct items or events (workouts, expenses, recipes), extract each as \
a separate atom.
  - If the sheet contains aggregates or summaries, prefer those over repeating individual rows.
  - Numeric values with clear meaning (totals, counts, percentages, rates) must use kind=count.
"""


def _source_addendum(source_type: str) -> str:
    if source_type == "chat":
        return _CHAT_ADDENDUM
    if source_type == "markdown":
        return _MARKDOWN_ADDENDUM
    if source_type == "code":
        return _CODE_ADDENDUM
    if source_type == "pdf":
        return _PDF_ADDENDUM
    if source_type == "pptx":
        return _PPTX_ADDENDUM
    if source_type in ("xlsx", "xls"):
        return _XLSX_ADDENDUM
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

_WRITTEN_NUMBERS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}
_WRITTEN_NUMBER_PATTERN = re.compile(
    r"\b(" + "|".join(_WRITTEN_NUMBERS) + r")\s+(days?|weeks?|months?)\s+ago\b",
    re.IGNORECASE,
)

_RELATIVE_PATTERNS: list[tuple[re.Pattern, Any]] = [
    (
        re.compile(r"\b(\d+)\s+days?\s+ago\b", re.IGNORECASE),
        lambda m, ref: (ref - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\b(\d+)\s+weeks?\s+ago\b", re.IGNORECASE),
        lambda m, ref: (ref - timedelta(weeks=int(m.group(1)))).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\b(\d+)\s+months?\s+ago\b", re.IGNORECASE),
        lambda m, ref: (ref - timedelta(days=int(m.group(1)) * 30)).strftime(
            "%Y-%m-%d"
        ),
    ),
    (
        re.compile(r"\ba\s+day\s+ago\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(days=1)).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\ba\s+week\s+ago\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(weeks=1)).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\ba\s+month\s+ago\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(days=30)).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\ba\s+year\s+ago\b", re.IGNORECASE),
        lambda _, ref: str(ref.year - 1),
    ),
    (re.compile(r"\blast\s+year\b", re.IGNORECASE), lambda _, ref: str(ref.year - 1)),
    (
        re.compile(r"\blast\s+week\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(weeks=1)).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\blast\s+month\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(days=30)).strftime("%Y-%m-%d"),
    ),
    (
        re.compile(r"\byesterday\b", re.IGNORECASE),
        lambda _, ref: (ref - timedelta(days=1)).strftime("%Y-%m-%d"),
    ),
    (re.compile(r"\btoday\b", re.IGNORECASE), lambda _, ref: ref.strftime("%Y-%m-%d")),
]

_WEEKDAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
_WEEKDAY_PATTERN = re.compile(
    r"\blast\s+(" + "|".join(_WEEKDAY_NAMES) + r")\b", re.IGNORECASE
)


def _resolve_dates(content: str, ref: datetime) -> str:
    """Replace relative date expressions in atom content with absolute ISO dates."""

    def _normalize_written(m: re.Match) -> str:
        n = _WRITTEN_NUMBERS[m.group(1).lower()]
        return f"{n} {m.group(2)} ago"

    content = _WRITTEN_NUMBER_PATTERN.sub(_normalize_written, content)

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


def _extract_json(text: str) -> str:
    """Extract the first complete top-level JSON object from an LLM response.

    Walks brace depth so arbitrarily nested objects (atoms inside arrays inside
    the top-level dict) are captured correctly. Handles markdown fences, prose
    preambles, and trailing commentary without regex edge cases.
    """
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return text[start : i + 1]
    return text


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


def segment_source(source: str, metadata: dict) -> list[Segment]:
    """Stage 1: parse source into segments. No LLM calls."""
    source_type = infer_source_type(source, metadata)
    return parse(source, source_type)


def _extract_atoms(segment: Segment, metadata: dict, ref: datetime, cfg: "Config") -> list[dict]:
    text = segment.text
    if segment.context:
        text = f"Context: {segment.context}\n\n{text}"
    system = _SYSTEM + _source_addendum(segment.source_type)
    messages = [
        {"role": "system", "content": system},
        {
            "role": "user",
            "content": (
                f"Today's date: {ref.date().isoformat()}\n\n---\n\n{text}"
                "\n\n---\nRespond with the JSON object only."
            ),
        },
    ]
    raw = complete(messages, cfg, text_format=_AtomList, model=cfg.ingest_model)
    try:
        atoms_data: list[dict] = json.loads(_extract_json(raw))["atoms"]
    except (json.JSONDecodeError, KeyError, TypeError):
        logging.getLogger("lattice.ingest").warning(
            "segment extraction returned unparseable JSON — skipping segment (len=%d)",
            len(raw),
        )
        return []

    source_override = metadata.get("source")
    for a in atoms_data:
        # Chat segments: preserve per-turn LLM attribution — a blanket override
        # would mislabel assistant-turn atoms as "user" (or vice-versa).
        if source_override and segment.source_type != "chat":
            a["source"] = source_override
        a["content"] = _resolve_dates(a["content"], ref)
        a["metadata"] = metadata
        a["segment_id"] = segment.segment_id
        a["source_type"] = segment.source_type
        a["source_span"] = {"start": segment.start, "end": segment.end}
    return atoms_data


def extract_atoms(
    segments: list[Segment],
    metadata: dict,
    ref: datetime,
    cfg: "Config",
) -> list[dict]:
    """Stage 2: LLM extraction with PII redact/restore. Returns raw atom dicts."""
    _redactor = EntityRedactor()
    _seg_texts, _entity_map = _redactor.redact_batch([s.text for s in segments], cfg)
    if _entity_map:
        segments = [
            Segment(
                segment_id=s.segment_id,
                text=rt,
                source_type=s.source_type,
                start=s.start,
                end=s.end,
                role=s.role,
                context=s.context,
            )
            for s, rt in zip(segments, _seg_texts)
        ]

    workers = cfg.ingest_workers
    if workers == 1 or len(segments) == 1:
        nested = [_extract_atoms(s, metadata, ref, cfg) for s in segments]
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            nested = list(
                pool.map(lambda s: _extract_atoms(s, metadata, ref, cfg), segments)
            )
    atoms_data = [a for atoms in nested for a in atoms]

    if _entity_map:
        for a in atoms_data:
            a["content"] = _redactor.restore(a["content"], _entity_map)
            if a.get("subject"):
                a["subject"] = _redactor.restore(a["subject"], _entity_map)

    return atoms_data


def detect_supersession(db: LatticeDB, new_atom: Atom, cfg: "Config") -> str | None:
    """Stage 3: decide if new_atom supersedes an existing atom. Returns old atom_id or None."""
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
        raw = complete(messages, cfg, text_format=_SupersessionResult, model=cfg.ingest_model)
        try:
            superseded_id = json.loads(_extract_json(raw)).get("superseded_atom_id")
        except (json.JSONDecodeError, AttributeError):
            return None
        if not superseded_id:
            return None
        return existing_id if superseded_id == existing_id else None

    # Slow path: scan by subject (handles hand-edited atoms)
    existing = [a for a in db.by_subject(new_atom.subject) if not a.is_superseded]
    if not existing:
        # Fuzzy path: find semantically similar subjects via token overlap
        fuzzy_ids = db.fuzzy_subject_candidates(new_atom.subject, cfg.subject_fuzzy_threshold)
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
    raw = complete(messages, cfg, text_format=_SupersessionResult, model=cfg.ingest_model)
    try:
        superseded_id = json.loads(_extract_json(raw)).get("superseded_atom_id")
    except (json.JSONDecodeError, AttributeError):
        return None
    if not superseded_id:
        return None
    valid_ids = {a.atom_id for a in existing}
    return superseded_id if superseded_id in valid_ids else None


def persist_atoms(
    atoms_data: list[dict],
    db: LatticeDB,
    source_id: str,
    observed_at: "datetime | None",
    ref: datetime,
    cfg: "Config",
) -> dict:
    """Stage 4: dedup + supersession + DB write. Returns summary dict (no segments_processed)."""
    created_ids: list[str] = []
    new_ids: list[str] = []
    updated_ids: list[str] = []
    duplicate_ids: list[str] = []

    for data in atoms_data:
        content = data["content"]
        content_hash = _hash_text(content)
        normalized_hash = _hash_text(_normalized_content(content))
        meta = data.get("metadata", {})

        with db.lock:
            duplicate = db.find_by_normalized_hash(normalized_hash)
            if duplicate is not None:
                duplicate_ids.append(duplicate.atom_id)
                continue

            atom = Atom(
                kind=data.get("kind", "fact"),
                source=data.get("source", "document"),
                subject=data.get("subject") or data.get("topic") or "",
                content=content,
                valid_from=_parse_date(data.get("valid_from")),
                valid_until=_parse_date(data.get("valid_until")),
                ingested_at=ref,
                observed_at=observed_at,
                source_id=source_id,
                source_title=meta.get("title") or meta.get("source_title"),
                session_id=meta.get("session_id"),
                segment_id=data.get("segment_id"),
                source_type=data.get("source_type"),
                source_span=data.get("source_span"),
                content_hash=content_hash,
                normalized_content_hash=normalized_hash,
                metadata=meta,
            )

            old_id = detect_supersession(db, atom, cfg)
            if old_id:
                db.supersede(old_id, atom)
                updated_ids.append(atom.atom_id)
            else:
                db.write(atom)
                new_ids.append(atom.atom_id)

            if atom.subject:
                db.register_subject(atom.subject, atom.atom_id)

            created_ids.append(atom.atom_id)

    return {
        "atoms_created": len(created_ids),
        "atoms_new": len(new_ids),
        "atoms_updated": len(updated_ids),
        "atom_ids": created_ids,
        "new_atom_ids": new_ids,
        "updated_atom_ids": updated_ids,
        "duplicates_skipped": len(duplicate_ids),
        "duplicate_atom_ids": duplicate_ids,
        "source_id": source_id,
    }


def ingest(
    source: str,
    metadata: dict | None = None,
    db: LatticeDB | None = None,
    cfg: "Config | None" = None,
) -> dict:
    if cfg is None:
        from lattice.config import Config
        cfg = Config.from_env()
    if db is None:
        db = LatticeDB(cfg.lattice_dir)
    metadata = metadata or {}
    source_id = str(metadata.get("source_id") or uuid.uuid4())
    observed_at = _parse_datetime(
        metadata.get("observed_at") or metadata.get("date") or metadata.get("timestamp")
    )
    ref = observed_at or _today()

    segments = segment_source(source, metadata)
    atoms_data = extract_atoms(segments, metadata, ref, cfg)
    result = persist_atoms(atoms_data, db, source_id, observed_at, ref, cfg)
    result["segments_processed"] = len(segments)
    return result
