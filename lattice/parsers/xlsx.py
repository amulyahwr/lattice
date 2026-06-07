from __future__ import annotations

import re

from lattice.parsers import Segment, _parse_plain

_SHEET_RE = re.compile(r"\[Sheet: ([^\]]+)\]\n?")


def parse_xlsx(text: str, max_chars: int) -> list[Segment]:
    """Split XLSX-extracted text on [Sheet: name] markers. Each sheet = one segment."""
    matches = list(_SHEET_RE.finditer(text))
    if not matches:
        return _parse_plain(text, "xlsx", max_chars)

    segments: list[Segment] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        context = f"Sheet: {match.group(1)}"
        if not content:
            continue
        if len(content) > max_chars:
            for part in _parse_plain(content, "xlsx", max_chars):
                segments.append(Segment(
                    f"s{len(segments)}", part.text, "xlsx",
                    start + part.start, start + part.end, context=context,
                ))
        else:
            segments.append(Segment(
                f"s{len(segments)}", content, "xlsx", start, end, context=context,
            ))
    return segments or _parse_plain(text, "xlsx", max_chars)
