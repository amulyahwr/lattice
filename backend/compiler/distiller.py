"""Distiller — generate concise, token-efficient text per atom.

Evolved from engine/summarize.py. For MVP, uses extractive methods
(no external LLM dependency). The raw_content is preserved; content
gets the distilled version.
"""

import re
from collections import Counter


def distill(text: str, max_length: int = 300) -> str:
    """Distill a piece of text into a concise version.

    For MVP this is extractive — removes boilerplate and noise,
    keeps signal. LLM-based distillation comes later.
    """
    # Clean whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) <= max_length:
        return text

    # Remove common filler phrases
    fillers = [
        r"\b(?:it is worth noting that|it should be noted that)\b",
        r"\b(?:as mentioned (?:earlier|above|before|previously))\b",
        r"\b(?:in this (?:regard|context|case))\b",
        r"\b(?:please note that|note that)\b",
        r"\b(?:basically|essentially|fundamentally)\b",
    ]
    cleaned = text
    for filler in fillers:
        cleaned = re.sub(filler, "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) <= max_length:
        return cleaned

    # Truncate at a sentence boundary
    truncated = cleaned[:max_length]
    last_period = truncated.rfind(".")
    if last_period > max_length * 0.5:
        return truncated[: last_period + 1].strip()

    return truncated.strip()


def distill_batch(texts: list[str], max_length: int = 300) -> list[str]:
    """Distill a batch of texts."""
    return [distill(t, max_length) for t in texts]


def extract_key_phrases(text: str, top_n: int = 5) -> list[str]:
    """Extract the most frequent meaningful phrases (bigrams).

    Carried forward from summarize.py for domain suggestion support.
    """
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())

    stop_words = {
        "the", "and", "for", "are", "but", "not", "you", "all",
        "can", "has", "her", "was", "one", "our", "out", "his",
        "had", "how", "its", "may", "new", "now", "old", "see",
        "way", "who", "did", "get", "let", "say", "she", "too",
        "use", "this", "that", "with", "have", "from", "they",
        "been", "will", "more", "when", "what", "your", "than",
        "them", "some", "other", "into", "also", "each", "which",
        "their", "there", "about", "would", "these", "could",
        "should", "being", "after", "before", "between", "through",
    }
    words = [w for w in words if w not in stop_words]

    bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
    counter = Counter(bigrams)

    return [phrase.title() for phrase, _ in counter.most_common(top_n)]
