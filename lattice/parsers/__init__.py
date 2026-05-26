from __future__ import annotations

import os
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    segment_id: str
    text: str
    source_type: str
    start: int
    end: int
    role: str | None = None  # "user"/"assistant"/"system" for chat; None otherwise
    context: str = ""  # nearest heading for markdown


def infer_source_type(text: str, metadata: dict) -> str:
    if metadata.get("source_type"):
        return str(metadata["source_type"])
    if re.search(r"^#{1,6}\s+\S", text, flags=re.MULTILINE):
        return "markdown"
    if re.search(r"^\s*(user|assistant|system|developer)\s*:", text, flags=re.IGNORECASE | re.MULTILINE):
        return "chat"
    if "```" in text or re.search(r"\b(def|class|function|import|from)\s+\w+", text):
        return "code"
    return "plain"


def parse(text: str, source_type: str, max_chars: int | None = None) -> list[Segment]:
    if max_chars is None:
        max_chars = int(os.environ.get("LATTICE_SEGMENT_CHARS", "12000"))
    if source_type == "markdown":
        from lattice.parsers.markdown import parse_markdown
        return parse_markdown(text, max_chars)
    if source_type == "chat":
        from lattice.parsers.chat import parse_chat
        return parse_chat(text, max_chars)
    if source_type == "code":
        from lattice.parsers.code import parse_code
        return parse_code(text, max_chars)
    return _parse_plain(text, source_type, max_chars)


def _parse_plain(text: str, source_type: str, max_chars: int) -> list[Segment]:
    if len(text) <= max_chars:
        return [Segment("s0", text, source_type, 0, len(text))]

    segments: list[Segment] = []
    overlap = min(300, max_chars // 5)
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if boundary > start + max_chars // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            segments.append(Segment(f"s{len(segments)}", chunk, source_type, start, end))
        if end >= len(text):
            break
        start = max(0, end - overlap)
    return segments
