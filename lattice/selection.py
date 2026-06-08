from __future__ import annotations

import math
import os
from datetime import date, datetime, timezone

from lattice.db import LatticeDB
from lattice.models import Atom
from lattice.query import parse_query

_PROBE_K = 7
_POINTED_MAX = 14
_BFS_MAX_ATOMS = 60


_RECOMMENDATION_CAP = int(os.environ.get("LATTICE_RECOMMENDATION_CAP", "5"))
# Drop BM25 seeds scoring exactly 0 (matched no query tokens) before BFS.
# Zero-score seeds expand the graph from unrelated atoms, injecting noise.
_SEED_MIN_SCORE = float(os.environ.get("LATTICE_SEED_MIN_SCORE", "0.0"))
# After BFS expansion, re-sort result by BM25 score so highest-signal atoms surface first.
_BFS_RESCORE = os.environ.get("LATTICE_BFS_RESCORE", "").lower() in ("1", "true")
# Pre-BFS seed weight multiplier: decay BM25 score by atom age + kind.
# Set LATTICE_TIME_DECAY=0 to disable.
_TIME_DECAY = os.environ.get("LATTICE_TIME_DECAY", "1").lower() not in ("0", "false")

# Half-life in days per kind. Atoms older than 2× half-life are heavily discounted.
# Durable kinds (fact, count) decay very slowly; transient kinds (reminder) decay fast.
_HALF_LIFE: dict[str, float] = {
    "reminder":       3.0,
    "event":         60.0,
    "recommendation": 90.0,
    "decision":      180.0,
    "preference":    365.0,
    "belief":        365.0,
    "fact":          730.0,
    "count":         730.0,
}
_DEFAULT_HALF_LIFE = 180.0
_DECAY_FLOOR = 0.1  # never fully silence an atom via decay alone


def _decay_factor(kind: str | None, ref_dt: datetime | None, now: datetime | None = None) -> float:
    """Exponential decay multiplier: 1.0 when fresh, approaching _DECAY_FLOOR when old.

    `now` defaults to wall clock. Pass `as_of` converted to datetime for historical queries
    so atoms are decayed relative to the query date, not today.
    """
    if not _TIME_DECAY or ref_dt is None:
        return 1.0
    half_life = _HALF_LIFE.get(kind or "", _DEFAULT_HALF_LIFE)
    if ref_dt.tzinfo is None:
        ref_dt = ref_dt.replace(tzinfo=timezone.utc)
    _now = now or datetime.now(tz=timezone.utc)
    age_days = (_now - ref_dt).total_seconds() / 86400
    if age_days <= 0:
        return 1.0
    return max(math.exp(-age_days * math.log(2) / half_life), _DECAY_FLOOR)


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
    scored_seeds = db.search_scored(query, as_of=as_of, top_k=top_k)
    if _SEED_MIN_SCORE > 0.0:
        scored_seeds = [(s, a) for s, a in scored_seeds if s > _SEED_MIN_SCORE]

    if _TIME_DECAY:
        # Decay relative to as_of when provided (historical queries); else wall clock.
        now_dt = (
            datetime.combine(as_of, datetime.min.time()).replace(tzinfo=timezone.utc)
            if as_of else datetime.now(tz=timezone.utc)
        )
        scored_seeds = [
            (s * _decay_factor(a.kind, a.observed_at or a.ingested_at, now=now_dt), a)
            for s, a in scored_seeds
        ]
        scored_seeds.sort(key=lambda x: x[0], reverse=True)

    seeds = [a for _, a in scored_seeds]
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

    if _BFS_RESCORE and result:
        scored = db.search_scored(query, as_of=as_of, top_k=len(result) + top_k)
        score_map = {a.atom_id: s for s, a in scored}
        result.sort(key=lambda d: score_map.get(d["atom_id"], 0.0), reverse=True)

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


def select(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> list[dict]:
    return _retrieve(query, as_of=as_of, db=db, top_k=top_k)
