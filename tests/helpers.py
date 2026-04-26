"""Shared test helpers — not fixtures, just plain functions importable anywhere."""

from __future__ import annotations

import math


def make_vector(seed: int = 0) -> list[float]:
    """Deterministic 384-dim vector seeded by an integer."""
    return [(math.sin(i + seed) + 1) / 2 for i in range(384)]


def chat_sequence(*responses: str):
    """
    Returns an async side_effect callable that yields responses in order.
    Use with mock_chat.side_effect = chat_sequence(resp1, resp2, ...).

    Raises StopIteration-wrapped RuntimeError if called more times than
    responses provided (helps catch unexpected extra LLM calls in tests).
    """
    it = iter(responses)

    async def _side_effect(system: str, user: str, **kw) -> str:
        try:
            return next(it)
        except StopIteration:
            raise RuntimeError(
                "chat() called more times than expected responses supplied to chat_sequence()"
            )

    return _side_effect
