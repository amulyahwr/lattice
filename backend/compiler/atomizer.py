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

import json
from dataclasses import dataclass, field

from backend.compiler.llm_client import chat

_SYSTEM = """\
You extract atomic propositions from text.

A proposition is a single, self-contained claim: subject + predicate + object.
One sentence often contains multiple propositions — split them into separate lines.

For each proposition output exactly one line in this format:
<kind>|<proposition>

Kinds:
  metric       — a quantitative claim; must include the specific number or value
  decision     — something decided, approved, or agreed
  event        — something that happened, was launched, or completed
  procedure    — a step-by-step instruction or process description
  fact         — any other standalone claim

Rules:
- Each proposition must be fully self-contained (include all names, dates, values)
- Metrics must include the numeric value; never omit it
- Skip navigation text, page numbers, section headers, and formatting noise
- Do not number lines, add explanations, or output blank lines
- Output ONLY the <kind>|<proposition> lines, nothing else
"""

_VALID_KINDS = frozenset({"fact", "metric", "decision", "event", "procedure"})


@dataclass
class RawAtom:
    """A proposition extracted from source text, before distillation."""

    content: str
    kind: str = "fact"
    entities: list[str] = field(default_factory=list)


def _parse_propositions(llm_output: str) -> list[RawAtom]:
    atoms: list[RawAtom] = []
    for line in llm_output.splitlines():
        line = line.strip()
        if "|" not in line:
            continue
        kind, _, content = line.partition("|")
        kind = kind.strip().lower()
        content = content.strip()
        if kind not in _VALID_KINDS or len(content.split()) < 3:
            continue
        atoms.append(RawAtom(content=content, kind=kind))
    return atoms


async def atomize_chunk(text: str) -> list[RawAtom]:
    """Extract atomic propositions from a single text chunk."""
    output = await chat(_SYSTEM, text.strip())
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
    """Extract the JSON array from a merged LLM response, filtering bad items."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []

    result: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "fact")).strip().lower()
        content = str(item.get("content", "")).strip()
        if kind not in _VALID_KINDS or len(content.split()) < 3:
            continue
        result.append({"kind": kind, "content": content, "canonical": item.get("canonical")})
    return result


async def atomize_and_distill_chunk(text: str) -> list[dict]:
    """Extract and distill atoms from one chunk in a single LLM call.

    Returns [{kind, content, canonical}] — the merged output used by the
    pipeline in place of separate atomize + distill calls.
    """
    output = await chat(_MERGED_SYSTEM, text.strip())
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
