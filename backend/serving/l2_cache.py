"""L2 Frame Cache — in-memory dict for MVP.

Pre-warmed frames keyed by domain. Provides ~5ms serving for cache hits.
Redis-backed version comes in Phase 2.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID


@dataclass
class CachedFrame:
    """A frame in the L2 cache."""

    frame_id: UUID
    name: str
    domain: str
    atom_ids: list[UUID]
    atom_contents: list[str]  # Pre-serialized atom content
    atom_access_masks: list[int]
    token_count: int
    access_mask: int  # Union of all atom masks
    cached_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    hit_count: int = 0


class L2Cache:
    """In-memory frame cache keyed by domain."""

    def __init__(self, max_frames: int = 1000):
        self._cache: dict[str, list[CachedFrame]] = {}  # domain -> frames
        self._lock = threading.Lock()
        self._max_frames = max_frames
        self._total_hits = 0
        self._total_misses = 0

    def put(self, frame: CachedFrame) -> None:
        """Cache a frame."""
        with self._lock:
            domain = frame.domain
            if domain not in self._cache:
                self._cache[domain] = []
            # Replace existing frame with same ID
            self._cache[domain] = [
                f for f in self._cache[domain] if f.frame_id != frame.frame_id
            ]
            self._cache[domain].append(frame)

    def get_by_domain(self, domain: str, role_mask: int) -> CachedFrame | None:
        """Find a cached frame matching domain and role mask.

        Returns the frame if the agent's role_mask has access (AND check).
        """
        with self._lock:
            frames = self._cache.get(domain, [])
            for frame in frames:
                if frame.access_mask & role_mask:
                    frame.hit_count += 1
                    self._total_hits += 1
                    return frame
            self._total_misses += 1
            return None

    def invalidate_domain(self, domain: str) -> None:
        """Remove all frames for a domain."""
        with self._lock:
            self._cache.pop(domain, None)

    def invalidate_all(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()

    @property
    def stats(self) -> dict:
        """Cache statistics."""
        with self._lock:
            total_frames = sum(len(v) for v in self._cache.values())
            total_requests = self._total_hits + self._total_misses
            return {
                "total_frames": total_frames,
                "domains": list(self._cache.keys()),
                "total_hits": self._total_hits,
                "total_misses": self._total_misses,
                "hit_rate": (
                    self._total_hits / total_requests if total_requests > 0 else 0.0
                ),
            }


# Global singleton
l2_cache = L2Cache()
