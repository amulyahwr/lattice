from __future__ import annotations

import re

from lattice.parsers import Segment, _parse_plain

_TURN_RE = re.compile(
    r"^\s*(user|assistant|system|developer)\s*:", re.IGNORECASE | re.MULTILINE
)


def parse_chat(text: str, max_chars: int) -> list[Segment]:
    turns = list(_TURN_RE.finditer(text))
    if len(text) <= max_chars or not turns:
        return [Segment("s0", text, "chat", 0, len(text), role=_sole_role(turns))]

    segments: list[Segment] = []
    current_start = turns[0].start()

    for turn in turns[1:]:
        if turn.start() - current_start >= max_chars:
            chunk = text[current_start:turn.start()].strip()
            if chunk:
                window = [t for t in turns if current_start <= t.start() < turn.start()]
                segments.append(Segment(
                    f"s{len(segments)}", chunk, "chat",
                    current_start, turn.start(), role=_sole_role(window),
                ))
            current_start = turn.start()

    chunk = text[current_start:].strip()
    if chunk:
        window = [t for t in turns if t.start() >= current_start]
        segments.append(Segment(
            f"s{len(segments)}", chunk, "chat",
            current_start, len(text), role=_sole_role(window),
        ))

    return segments or _parse_plain(text, "chat", max_chars)


def _sole_role(turns: list[re.Match]) -> str | None:
    """Return the role name if all turns share one role, else None."""
    roles = {t.group(1).lower() for t in turns}
    return roles.pop() if len(roles) == 1 else None
