"""Compiler Pipeline — orchestrates extract → embed → link+tag → index → cross-link.

LLM call count per source (vs. old atomize→distill→link→tag):
  Old: 4 calls  (atomize, distill, link, tag)
  New: 3 calls  (extract, then link+tag in parallel)
  + 1 optional cross-link call when candidates exist

Dedup strategy (two tiers):
  Tier 1 — content_hash:   exact SHA-256 match on distilled text (re-ingestion guard)
  Tier 2 — canonical_hash: structural match on normalized canonical JSON (cross-source)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.atomizer import atomize_and_distill_chunks
from backend.compiler.linker import cross_link_atoms, expand_domains, link_atoms
from backend.compiler.tagger import mask_to_domains, tag_atoms
from backend.config import CROSS_LINK_SIMILARITY_THRESHOLD, CROSS_LINK_TOP_K
from backend.engine.embeddings import embed_texts
from backend.models.atoms import Atom, AtomSource, Source


async def fetch_cross_link_candidates(
    db: AsyncSession,
    new_atom_ids: list[uuid.UUID],
    new_embeddings: list[list[float]],
    new_domains: list[list[str]],
) -> list[Atom]:
    """Fetch existing atoms that are good cross-link candidates for new atoms.

    For each new atom, expands its domains one hop via DOMAIN_GROUPS, then
    queries existing atoms within those domains ordered by cosine similarity.
    Returns a deduplicated list of candidates above CROSS_LINK_SIMILARITY_THRESHOLD.
    """
    candidates: dict[uuid.UUID, Atom] = {}

    for embedding, domains in zip(new_embeddings, new_domains):
        expanded = expand_domains(domains)
        if not expanded:
            continue

        stmt = (
            select(Atom)
            .where(
                Atom.dense_vec.cosine_distance(embedding)
                <= (1 - CROSS_LINK_SIMILARITY_THRESHOLD)
            )
            .where(Atom.domain.overlap(list(expanded)))
            .order_by(Atom.dense_vec.cosine_distance(embedding))
            .limit(CROSS_LINK_TOP_K)
        )
        if new_atom_ids:
            stmt = stmt.where(Atom.id.not_in(new_atom_ids))

        result = await db.execute(stmt)
        for atom in result.scalars().all():
            if atom.id not in candidates:
                candidates[atom.id] = atom

    return list(candidates.values())


async def compile_source(
    db: AsyncSession,
    source: Source,
    chunks_text: list[str],
) -> dict:
    """Run the full compiler pipeline on raw text chunks.

    Stages:
    1+2. Extract  — one LLM call per chunk: atomize + distill merged
    3.   Embed    — dense vectors via sentence-transformers
    4+5. Link+Tag — parallel LLM calls (independent of each other)
    6.   Index    — write to DB with two-tier dedup (2 batch SELECTs, not N)
    7.   Cross-link — LLM links new atoms to semantically similar existing atoms
    """
    if not chunks_text:
        return {"atoms_created": 0}

    # ── Stages 1+2: Extract (atomize + distill merged into one LLM call per chunk) ──
    extracted = await atomize_and_distill_chunks(chunks_text)
    if not extracted:
        return {"atoms_created": 0}

    raw_kinds = [item["kind"] for item in extracted]
    distilled_contents = [item["content"] for item in extracted]
    canonicals = [item.get("canonical") for item in extracted]

    # ── Stage 3: Embed ──
    embeddings = embed_texts(distilled_contents)

    # ── Stages 4+5: Link + Tag (parallel — neither depends on the other) ──
    link_sets, tags = await asyncio.gather(
        link_atoms(distilled_contents),
        tag_atoms(contents=distilled_contents, kinds=raw_kinds),
    )

    # ── Stage 6: Index (batch dedup — 2 SELECTs instead of 2N) ──
    all_content_hashes = [
        hashlib.sha256(c.encode()).hexdigest() for c in distilled_contents
    ]
    all_canonical_hashes = [
        (
            hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
            if canonical
            else None
        )
        for canonical in canonicals
    ]

    # Batch lookup by content hash
    existing_by_content: dict[str, Atom] = {}
    rows = (
        (
            await db.execute(
                select(Atom).where(Atom.content_hash.in_(all_content_hashes))
            )
        )
        .scalars()
        .all()
    )
    for atom in rows:
        existing_by_content[atom.content_hash] = atom

    # Batch lookup by canonical hash (only for atoms with a canonical form)
    existing_by_canonical: dict[str, Atom] = {}
    canonical_hash_set = [h for h in all_canonical_hashes if h]
    if canonical_hash_set:
        rows = (
            (
                await db.execute(
                    select(Atom).where(Atom.canonical_hash.in_(canonical_hash_set))
                )
            )
            .scalars()
            .all()
        )
        for atom in rows:
            existing_by_canonical[atom.canonical_hash] = atom

    atom_ids: list[uuid.UUID] = []
    atom_objects: list[Atom] = []  # newly created atoms only (not dedup hits)
    now = datetime.now(timezone.utc)

    for content, canonical, content_hash, canonical_hash, embedding, tag in zip(
        distilled_contents,
        canonicals,
        all_content_hashes,
        all_canonical_hashes,
        embeddings,
        tags,
    ):
        # Tier 1: exact content match
        existing = existing_by_content.get(content_hash)
        # Tier 2: structural canonical match
        if existing is None and canonical_hash:
            existing = existing_by_canonical.get(canonical_hash)

        if existing is not None:
            existing.access_mask = existing.access_mask | tag["access_mask"]
            atom_id = existing.id
            is_primary = False
        else:
            atom_id = uuid.uuid4()
            atom = Atom(
                id=atom_id,
                content=content,
                raw_content=content,
                content_hash=content_hash,
                canonical=canonical,
                canonical_hash=canonical_hash,
                kind=tag["kind"],
                dense_vec=embedding,
                domain=tag["domain"],
                freshness=now,
                confidence=1.0,
                access_mask=tag["access_mask"],
                links=[],
                compiled_at=now,
                version=1,
            )
            db.add(atom)
            atom_objects.append(atom)
            is_primary = True

        atom_ids.append(atom_id)
        db.add(AtomSource(atom_id=atom_id, source_id=source.id, is_primary=is_primary))

    # Resolve within-source links on new atoms
    id_to_pos = {atom_id: i for i, atom_id in enumerate(atom_ids)}
    for atom in atom_objects:
        pos = id_to_pos[atom.id]
        atom.links = [
            {
                "target_id": str(atom_ids[link["target_index"]]),
                "relation": link["relation"],
            }
            for link in link_sets[pos]
            if 0 <= link["target_index"] < len(atom_ids)
        ]

    await db.flush()

    # ── Stage 7: Cross-link (new atoms ↔ existing atoms from other sources) ──
    cross_links_added = 0
    if atom_objects:
        id_to_idx = {atom_id: i for i, atom_id in enumerate(atom_ids)}
        new_embeddings = [embeddings[id_to_idx[a.id]] for a in atom_objects]
        new_domains = [tags[id_to_idx[a.id]]["domain"] for a in atom_objects]

        candidates = await fetch_cross_link_candidates(
            db=db,
            new_atom_ids=[a.id for a in atom_objects],
            new_embeddings=new_embeddings,
            new_domains=new_domains,
        )

        if candidates:
            cl_sets = await cross_link_atoms(
                new_contents=[a.content for a in atom_objects],
                existing_contents=[c.content for c in candidates],
            )

            for atom, atom_cl in zip(atom_objects, cl_sets):
                existing_targets = {lnk["target_id"] for lnk in (atom.links or [])}
                for cl in atom_cl:
                    target_id = str(candidates[cl["existing_index"]].id)
                    if target_id not in existing_targets:
                        atom.links = (atom.links or []) + [
                            {"target_id": target_id, "relation": cl["relation"]}
                        ]
                        existing_targets.add(target_id)
                        cross_links_added += 1

            await db.flush()

    source_domains = mask_to_domains(tags[0]["access_mask"]) if tags else []

    return {
        "atoms_created": len(atom_objects),
        "cross_links_added": cross_links_added,
        "kinds": _count_kinds(atom_objects),
        "domains": source_domains,
    }


def _count_kinds(atoms: list[Atom]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for atom in atoms:
        counts[atom.kind] = counts.get(atom.kind, 0) + 1
    return counts
