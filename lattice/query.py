from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from lattice.models import Atom

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "was", "are", "were", "be", "been",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "i", "you", "he", "she", "it", "we", "they",
    "my", "your", "his", "her", "its", "our", "their", "this", "that",
    "what", "when", "where", "which", "who", "whom", "how", "why",
    "many", "much", "often", "long", "far", "old",
}

_TEMPORAL_SIGNALS = {
    "when", "last", "first", "date", "time", "ago", "since", "before",
    "after", "recently", "latest", "earliest", "history", "timeline",
    "days", "weeks", "months", "years",
}
_RECOMMENDATION_SIGNALS = {
    "recommend", "recommended", "suggestion", "suggest", "suggested",
    "advice", "advise", "advised", "told", "tell", "said", "tip",
    "propose", "proposed", "mention", "mentioned",
}
_PREFERENCE_SIGNALS = {
    "prefer", "preference", "like", "dislike", "favorite", "favourite",
    "enjoy", "hate", "love", "want", "wish", "rather",
}


class QueryShape(Enum):
    TEMPORAL = "temporal"
    RECOMMENDATION = "recommendation"
    PREFERENCE = "preference"
    FACTUAL = "factual"  # catch-all: no special handling


def _tokenize(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", text.lower()) if w not in _STOPWORDS}


@dataclass
class QueryIntent:
    raw: str
    shape: QueryShape = QueryShape.FACTUAL
    tokens: set[str] = field(default_factory=set)

    @property
    def primary_kind(self) -> str | None:
        """Atom kind prioritized for this query shape. None = no bias."""
        return {
            QueryShape.TEMPORAL: "event",
            QueryShape.RECOMMENDATION: "recommendation",
            QueryShape.PREFERENCE: "preference",
            QueryShape.FACTUAL: None,
        }[self.shape]

    def subject_overlap(self, atom: Atom) -> int:
        return len(self.tokens & _tokenize(atom.subject))

    def is_on_topic(self, atom: Atom) -> bool:
        if not self.tokens:
            return True
        return self.subject_overlap(atom) > 0


def parse_query(query: str) -> QueryIntent:
    tokens = _tokenize(query)
    raw_lower = query.lower()

    # Recommendation check first — "did you tell/suggest/recommend" is specific
    if _signal_match(tokens, _RECOMMENDATION_SIGNALS) or "did you" in raw_lower:
        shape = QueryShape.RECOMMENDATION
    elif _signal_match(tokens, _TEMPORAL_SIGNALS):
        shape = QueryShape.TEMPORAL
    elif _signal_match(tokens, _PREFERENCE_SIGNALS):
        shape = QueryShape.PREFERENCE
    else:
        shape = QueryShape.FACTUAL

    return QueryIntent(raw=query, shape=shape, tokens=tokens)


def _signal_match(tokens: set[str], signals: set[str]) -> bool:
    return bool(tokens & signals)


