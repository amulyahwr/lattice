"""Consolidator — Stage 8 of the compiler pipeline.

After new atoms are indexed, finds near-duplicate existing atoms via pgvector
similarity and classifies the relationship:

  confirms    — same fact, same scope, different wording
                → boost confidence on existing; emit confirms link
  subsumes    — new atom contains everything existing said, plus more
                → mark existing superseded; emit subsumes link
  supersedes  — fact has changed; new replaces old
                → mark existing superseded; emit supersedes link
  contradicts — they disagree
                → both live; emit contradicts link on both; flag for review
  distinct    — similar but genuinely different facts; no action

This replaces the old Tier 2 canonical_hash dedup gate. Instead of silently
discarding near-duplicate atoms, we let them in and record *why* they are
related. Provenance is preserved; the serving layer collapses them at query time.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, RootModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.llm_client import chat
from backend.models.atoms import Atom, AtomVersion

logger = logging.getLogger(__name__)

# Cosine distance threshold — atoms closer than this are sent to the LLM for
# relationship classification. 0.15 ≈ cosine similarity ≥ 0.85.
CONSOLIDATION_DISTANCE_THRESHOLD = 0.15

# Max existing-atom candidates to consider per new atom.
CONSOLIDATION_TOP_K = 5

VALID_RELATIONS = {"confirms", "subsumes", "supersedes", "contradicts", "distinct"}

_SYSTEM = """\
You classify the relationship between pairs of knowledge atoms.

You receive a JSON array of pairs, each with:
  "new":      a newly ingested atom
  "existing": an atom already in the knowledge base

For each pair, classify the relationship from the NEW atom's perspective:

  confirms    — same fact, same scope, just different wording
  subsumes    — new contains everything existing said AND more (new is richer)
  supersedes  — the fact has changed; new replaces existing (information evolved)
  contradicts — they make conflicting or opposing claims
  distinct    — similar topic but genuinely different facts; no consolidation needed

Return a JSON array parallel to the input, one classification per pair:
[{"pair_index": 0, "relation": "confirms"}, ...]

Rules:
- Output ONLY valid JSON — no explanation, no markdown, no code fences
- Every pair_index from 0 to N-1 must appear exactly once
- Use "distinct" when in doubt — false consolidations are worse than missed ones
"""


# ── Response schema ───────────────────────────────────────────────────────────


class _Classification(BaseModel):
    pair_index: int
    relation: Literal["confirms", "subsumes", "supersedes", "contradicts", "distinct"] = "distinct"


class _ConsolidateResponse(RootModel[list[_Classification]]):
    pass


# ── Parser ────────────────────────────────────────────────────────────────────


def _parse_classifications(raw: str, expected: int) -> list[str]:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        logger.warning("Consolidator: LLM returned no JSON array, defaulting all to distinct")
        return ["distinct"] * expected

    try:
        items_raw = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("Consolidator: JSON parse failed, defaulting all to distinct")
        return ["distinct"] * expected

    results = ["distinct"] * expected
    for item in items_raw:
        try:
            c = _Classification.model_validate(item)
            if 0 <= c.pair_index < expected:
                results[c.pair_index] = c.relation
        except Exception:
            continue
    return results


# ── DB helpers ────────────────────────────────────────────────────────────────


async def _find_candidates(
    db: AsyncSession,
    atom: Atom,
    exclude_ids: list[uuid.UUID],
) -> list[Atom]:
    """Return existing atoms within CONSOLIDATION_DISTANCE_THRESHOLD of atom."""
    stmt = (
        select(Atom)
        .where(Atom.dense_vec.cosine_distance(atom.dense_vec) <= CONSOLIDATION_DISTANCE_THRESHOLD)
        .where(Atom.is_superseded.is_(False))
        .where(Atom.id != atom.id)
        .order_by(Atom.dense_vec.cosine_distance(atom.dense_vec))
        .limit(CONSOLIDATION_TOP_K)
    )
    if exclude_ids:
        stmt = stmt.where(Atom.id.not_in(exclude_ids))

    result = await db.execute(stmt)
    return result.scalars().all()


def _write_version(atom: Atom, reason: str, triggered_by: uuid.UUID, now: datetime) -> AtomVersion:
    return AtomVersion(
        atom_id=atom.id,
        version=atom.version,
        content=atom.content,
        canonical=atom.canonical,
        valid_from=atom.valid_from or now,
        valid_until=now,
        reason=reason,
        triggered_by_atom_id=triggered_by,
    )


def _add_link(atom: Atom, target_id: uuid.UUID, relation: str) -> None:
    existing = {lnk["target_id"] for lnk in (atom.links or [])}
    if str(target_id) not in existing:
        atom.links = (atom.links or []) + [
            {"target_id": str(target_id), "relation": relation}
        ]


# ── Main entry point ──────────────────────────────────────────────────────────


async def consolidate_atoms(
    db: AsyncSession,
    new_atoms: list[Atom],
) -> dict:
    """Run consolidation for a batch of newly indexed atoms.

    For each new atom, finds near-duplicate existing atoms, classifies the
    relationship via LLM, and applies the appropriate action.

    Returns a summary dict with counts per relation type.
    """
    if not new_atoms:
        return {}

    new_ids = [a.id for a in new_atoms]
    now = datetime.now(timezone.utc)

    # Build (new_atom, candidate) pairs across all new atoms in one pass.
    pairs: list[tuple[Atom, Atom]] = []
    for new_atom in new_atoms:
        if new_atom.dense_vec is None:
            continue
        candidates = await _find_candidates(db, new_atom, exclude_ids=new_ids)
        for candidate in candidates:
            pairs.append((new_atom, candidate))

    if not pairs:
        return {}

    # Single batched LLM call for all pairs.
    payload = json.dumps(
        [
            {
                "pair_index": i,
                "new": new.content,
                "existing": existing.content,
            }
            for i, (new, existing) in enumerate(pairs)
        ],
        ensure_ascii=False,
    )
    raw = await chat(_SYSTEM, payload, temperature=0.0, response_format=_ConsolidateResponse)
    relations = _parse_classifications(raw, expected=len(pairs))

    counts: dict[str, int] = {}
    for (new_atom, existing_atom), relation in zip(pairs, relations):
        counts[relation] = counts.get(relation, 0) + 1

        if relation == "distinct":
            continue

        if relation == "confirms":
            existing_atom.confidence = (existing_atom.confidence or 1.0) + 0.5
            db.add(
                _write_version(existing_atom, reason="confirmed", triggered_by=new_atom.id, now=now)
            )
            _add_link(new_atom, existing_atom.id, "confirms")

        elif relation in ("subsumes", "supersedes"):
            # Archive the existing atom.
            db.add(
                _write_version(existing_atom, reason="superseded", triggered_by=new_atom.id, now=now)
            )
            existing_atom.is_superseded = True
            existing_atom.superseded_by = new_atom.id
            existing_atom.valid_until = now
            _add_link(new_atom, existing_atom.id, relation)

        elif relation == "contradicts":
            _add_link(new_atom, existing_atom.id, "contradicts")
            _add_link(existing_atom, new_atom.id, "contradicts")

    await db.flush()

    logger.info(
        "Consolidation complete: %s",
        ", ".join(f"{v} {k}" for k, v in counts.items() if k != "distinct"),
    )
    return counts
