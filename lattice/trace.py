"""STORY-041 — End-to-end query trace.

QueryTrace captures one query pipeline run: what BM25 found, what dense search
added, what BFS expanded, what synthesis cited, and how long each stage took.

Enabled by LATTICE_TRACE=true (default false). When disabled, QueryTrace objects
are never created — zero overhead on the hot path.

Query text is never stored. Only SHA-1 prefixes (16 hex chars) are recorded.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lattice.config import Config


def _sha1(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


@dataclass
class QueryTrace:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    query_hash: str = ""
    channel: str = "web"
    reformulated_hash: str | None = None
    bm25_seeds: list[dict] = field(default_factory=list)   # [{atom_id, score}]
    dense_hits: list[dict] = field(default_factory=list)   # [{atom_id}]
    bfs_expanded: list[str] = field(default_factory=list)
    final_atoms: list[str] = field(default_factory=list)
    cited_atoms: list[str] = field(default_factory=list)
    stage_ms: dict = field(default_factory=lambda: {"selection": 0, "reformulation": 0, "synthesis": 0})
    no_answer: bool = False
    pii_protected: bool = False

    @classmethod
    def create(cls, query: str, channel: str = "web") -> "QueryTrace":
        return cls(query_hash=_sha1(query), channel=channel)

    def set_reformulated(self, reformulated: str) -> None:
        self.reformulated_hash = _sha1(reformulated)


class TraceWriter:
    def __init__(self, cfg: "Config") -> None:
        self._path = cfg.lattice_dir / "traces.jsonl"

    def write(self, trace: QueryTrace) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace.__dict__) + "\n")

    def read(self, trace_id: str) -> dict | None:
        if not self._path.exists():
            return None
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("trace_id") == trace_id:
                        return rec
                except json.JSONDecodeError:
                    continue
        return None
