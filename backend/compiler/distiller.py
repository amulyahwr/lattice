"""Distiller — rewrite each proposition concisely and extract canonical form.

A single batched LLM call handles all atoms from a compilation run.
Returns distilled content (≤25 words) and a structured canonical form used
for cross-source dedup of metrics and facts.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, RootModel

from backend.compiler.atomizer import RawAtom
from backend.compiler.llm_client import chat

_SYSTEM = """\
You are a knowledge distillation system.

You receive a JSON array of propositions. For each proposition:
1. Rewrite it concisely in 25 words or fewer. Preserve all numbers, names, and dates exactly.
2. Extract a canonical form if the proposition contains a measurable value.

Return a JSON array of the same length and order. Each element must be:
{
  "content": "<concise rewrite>",
  "canonical": {
    "subject": "<what is being measured or described>",
    "predicate": "<the relationship or verb>",
    "object": "<the value, outcome, or target>",
    "value": <numeric value as a number, or null>,
    "unit": "<USD / % / count / etc., or null>",
    "period": "<time period like Q2-2026, or null>"
  }
}

Set "canonical" to null for events and procedures where no
measurable value exists.

Output ONLY valid JSON — no explanation, no markdown, no code fences.
"""

_BATCH_SIZE = 25  # atoms per LLM call


# ── Response schema ───────────────────────────────────────────────────────────


class _CanonicalForm(BaseModel):
    subject: str
    predicate: str
    object: str
    value: float | None = None
    unit: str | None = None
    period: str | None = None


class _DistilledAtom(BaseModel):
    content: str
    canonical: _CanonicalForm | None = None


class _DistillResponse(RootModel[list[_DistilledAtom]]):
    pass


# ── Parser ────────────────────────────────────────────────────────────────────


def _extract_json_array(text: str) -> str:
    """Strip any surrounding prose and extract the JSON array."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError(f"Distiller: no JSON array in output: {text[:300]!r}")
    return text[start : end + 1]


async def distill_atoms(atoms: list[RawAtom]) -> list[dict]:
    """Distill all atoms, returning [{content, canonical}] parallel to input."""
    results: list[dict] = []

    for i in range(0, len(atoms), _BATCH_SIZE):
        batch = atoms[i : i + _BATCH_SIZE]
        payload = json.dumps(
            [{"kind": a.kind, "proposition": a.content} for a in batch],
            ensure_ascii=False,
        )
        output = await chat(_SYSTEM, payload, response_format=_DistillResponse)
        raw = _extract_json_array(output)

        try:
            parsed = _DistillResponse.model_validate_json(raw)
        except Exception as exc:
            raise ValueError(f"Distiller: invalid response structure: {raw[:300]!r}") from exc

        if len(parsed.root) != len(batch):
            raise ValueError(
                f"Distiller returned {len(parsed.root)} items for {len(batch)} atoms in batch {i}"
            )

        for atom in parsed.root:
            results.append({
                "content": atom.content,
                "canonical": atom.canonical.model_dump() if atom.canonical else None,
            })

    return results
