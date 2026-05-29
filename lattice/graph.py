from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import networkx as nx

if TYPE_CHECKING:
    from lattice.models import Atom

from lattice.util import _normalized_subject, _write_json_atomic, write_file_atomic


class LatticeGraph:
    def __init__(self) -> None:
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()
        # index: normalized_subject -> set of atom node ids
        self._subject_index: dict[str, set[str]] = {}
        # index: normalized_content_hash -> set of atom node ids
        self._hash_index: dict[str, set[str]] = {}

    @property
    def graph(self) -> nx.MultiDiGraph:
        return self._g

    # ── mutation ──────────────────────────────────────────────────────────

    def add_atom(self, atom: "Atom") -> None:
        atom_node = f"atom:{atom.atom_id}"

        # Upsert atom node
        self._g.add_node(
            atom_node,
            type="atom",
            subject=atom.subject,
            kind=atom.kind,
            is_superseded=atom.is_superseded,
            ingested_at=atom.ingested_at.isoformat() if atom.ingested_at else None,
            observed_at=atom.observed_at.isoformat() if atom.observed_at else None,
            source_id=atom.source_id,
            session_id=atom.session_id,
            segment_id=atom.segment_id,
            normalized_content_hash=atom.normalized_content_hash,
        )

        # Source node
        if atom.source_id:
            source_node = f"source:{atom.source_id}"
            self._g.add_node(source_node, type="source")

        # Segment node
        if atom.segment_id:
            container_id = atom.source_id or atom.session_id
            if container_id:
                segment_node = f"segment:{container_id}:{atom.segment_id}"
                self._g.add_node(segment_node, type="segment")
                if atom.source_id:
                    source_node = f"source:{atom.source_id}"
                    if not self._g.has_edge(source_node, segment_node):
                        self._g.add_edge(source_node, segment_node, type="source_contains_segment")
                if not self._g.has_edge(segment_node, atom_node):
                    self._g.add_edge(segment_node, atom_node, type="segment_contains_atom")

        # Subject node + edge
        norm = _normalized_subject(atom.subject)
        if norm:
            subject_node = f"subject:{norm}"
            self._g.add_node(subject_node, type="subject", normalized=norm)
            if not self._g.has_edge(atom_node, subject_node):
                self._g.add_edge(atom_node, subject_node, type="atom_has_subject")

            # same_subject_as edges to existing atoms with same subject
            existing = self._subject_index.get(norm, set())
            for other_node in existing:
                if other_node != atom_node:
                    if not self._g.has_edge(atom_node, other_node):
                        self._g.add_edge(atom_node, other_node, type="same_subject_as")
                    if not self._g.has_edge(other_node, atom_node):
                        self._g.add_edge(other_node, atom_node, type="same_subject_as")

            if norm not in self._subject_index:
                self._subject_index[norm] = set()
            self._subject_index[norm].add(atom_node)

        # same_hash edges
        if atom.normalized_content_hash:
            existing_hashes = self._hash_index.get(atom.normalized_content_hash, set())
            for other_node in existing_hashes:
                if other_node != atom_node and not self._g.has_edge(atom_node, other_node):
                    self._g.add_edge(atom_node, other_node, type="same_hash")
            if atom.normalized_content_hash not in self._hash_index:
                self._hash_index[atom.normalized_content_hash] = set()
            self._hash_index[atom.normalized_content_hash].add(atom_node)

        # Update is_superseded on existing node if atom was already present
        self._g.nodes[atom_node]["is_superseded"] = atom.is_superseded

    def mark_superseded(self, old_id: str, new_id: str) -> None:
        old_node = f"atom:{old_id}"
        new_node = f"atom:{new_id}"
        if old_node in self._g.nodes:
            self._g.nodes[old_node]["is_superseded"] = True
        if new_node in self._g.nodes and old_node in self._g.nodes:
            existing = self._g.get_edge_data(new_node, old_node) or {}
            if not any(d.get("type") == "supersedes" for d in existing.values()):
                self._g.add_edge(new_node, old_node, type="supersedes")

    def rebuild(self, atoms: list["Atom"]) -> None:
        self._g.clear()
        self._subject_index.clear()
        self._hash_index.clear()
        for atom in atoms:
            self.add_atom(atom)
        # Add supersedes edges from atom fields
        for atom in atoms:
            if atom.supersedes:
                new_node = f"atom:{atom.atom_id}"
                old_node = f"atom:{atom.supersedes}"
                if new_node in self._g.nodes and old_node in self._g.nodes:
                    if not self._g.has_edge(new_node, old_node):
                        self._g.add_edge(new_node, old_node, type="supersedes")

    # ── persistence ───────────────────────────────────────────────────────

    def save(self, lattice_dir: Path) -> None:
        graph_dir = lattice_dir / "graph"
        graph_dir.mkdir(parents=True, exist_ok=True)

        nodes_lines = []
        for node_id, attrs in self._g.nodes(data=True):
            nodes_lines.append(json.dumps({"id": node_id, **attrs}))

        edges_lines = []
        for src, dst, key, attrs in self._g.edges(data=True, keys=True):
            edges_lines.append(json.dumps({"src": src, "dst": dst, "key": key, **attrs}))

        atom_count = sum(1 for n, d in self._g.nodes(data=True) if d.get("type") == "atom")
        manifest = {
            "version": 1,
            "atom_count": atom_count,
            "edge_count": self._g.number_of_edges(),
            "built_at": datetime.now(timezone.utc).isoformat(),
        }

        _write_lines_atomic(graph_dir / "nodes.jsonl", nodes_lines)
        _write_lines_atomic(graph_dir / "edges.jsonl", edges_lines)
        _write_json_atomic(graph_dir / "manifest.json", manifest)

    @classmethod
    def load(cls, lattice_dir: Path) -> "LatticeGraph":
        graph_dir = lattice_dir / "graph"
        lg = cls()

        nodes_path = graph_dir / "nodes.jsonl"
        if nodes_path.exists():
            for line in nodes_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                node_id = data.pop("id")
                lg._g.add_node(node_id, **data)
                # Rebuild indexes
                if data.get("type") == "atom":
                    norm = data.get("normalized_subject") or _normalized_subject(data.get("subject", ""))
                    if norm:
                        lg._subject_index.setdefault(norm, set()).add(node_id)
                    h = data.get("normalized_content_hash")
                    if h:
                        lg._hash_index.setdefault(h, set()).add(node_id)

        edges_path = graph_dir / "edges.jsonl"
        if edges_path.exists():
            for line in edges_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                src = data.pop("src")
                dst = data.pop("dst")
                data.pop("key", None)
                lg._g.add_edge(src, dst, **data)

        return lg

    # Semantic edges carry meaning between atoms — traverse at full depth.
    # Structural edges (source/segment containment) encode provenance, not
    # relevance. Capped at depth 2: seeds → segment → same-segment siblings.
    # Beyond depth 2, structural edges explode to the entire source document.
    _SEMANTIC_EDGE_TYPES = frozenset({"same_subject_as", "supersedes", "same_hash"})
    _STRUCTURAL_DEPTH_CAP = 2

    def _typed_neighbors(self, node: str) -> list[tuple[str, bool]]:
        """Return (neighbor_node, is_structural) for all edges from node."""
        neighbors = []
        for _, nbr, data in self._g.out_edges(node, data=True):
            neighbors.append((nbr, data.get("type") not in self._SEMANTIC_EDGE_TYPES))
        for src, _, data in self._g.in_edges(node, data=True):
            neighbors.append((src, data.get("type") not in self._SEMANTIC_EDGE_TYPES))
        return neighbors

    def bfs_expand(
        self,
        seed_atom_ids: list[str],
        max_depth: int = 4,
        max_atoms: int = 60,
    ) -> list[str]:
        """Hybrid BFS: semantic edges at full depth, structural edges capped at depth 2.

        Semantic edges (same_subject_as, supersedes, same_hash) traverse up to
        max_depth — needed for supersession chains and subject clustering.

        Structural edges (source_contains_segment, segment_contains_atom,
        atom_has_subject) are limited to depth 2: seeds → segment → same-segment
        siblings only. Depth 3+ via structural edges explodes to the entire
        source document and is blocked.
        """
        from collections import deque

        visited: set[str] = set()
        result: list[str] = []
        # Queue: (node, semantic_depth, structural_depth)
        queue: deque[tuple[str, int, int]] = deque()

        for aid in seed_atom_ids:
            node = f"atom:{aid}"
            if node in self._g.nodes and node not in visited:
                visited.add(node)
                result.append(aid)
                queue.append((node, 0, 0))
                if len(result) >= max_atoms:
                    return result

        while queue:
            node, sem_depth, struct_depth = queue.popleft()

            for nbr, is_structural in self._typed_neighbors(node):
                if nbr in visited:
                    continue

                if is_structural:
                    if struct_depth >= self._STRUCTURAL_DEPTH_CAP:
                        continue
                    new_sem, new_struct = sem_depth, struct_depth + 1
                else:
                    if sem_depth >= max_depth:
                        continue
                    new_sem, new_struct = sem_depth + 1, struct_depth

                visited.add(nbr)
                if nbr not in self._g.nodes:
                    continue
                if self._g.nodes[nbr].get("type") == "atom":
                    result.append(nbr[len("atom:"):])
                    if len(result) >= max_atoms:
                        return result
                queue.append((nbr, new_sem, new_struct))

        return result

    def is_stale(self, lattice_dir: Path, atom_count: int) -> bool:
        manifest_path = lattice_dir / "graph" / "manifest.json"
        if not manifest_path.exists():
            return True
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return manifest.get("atom_count", -1) != atom_count
        except Exception:
            return True


# ── file helpers ──────────────────────────────────────────────────────────

def _write_lines_atomic(path: Path, lines: list[str]) -> None:
    text = "\n".join(lines)
    if lines:
        text += "\n"
    write_file_atomic(path, text)
