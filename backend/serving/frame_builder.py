"""Frame Builder — assemble frames from atoms by domain clustering.

Groups atoms by domain, computes token counts, and creates Frame records
in the database. Also populates the L2 cache.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

import tiktoken

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.atoms import Atom, Frame, Source
from backend.serving.l2_cache import CachedFrame, l2_cache

# Use cl100k_base encoding (GPT-4 / Claude compatible)
_enc: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    global _enc
    if _enc is None:
        _enc = tiktoken.get_encoding("cl100k_base")
    return _enc


def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    return len(_get_encoder().encode(text))


async def build_frames_for_source(
    db: AsyncSession,
    source: Source,
    atoms: list[Atom],
) -> int:
    """Build frames from a set of atoms by domain clustering.

    Each unique domain gets a frame containing all atoms tagged with that domain.
    Frames are written to DB and warmed into L2 cache.

    Returns the number of frames created.
    """
    if not atoms:
        return 0

    # Group atoms by domain
    domain_atoms: dict[str, list[Atom]] = defaultdict(list)
    for atom in atoms:
        domains = atom.domain or ["general"]
        for domain in domains:
            domain_atoms[domain].append(atom)

    frames_created = 0
    now = datetime.now(timezone.utc)

    for domain, domain_atom_list in domain_atoms.items():
        # Compute token count
        total_tokens = sum(count_tokens(a.content) for a in domain_atom_list)

        # Compute union access mask
        union_mask = 0
        for a in domain_atom_list:
            union_mask |= a.access_mask

        atom_ids = [a.id for a in domain_atom_list]

        frame = Frame(
            id=uuid.uuid4(),
            name=f"{source.name} — {domain}",
            domain=domain,
            atom_ids=atom_ids,
            token_count=total_tokens,
            access_mask=union_mask,
            last_accessed=now,
            access_count=0,
        )
        db.add(frame)
        frames_created += 1

        # Warm L2 cache
        cached = CachedFrame(
            frame_id=frame.id,
            name=frame.name,
            domain=domain,
            atom_ids=atom_ids,
            atom_contents=[a.content for a in domain_atom_list],
            atom_access_masks=[a.access_mask for a in domain_atom_list],
            token_count=total_tokens,
            access_mask=union_mask,
        )
        l2_cache.put(cached)

    return frames_created
