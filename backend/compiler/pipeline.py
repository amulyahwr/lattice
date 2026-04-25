"""Compiler Pipeline — orchestrates atomize → distill → embed → link → tag → index.

Synchronous for MVP. Takes raw text chunks from a connector and runs them
through each stage, producing atoms and frames in the database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.compiler.atomizer import atomize_chunks
from backend.compiler.distiller import distill
from backend.compiler.linker import link_atoms
from backend.compiler.tagger import tag_atoms
from backend.engine.embeddings import embed_texts
from backend.models.atoms import Atom, Source
from backend.serving.frame_builder import build_frames_for_source


async def compile_source(
    db: AsyncSession,
    source: Source,
    chunks_text: list[str],
) -> dict:
    """Run the full compiler pipeline on raw text chunks.

    Stages:
    1. Atomize — break into atomic facts
    2. Distill — generate concise text per atom
    3. Embed — generate dense vectors
    4. Link — identify relationships between atoms
    5. Tag — assign access_mask, domains, kind
    6. Index — write atoms to DB, build/update frames

    Returns compilation stats.
    """
    if not chunks_text:
        return {"atoms_created": 0, "frames_created": 0}

    # ── Stage 1: Atomize ──
    raw_atoms = atomize_chunks(chunks_text)
    if not raw_atoms:
        return {"atoms_created": 0, "frames_created": 0}

    # ── Stage 2: Distill ──
    distilled_contents = [distill(atom.content) for atom in raw_atoms]

    # ── Stage 3: Embed ──
    embeddings = embed_texts(distilled_contents)

    # ── Stage 4: Link ──
    link_sets = link_atoms(raw_atoms)

    # ── Stage 5: Tag ──
    tags = tag_atoms(
        contents=distilled_contents,
        kinds=[atom.kind for atom in raw_atoms],
        source_classification=source.classification or "internal",
        source_domains=source.domains or [],
    )

    # ── Stage 6: Index ──
    atom_ids: list[uuid.UUID] = []
    atom_objects: list[Atom] = []
    now = datetime.now(timezone.utc)

    for i, (raw, content, embedding, tag) in enumerate(
        zip(raw_atoms, distilled_contents, embeddings, tags)
    ):
        atom_id = uuid.uuid4()
        atom_ids.append(atom_id)

        atom = Atom(
            id=atom_id,
            content=content,
            raw_content=raw.content,
            kind=tag["kind"],
            dense_vec=embedding,
            domain=tag["domain"],
            freshness=now,
            confidence=1.0,
            access_mask=tag["access_mask"],
            links=[],  # Will be resolved after all IDs are assigned
            source_id=source.id,
            compiled_at=now,
            version=1,
        )
        atom_objects.append(atom)

    # Resolve links: replace target_index with actual UUIDs
    for i, atom in enumerate(atom_objects):
        resolved_links = []
        for link in link_sets[i]:
            target_idx = link["target_index"]
            if 0 <= target_idx < len(atom_ids):
                resolved_links.append({
                    "target_id": str(atom_ids[target_idx]),
                    "relation": link["relation"],
                })
        atom.links = resolved_links

    # Write atoms to DB
    for atom in atom_objects:
        db.add(atom)

    await db.flush()

    # Build frames from the new atoms
    frames_created = await build_frames_for_source(
        db=db,
        source=source,
        atoms=atom_objects,
    )

    return {
        "atoms_created": len(atom_objects),
        "frames_created": frames_created,
        "kinds": _count_kinds(atom_objects),
        "domains": _collect_domains(atom_objects),
    }


def _count_kinds(atoms: list[Atom]) -> dict[str, int]:
    """Count atoms by kind."""
    counts: dict[str, int] = {}
    for atom in atoms:
        counts[atom.kind] = counts.get(atom.kind, 0) + 1
    return counts


def _collect_domains(atoms: list[Atom]) -> list[str]:
    """Collect unique domains across atoms."""
    domains: set[str] = set()
    for atom in atoms:
        if atom.domain:
            domains.update(atom.domain)
    return sorted(domains)
