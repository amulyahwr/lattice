from __future__ import annotations

import re

from lattice.parsers import Segment, _parse_plain

_SLIDE_RE = re.compile(r"\[Slide (\d+)\]\n?")


def parse_pptx(text: str, max_chars: int) -> list[Segment]:
    """Split PPTX-extracted text on [Slide N] markers. Each slide = one segment."""
    matches = list(_SLIDE_RE.finditer(text))
    if not matches:
        return _parse_plain(text, "pptx", max_chars)

    segments: list[Segment] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        context = f"Slide {match.group(1)}"
        if not content:
            continue
        if len(content) > max_chars:
            for part in _parse_plain(content, "pptx", max_chars):
                segments.append(Segment(
                    f"s{len(segments)}", part.text, "pptx",
                    start + part.start, start + part.end, context=context,
                ))
        else:
            segments.append(Segment(
                f"s{len(segments)}", content, "pptx", start, end, context=context,
            ))
    return segments or _parse_plain(text, "pptx", max_chars)
