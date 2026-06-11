"""Multi-turn query reformulation.

is_followup(query) detects anaphoric / short follow-up questions.
reformulate(query, history, cfg) rewrites them into self-contained queries
using the last N Q&A pairs as context. PII-safe: redact before LLM, restore after.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from lattice.llm import complete, resolve_model
from lattice.privacy import EntityRedactor, is_active as _pii_active

if TYPE_CHECKING:
    from lattice.config import Config

# Short queries that are almost always follow-ups regardless of the heuristic.
_FOLLOWUP_PHRASES: frozenset[str] = frozenset({
    "why", "why?",
    "how", "how?",
    "more", "more?",
    "what else", "what else?",
    "and then", "and then?",
    "go on", "go on.",
    "elaborate", "elaborate.",
    "tell me more", "tell me more.",
    "when", "when?",
    "where", "where?",
    "who", "who?",
    "really", "really?",
    "explain", "explain.",
    "continue", "continue.",
})

# Pronouns that signal the query refers to something mentioned earlier.
_ANAPHORIC_TOKENS: frozenset[str] = frozenset({
    "that", "it", "those", "them", "this",
    "the same", "there", "then", "its", "their",
    "he", "she", "they", "his", "her",
})

_REFORMULATION_SYSTEM = (
    "You are a query reformulation assistant. "
    "Given a conversation and a follow-up question, rewrite the follow-up as a "
    "complete, self-contained question that can be understood and answered without "
    "any conversation context. Fix any spelling or grammar errors. "
    "Return ONLY the rewritten question — no explanation, no punctuation changes beyond "
    "fixing errors, no added commentary."
)


def is_followup(query: str) -> bool:
    """Return True if query is likely a follow-up to a prior turn."""
    q = query.strip()
    q_lower = q.lower()

    # Fast-path: known short followup phrases
    if q_lower in _FOLLOWUP_PHRASES:
        return True

    tokens = q_lower.split()

    # Short query (< 6 words) is a strong signal
    if len(tokens) < 6:
        # Check for any anaphoric token
        for tok in tokens:
            if tok in _ANAPHORIC_TOKENS:
                return True
        # Check for "the same" multi-token
        if "the same" in q_lower:
            return True

    # Any length: explicit anaphoric token present
    for tok in tokens:
        if tok in _ANAPHORIC_TOKENS:
            return True
    if "the same" in q_lower:
        return True

    # No proper nouns beyond sentence start (all words lowercase after first)
    words = q.split()
    if len(words) > 1:
        body_words = words[1:]  # skip first word (may be capitalised at sentence start)
        has_proper_noun = any(
            w[0].isupper() for w in body_words if w and w[0].isalpha()
        )
        if not has_proper_noun and len(words) < 8:
            return True

    return False


def reformulate(query: str, history: list[dict], cfg: "Config") -> str:
    """Rewrite a follow-up query into a self-contained question.

    history: list of {question, answer} dicts, most recent last.
    Returns the reformulated query, or the original if reformulation fails/adds no value.
    """
    if not history:
        return query

    # Build conversation context (with PII redaction when using cloud provider)
    redactor = EntityRedactor()
    texts = []
    for turn in history:
        texts.append(turn.get("question", ""))
        texts.append(turn.get("answer", ""))
    texts.append(query)

    if _pii_active(cfg):
        redacted_texts, entity_map = redactor.redact_batch(texts, cfg)
    else:
        redacted_texts, entity_map = texts, {}

    # Rebuild history from redacted texts
    redacted_history = []
    for i, turn in enumerate(history):
        redacted_history.append({
            "question": redacted_texts[i * 2],
            "answer": redacted_texts[i * 2 + 1],
        })
    redacted_query = redacted_texts[-1]

    context_lines = []
    for turn in redacted_history:
        context_lines.append(f"User: {turn['question']}")
        context_lines.append(f"Assistant: {turn['answer']}")
    context_lines.append(f"Follow-up: {redacted_query}")
    context = "\n".join(context_lines)

    model = resolve_model(cfg, cfg.reformulation_model or cfg.ingest_model)
    messages = [
        {"role": "system", "content": _REFORMULATION_SYSTEM},
        {"role": "user", "content": context},
    ]

    try:
        raw = complete(messages, cfg, model=model)
    except Exception:
        return query

    result = raw.strip().strip('"').strip("'")

    # Restore PII in the reformulated query
    if entity_map:
        result = redactor.restore(result, entity_map)

    # Sanity checks — fall back to original if result is bad
    if not result:
        return query
    if result.lower() == query.lower():
        return query
    if len(result) > len(query) * 4:
        return query

    return result
