from __future__ import annotations

from lattice.parsers import Segment, _parse_plain


def parse_code(text: str, max_chars: int) -> list[Segment]:
    # Symbol-boundary splitting not yet implemented; falls back to plain windowing.
    # Future: split at def/class boundaries for finer-grained extraction.
    return _parse_plain(text, "code", max_chars)
