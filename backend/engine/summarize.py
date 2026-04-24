"""Extractive summarization — generate source summaries without external LLM calls."""

import re
from collections import Counter


def extractive_summary(chunks_text: list[str], max_length: int = 500) -> str:
    """
    Generate a summary from chunk texts using extractive methods.

    Strategy:
    1. Take the opening text (usually most informative)
    2. Extract key phrases by frequency
    3. Combine into a coherent summary
    """
    if not chunks_text:
        return ""

    full_text = " ".join(chunks_text)

    # Clean up whitespace
    full_text = re.sub(r"\s+", " ", full_text).strip()

    if len(full_text) <= max_length:
        return full_text

    # Take the opening (first ~60% of budget)
    opening_budget = int(max_length * 0.6)
    opening = full_text[:opening_budget]

    # Find a sentence boundary to cut cleanly
    last_period = opening.rfind(".")
    if last_period > opening_budget * 0.5:
        opening = opening[: last_period + 1]

    # Extract key phrases from the full text for the remaining budget
    keywords = _extract_key_phrases(full_text, top_n=5)
    if keywords:
        keyword_section = " Key topics: " + ", ".join(keywords) + "."
    else:
        keyword_section = ""

    summary = opening + keyword_section
    return summary[:max_length].strip()


def _extract_key_phrases(text: str, top_n: int = 5) -> list[str]:
    """Extract the most frequent meaningful phrases (2-3 word ngrams)."""
    # Simple word tokenization
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())

    # Remove common stop words
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

    # Bigrams
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    counter = Counter(bigrams)

    # Return most common, title-cased
    return [phrase.title() for phrase, _ in counter.most_common(top_n)]


def suggest_domains(summary: str, source_type: str) -> list[str]:
    """Suggest domain tags based on summary content."""
    summary_lower = summary.lower()

    domain_keywords = {
        "finance": ["revenue", "financial", "profit", "budget", "ebitda", "forecast", "earnings", "fiscal"],
        "engineering": ["api", "architecture", "system", "code", "deploy", "infrastructure", "technical", "database"],
        "legal": ["contract", "compliance", "regulation", "liability", "agreement", "policy", "legal", "law"],
        "sales": ["customer", "pipeline", "deal", "crm", "prospect", "quota", "sales"],
        "marketing": ["campaign", "brand", "engagement", "seo", "content", "audience", "marketing"],
        "hr": ["employee", "hiring", "onboarding", "performance review", "benefits", "compensation"],
        "product": ["roadmap", "feature", "user experience", "product", "release", "sprint"],
        "security": ["vulnerability", "threat", "encryption", "access control", "security", "breach"],
        "research": ["analysis", "study", "findings", "methodology", "data", "research"],
    }

    matched = []
    for domain, keywords in domain_keywords.items():
        score = sum(1 for kw in keywords if kw in summary_lower)
        if score >= 2:
            matched.append(domain)

    return matched if matched else ["general"]
