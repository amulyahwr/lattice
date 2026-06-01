from __future__ import annotations

import json
import os
from datetime import date

from pydantic import BaseModel, Field

from lattice.db import LatticeDB
from lattice.llm import complete
from lattice.models import Atom
from lattice.query import parse_query

_PROBE_K = 7
_POINTED_MAX = 14
_BFS_MAX_ATOMS = 60


class _AtomSelectionCoarse(BaseModel):
    n_selected: int = Field(ge=8, le=25)
    atom_ids: list[str] = Field(min_length=8, max_length=25)

class _AtomSelectionFine(BaseModel):
    n_selected: int = Field(ge=5, le=15)
    atom_ids: list[str] = Field(min_length=5, max_length=15)


_RECOMMENDATION_CAP = int(os.environ.get("LATTICE_RECOMMENDATION_CAP", "5"))


def _apply_recommendation_cap(atoms: list[dict]) -> list[dict]:
    rec_seen = 0
    result = []
    for atom in atoms:
        if atom.get("kind") == "recommendation":
            if rec_seen < _RECOMMENDATION_CAP:
                result.append(atom)
                rec_seen += 1
        else:
            result.append(atom)
    return result


def _atom_to_dict(a: Atom) -> dict:
    return {
        "atom_id": a.atom_id,
        "subject": a.subject,
        "kind": a.kind,
        "source": a.source,
        "content": a.content,
        "valid_from": a.valid_from.isoformat() if a.valid_from else None,
        "valid_until": a.valid_until.isoformat() if a.valid_until else None,
        "is_superseded": a.is_superseded,
        "supersedes": a.supersedes,
        "superseded_by": a.superseded_by,
        # Keep flat provenance fields for product/synthesis callers.
        "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
        "observed_at": a.observed_at.isoformat() if a.observed_at else None,
        "source_id": a.source_id,
        "source_title": a.source_title,
        "session_id": a.session_id,
        "segment_id": a.segment_id,
        "source_type": a.source_type,
        "source_span": a.source_span,
        # Mirror eval debug payload shape so select/bm25 modes differ only by
        # retrieval behavior, not metadata structure.
        "provenance": {
            "source_id": a.source_id,
            "source_title": a.source_title,
            "source_type": a.source_type,
            "session_id": a.session_id,
            "segment_id": a.segment_id,
            "source_span": a.source_span,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
        },
        "dedup": {
            "content_hash": a.content_hash,
            "normalized_content_hash": a.normalized_content_hash,
        },
    }


def _source_diversity(seeds: list[Atom]) -> int:
    return len({a.source_id for a in seeds if a.source_id})


def _retrieve(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> list[dict]:
    if db is None:
        db = LatticeDB()

    intent = parse_query(query)
    seeds = db.search(query, as_of=as_of, top_k=top_k)
    if not seeds:
        return []

    # Source-diversity probe: top _PROBE_K seeds tell us whether the answer
    # lives in one source (pointed) or spans multiple sources (expansion).
    probe = seeds[:_PROBE_K]
    if _source_diversity(probe) <= 1:
        active_seeds, max_atoms = probe, _POINTED_MAX
    else:
        active_seeds, max_atoms = seeds, _BFS_MAX_ATOMS

    graph = db.graph

    if graph.graph.number_of_nodes() > 0:
        result = _graph_select(active_seeds, graph, db, as_of, max_atoms)
    else:
        result = _fallback_select(active_seeds, db, as_of, max_atoms)

    # Kind fallback: if query has a primary kind and BFS found none, scan all.
    if intent.primary_kind is not None:
        present_kinds = {a["kind"] for a in result}
        if intent.primary_kind not in present_kinds:
            seen_ids = {a["atom_id"] for a in result}
            for fa in db.list_by_kind(intent.primary_kind, as_of=as_of):
                if fa.atom_id not in seen_ids:
                    result.append(_atom_to_dict(fa))

    return _apply_recommendation_cap(result)


def _graph_select(
    seeds: list,
    graph,
    db: LatticeDB,
    as_of: date | None,
    max_atoms: int,
) -> list[dict]:
    expanded_ids = graph.bfs_expand(
        [s.atom_id for s in seeds],
        max_depth=4,
        max_atoms=max_atoms,
    )

    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    result: list[Atom] = []

    for atom_id in expanded_ids:
        if atom_id in seen_ids:
            continue
        seen_ids.add(atom_id)
        try:
            atom = db.read(atom_id)
        except Exception:
            continue

        # Temporal validity filter
        if as_of is not None:
            if atom.valid_from is not None and atom.valid_from > as_of:
                continue
            if atom.valid_until is not None and atom.valid_until < as_of:
                continue

        # Collapse exact duplicates by normalized content hash
        if atom.normalized_content_hash:
            if atom.normalized_content_hash in seen_hashes:
                continue
            seen_hashes.add(atom.normalized_content_hash)

        result.append(atom)

    return [_atom_to_dict(a) for a in result]


def _fallback_select(
    seeds: list,
    db: LatticeDB,
    as_of: date | None,
    max_atoms: int,
) -> list[dict]:
    selected = []
    seen: set[str] = set()
    for seed in seeds:
        for atom in db.evidence_pack(seed, as_of=as_of):
            if atom.atom_id in seen:
                continue
            selected.append(atom)
            seen.add(atom.atom_id)
            if len(selected) >= max_atoms:
                return [_atom_to_dict(a) for a in selected]
    return [_atom_to_dict(a) for a in selected]


# ── LLM semantic filter (two-stage) ──────────────────────────────────────────

_FILTER_COARSE_PROMPT = """\
You are a memory filter. Given a query and a list of memory atoms (subject and kind only), \
select atoms most likely to contain information useful for answering the query.
Be generous — include any atom that could plausibly be relevant. \
Only exclude atoms that are clearly off-topic. Aim for 15–25 atoms.
Respond with a JSON object.
"""

_FILTER_FINE_PROMPT = """\
You are a memory filter. Given a query and a shortlist of memory atoms with full content, \
select atoms most useful for answering the query.
Keep at least half the atoms you receive. Only drop atoms that are clearly unrelated. \
When in doubt, keep the atom. Aim for 8–15 atoms.
Respond with a JSON object.
"""


def select(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> list[dict]:
    """BM25 + graph BFS retrieval followed by a two-stage LLM filter.

    Stage 1 (coarse): all candidates, subject + kind only → pick top 20 by topic relevance.
    Stage 2 (fine):   shortlist, full content → pick final 10-15 by content relevance.
    Falls back to the previous stage's output on any parse/LLM error.
    """
    candidates = _retrieve(query, as_of=as_of, db=db, top_k=top_k)
    if not candidates:
        return []

    model = os.environ.get("SELECTION_MODEL") or None
    num_ctx = int(os.environ.get("SELECTION_NUM_CTX", "8192"))

    # Stage 1: coarse — subject + kind only, fits 40+ atoms in ~600 tokens
    def _coarse_entry(a: dict) -> dict:
        e: dict = {"atom_id": a["atom_id"], "subject": a["subject"],
                   "kind": a["kind"], "observed_at": a["observed_at"]}
        if a.get("source_title"):
            e["source_title"] = a["source_title"]
        return e

    coarse_msgs = [
        {"role": "system", "content": _FILTER_COARSE_PROMPT},
        {"role": "user", "content": f"Query: {query}\n\nCandidates:\n{json.dumps([_coarse_entry(a) for a in candidates])}"},
    ]
    coarse_ids: set[str] = set()
    for _attempt in range(2):
        try:
            r1 = complete(coarse_msgs, text_format=_AtomSelectionCoarse, model=model, num_ctx=num_ctx)
            coarse_ids = set(json.loads(r1).get("atom_ids", []))
            if coarse_ids:
                break
        except Exception:
            pass
    shortlist = [a for a in candidates if a["atom_id"] in coarse_ids] or candidates[:20]

    # Stage 2: fine — full content, fits 20 atoms in ~1,800 tokens
    fine_msgs = [
        {"role": "system", "content": _FILTER_FINE_PROMPT},
        {"role": "user", "content": f"Query: {query}\n\nCandidates:\n{json.dumps([{'atom_id': a['atom_id'], 'subject': a['subject'], 'kind': a['kind'], 'content': a['content'], 'observed_at': a['observed_at']} for a in shortlist])}"},
    ]
    fine_ids: set[str] = set()
    for _attempt in range(2):
        try:
            r2 = complete(fine_msgs, text_format=_AtomSelectionFine, model=model, num_ctx=num_ctx)
            fine_ids = set(json.loads(r2).get("atom_ids", []))
            if fine_ids:
                break
        except Exception:
            pass
    filtered = [a for a in shortlist if a["atom_id"] in fine_ids]
    return filtered if len(filtered) >= 5 else shortlist
