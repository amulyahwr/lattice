"""Shared period and subject extraction utilities.

Used by both the atomizer (ingest-time canonical extraction) and the query
processor (query-time canonical pre-filter population). Keeping extraction
logic in one place ensures ingest and query use the same normalisation rules.
"""

from __future__ import annotations

import re

_QUARTER_ALIASES: dict[str, str] = {
    "first quarter":  "Q1",
    "second quarter": "Q2",
    "third quarter":  "Q3",
    "fourth quarter": "Q4",
    "1st quarter":    "Q1",
    "2nd quarter":    "Q2",
    "3rd quarter":    "Q3",
    "4th quarter":    "Q4",
    "q1": "Q1",
    "q2": "Q2",
    "q3": "Q3",
    "q4": "Q4",
}

_HALF_YEAR_ALIASES: dict[str, str] = {
    "first half":  "H1",
    "second half": "H2",
    "h1": "H1",
    "h2": "H2",
}

_MONTH_NAMES = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
)

# Ordered by specificity — first match wins.
_PERIOD_PATTERNS: list[re.Pattern] = [
    # Quarter shorthand: "Q2", "Q3 2024", "Q2-2024"
    re.compile(r"\bq[1-4](?:\s*[-/]?\s*(?:20\d{2}|\d{2}))?\b", re.IGNORECASE),
    # Quarter spelled out: "first quarter", "third quarter of 2024"
    re.compile(
        r"\b(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter"
        r"(?:\s+(?:of\s+)?(?:20\d{2}|\d{2}))?\b",
        re.IGNORECASE,
    ),
    # Half-year shorthand: "H1", "H2 2024"
    re.compile(r"\bh[12](?:\s*[-/]?\s*(?:20\d{2}|\d{2}))?\b", re.IGNORECASE),
    # Half-year spelled out: "first half", "second half of 2024"
    re.compile(
        r"\b(?:first|second)\s+half(?:\s+(?:of\s+)?(?:20\d{2}|\d{2}))?\b",
        re.IGNORECASE,
    ),
    # Month with optional year: "January 2024", "Sep 2024", "in March"
    re.compile(
        r"\b(?:" + "|".join(_MONTH_NAMES) + r")(?:\s+(?:20\d{2}|\d{2}))?\b",
        re.IGNORECASE,
    ),
    # Fiscal year: "FY2024", "FY 2024", "fiscal year 2024"
    re.compile(
        r"\bfy\s*(?:20\d{2}|\d{2})\b|\bfiscal\s+year\s+(?:20\d{2}|\d{2})\b",
        re.IGNORECASE,
    ),
    # Calendar year: standalone four-digit year
    re.compile(r"\b20\d{2}\b"),
    # Relative: "last quarter", "this year", "last month", YTD, MTD, QTD
    re.compile(
        r"\b(?:last|this|current|previous|prior)\s+(?:quarter|month|year|week|fy|fiscal\s+year)\b"
        r"|\byt[d]\b|\bmt[d]\b|\bqt[d]\b"
        r"|\byear[\s-]to[\s-]date\b|\bmonth[\s-]to[\s-]date\b|\bquarter[\s-]to[\s-]date\b",
        re.IGNORECASE,
    ),
]


def extract_period_from_text(text: str) -> str | None:
    """Extract the first temporal period expression from text using regex.

    Returns the raw matched string; pass through normalize_period() for canonical form.
    Ordered by specificity: quarter > half-year > month > fiscal year > year > relative.
    Never raises.
    """
    for pattern in _PERIOD_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def normalize_period(period: str | None) -> str | None:
    """Normalise a period string to a standard form for consistent filtering.

    "q2 2024", "Q2-2024", "second quarter 2024" → "Q2 2024"
    "first half 2024", "H1-2024"               → "H1 2024"
    "january 2024", "Jan 2024"                  → "January 2024"
    "fy2024", "fiscal year 2024"                → "FY 2024"
    """
    if not period:
        return None
    s = period.strip().lower()
    s = re.sub(r"[-/]", " ", s)
    s = re.sub(r"\s+", " ", s)

    for alias, canonical_q in _QUARTER_ALIASES.items():
        if s.startswith(alias):
            remainder = s[len(alias):].strip()
            return f"{canonical_q} {remainder}".strip() if remainder else canonical_q

    for alias, canonical_h in _HALF_YEAR_ALIASES.items():
        if s.startswith(alias):
            remainder = s[len(alias):].strip()
            return f"{canonical_h} {remainder}".strip() if remainder else canonical_h

    fy_match = re.match(r"fy\s*(20\d{2}|\d{2})$", s)
    if fy_match:
        return f"FY {fy_match.group(1)}"

    return period.strip().title()


def normalize_subject(subject: str | None) -> str | None:
    """Normalise a canonical subject to lowercase stripped form.

    "Revenue Growth" → "revenue growth", " ARR " → "arr"
    """
    if not subject:
        return None
    return subject.strip().lower()
