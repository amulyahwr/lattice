"""Linker — identify relationships between atoms.

Evolved from engine/graph.py. Instead of writing Entity/Relationship rows,
sets links[] on atoms as JSONB. Uses entity overlap and co-occurrence to
detect causal, temporal, hierarchical, and topical links.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.compiler.atomizer import RawAtom


@dataclass
class AtomLink:
    """A typed link between two atoms."""

    target_index: int  # Index into the atom list
    relation: str  # causal | temporal | hierarchical | topical | contradicts


# Causal connectors
CAUSAL_PATTERN = re.compile(
    r"\b(?:because|therefore|consequently|as a result|due to|caused by|led to|resulting in)\b",
    re.IGNORECASE,
)

# Temporal connectors
TEMPORAL_PATTERN = re.compile(
    r"\b(?:after|before|during|following|prior to|subsequently|then|next|meanwhile|previously)\b",
    re.IGNORECASE,
)

# Contradiction markers
CONTRADICTION_PATTERN = re.compile(
    r"\b(?:however|but|although|despite|contrary|instead|nevertheless|on the other hand|whereas)\b",
    re.IGNORECASE,
)


def _shared_entities(a: RawAtom, b: RawAtom) -> set[str]:
    """Find shared entities between two atoms."""
    set_a = {e.lower() for e in a.entities}
    set_b = {e.lower() for e in b.entities}
    return set_a & set_b


def link_atoms(atoms: list[RawAtom]) -> list[list[dict]]:
    """Identify relationships between atoms.

    Returns a list parallel to atoms, where each entry is a list of
    link dicts: [{"target_id": str, "relation": str}].
    The target_id will be set to the atom's actual UUID later in the pipeline;
    for now we use the index as a placeholder.

    Strategy:
    1. Entity overlap → topical link
    2. Sequential atoms with causal language → causal link
    3. Sequential atoms with temporal language → temporal link
    4. Contradiction markers → contradicts link
    """
    n = len(atoms)
    links: list[list[dict]] = [[] for _ in range(n)]

    for i in range(n):
        # Check pairs within a window
        for j in range(i + 1, min(i + 6, n)):
            shared = _shared_entities(atoms[i], atoms[j])
            combined_text = atoms[i].content + " " + atoms[j].content

            if CONTRADICTION_PATTERN.search(atoms[j].content):
                if shared:
                    links[i].append({"target_index": j, "relation": "contradicts"})
                    links[j].append({"target_index": i, "relation": "contradicts"})
                    continue

            if CAUSAL_PATTERN.search(atoms[j].content):
                if shared or j == i + 1:
                    links[i].append({"target_index": j, "relation": "causal"})
                    continue

            if TEMPORAL_PATTERN.search(atoms[j].content):
                if shared or j == i + 1:
                    links[i].append({"target_index": j, "relation": "temporal"})
                    continue

            # Topical: shared entities
            if shared:
                links[i].append({"target_index": j, "relation": "topical"})
                links[j].append({"target_index": i, "relation": "topical"})

    return links
