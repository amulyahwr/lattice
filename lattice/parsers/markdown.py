from __future__ import annotations

import re

from lattice.parsers import Segment, _parse_plain

_HEADING_RE = re.compile(r"^#{1,6}\s+.+$", re.MULTILINE)


def parse_markdown(text: str, max_chars: int) -> list[Segment]:
    headings = list(_HEADING_RE.finditer(text))
    if len(text) <= max_chars or not headings:
        return _parse_plain(text, "markdown", max_chars)

    segments: list[Segment] = []
    for idx, match in enumerate(headings):
        start = match.start()
        end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
        chunk = text[start:end].strip()
        heading = match.group(0).strip()
        if len(chunk) > max_chars:
            for part in _parse_plain(chunk, "markdown", max_chars):
                segments.append(Segment(
                    f"s{len(segments)}", part.text, "markdown",
                    start + part.start, start + part.end, context=heading,
                ))
        elif chunk:
            segments.append(Segment(
                f"s{len(segments)}", chunk, "markdown", start, end, context=heading,
            ))
    return segments
