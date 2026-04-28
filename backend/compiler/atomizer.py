"""Atomizer — extract atomic propositions from raw text using LLM.

A proposition is a single, self-contained claim: subject + predicate + object.
One sentence often contains multiple propositions — the LLM splits them.

Each proposition is classified into a kind:
  fact | metric | decision | event | procedure

atomize_and_distill_chunks() is the fast path used by the pipeline: one LLM
call per chunk extracts and distills in a single round-trip, cutting LLM calls
in half compared to the sequential atomize→distill approach.

atomize_chunk() / atomize_chunks() are kept for direct unit testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, RootModel

from backend.compiler.llm_client import chat
from backend.compiler.period_utils import extract_period_from_text, normalize_period


# ── Response schema for the merged extract+distill call ──────────────────────


class _CanonicalForm(BaseModel):
    subject: str
    predicate: str
    object: str
    value: float | None = None
    unit: str | None = None
    period: str | None = None


class _ExtractedAtom(BaseModel):
    kind: Literal["fact", "metric", "decision", "event", "procedure"]
    content: str
    canonical: _CanonicalForm | None = None


class _ExtractResponse(RootModel[list[_ExtractedAtom]]):
    """Top-level schema: a JSON array of extracted atoms."""


class _RawAtomItem(BaseModel):
    kind: Literal["fact", "metric", "decision", "event", "procedure"]
    content: str


class _AtomizeResponse(RootModel[list[_RawAtomItem]]):
    pass


_SYSTEM = """\
You extract atomic propositions from text.

A proposition is a single, self-contained claim: subject + predicate + object.
One sentence often contains multiple propositions — split them into separate items.

Classify each into a kind:
  metric       — a quantitative claim; must include the specific number or value
  decision     — something decided, approved, or agreed
  event        — something that happened, was launched, or completed
  procedure    — a step-by-step instruction or process description
  fact         — any other standalone claim

Rules:
- Each proposition must be fully self-contained (include all names, dates, values)
- Metrics must include the numeric value; never omit it
- Skip navigation text, page numbers, section headers, and formatting noise
- Return [] if no valid propositions are found
- Output ONLY a valid JSON array — no explanation, no markdown, no code fences

Return a JSON array. Each element:
{"kind": "<kind>", "content": "<proposition>"}
"""

_VALID_KINDS = frozenset({"fact", "metric", "decision", "event", "procedure"})


@dataclass
class RawAtom:
    """A proposition extracted from source text, before distillation."""

    content: str
    kind: str = "fact"
    entities: list[str] = field(default_factory=list)


def _parse_propositions(text: str) -> list[RawAtom]:
    import json as _json
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        raw_items = _json.loads(text[start : end + 1])
    except _json.JSONDecodeError:
        return []
    atoms = []
    for item in raw_items:
        try:
            parsed = _RawAtomItem.model_validate(item)
            if len(parsed.content.split()) >= 3:
                atoms.append(RawAtom(content=parsed.content, kind=parsed.kind))
        except Exception:
            continue
    return atoms


async def atomize_chunk(text: str) -> list[RawAtom]:
    """Extract atomic propositions from a single text chunk."""
    output = await chat(_SYSTEM, text.strip(), response_format=_AtomizeResponse)
    return _parse_propositions(output)


async def atomize_chunks(chunks_text: list[str]) -> list[RawAtom]:
    """Atomize all chunks, deduplicating exact-match propositions within a run."""
    seen: set[str] = set()
    all_atoms: list[RawAtom] = []

    for text in chunks_text:
        for atom in await atomize_chunk(text):
            key = atom.content.lower().strip()
            if key not in seen:
                seen.add(key)
                all_atoms.append(atom)

    return all_atoms


# ── Merged extract + distill (fast path) ─────────────────────────────────────

_MERGED_SYSTEM = """\
You extract and distill atomic propositions from text.

For each proposition found:
1. Classify it into a kind: fact | metric | decision | event | procedure
2. Rewrite it concisely in 25 words or fewer, preserving all numbers, names, and dates exactly.
3. Extract a canonical form ONLY if the proposition contains a measurable numeric value.

Return a JSON array. Each element must be:
{
  "kind": "<fact|metric|decision|event|procedure>",
  "content": "<concise rewrite, 25 words or fewer>",
  "canonical": {
    "subject": "<what is being measured>",
    "predicate": "<relationship or verb>",
    "object": "<value, outcome, or target>",
    "value": <number or null>,
    "unit": "<USD | % | count | etc., or null>",
    "period": "<time period like Q2-2026, or null>"
  }
}

Set "canonical" to null for events, procedures, and non-numeric facts.

Rules:
- Each proposition must be fully self-contained (include all names, dates, values)
- Metrics must preserve the exact numeric value
- Skip navigation text, page numbers, section headers, and formatting noise
- Return [] if no valid propositions are found
- Output ONLY a valid JSON array — no explanation, no markdown, no code fences
"""


def _parse_merged(text: str) -> list[dict]:
    """Validate and normalise the merged LLM response using the Pydantic schema.

    Falls back to an empty list on any parse or validation error so the pipeline
    never crashes on a malformed model response.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        atoms = _ExtractResponse.model_validate_json(text[start : end + 1])
    except Exception:
        return []

    result: list[dict] = []
    for atom in atoms.root:
        if len(atom.content.split()) < 3:
            continue
        canonical = atom.canonical.model_dump() if atom.canonical else None

        # Regex fallback — if LLM left period null, extract it from the atom content
        detected = extract_period_from_text(atom.content)
        if detected:
            period_norm = normalize_period(detected)
            if canonical is None:
                canonical = {"period": period_norm}
            elif not canonical.get("period"):
                canonical["period"] = period_norm

        result.append({
            "kind": atom.kind,
            "content": atom.content,
            "canonical": canonical,
        })
    return result


async def atomize_and_distill_chunk(text: str) -> list[dict]:
    """Extract and distill atoms from one chunk in a single LLM call.

    Returns [{kind, content, canonical}] — the merged output used by the
    pipeline in place of separate atomize + distill calls.
    """
    output = await chat(_MERGED_SYSTEM, text.strip(), response_format=_ExtractResponse)
    return _parse_merged(output)


async def atomize_and_distill_chunks(chunks_text: list[str]) -> list[dict]:
    """Atomize and distill all chunks, deduplicating on distilled content.

    Returns [{kind, content, canonical}] ready for the pipeline index stage.
    """
    seen: set[str] = set()
    all_items: list[dict] = []

    for text in chunks_text:
        for item in await atomize_and_distill_chunk(text):
            key = item["content"].lower().strip()
            if key not in seen:
                seen.add(key)
                all_items.append(item)

    return all_items
