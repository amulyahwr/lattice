from __future__ import annotations

from datetime import date

from lattice.db import LatticeDB
from lattice.models import Atom


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


def select(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> list[dict]:
    if db is None:
        db = LatticeDB()

    seeds = db.search(query, as_of=as_of, top_k=top_k)
    if not seeds:
        return []

    max_atoms = max(top_k, top_k * 3)
    graph = db.graph

    if graph.graph.number_of_nodes() > 0:
        return _graph_select(seeds, graph, db, as_of, max_atoms)

    # Fallback: P4 evidence_pack expansion
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
