"""HyDE query processor — converts raw queries into k diverse declarative statements.

Generates multiple hypothetical atoms covering different angles of the query, which are
each embedded and searched independently. This eliminates the single-hypothesis failure
mode and removes the need for kind classification.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, field_validator

from backend.compiler.llm_client import chat

logger = logging.getLogger(__name__)

HYPOTHESES_K = 3

_SYSTEM = """\
You are a knowledge-base query assistant.

Given a user query, produce:

1. hypotheses: Exactly 3 SHORT declarative statements (≤20 words each), each written \
as if a matching atom already exists in the knowledge base. Make them DIVERSE — cover \
different angles (e.g. one about activity/events, one about metrics/quantities, one \
about trends or decisions). CRITICAL RULES:
  - Do NOT hallucinate specific entity names, company names, dollar amounts, percentages, \
or any values not explicitly stated in the query.
  - Use GENERIC language so each hypothesis can match any relevant atom, not just one.
  - Do NOT classify the query type.

Example for "top deals for Q2":
  ["A major enterprise contract was closed in Q2.",
   "Q2 deal sizes and contract values grew compared to the prior period.",
   "The sales team closed multiple high-value accounts in Q2."]

Example for "Q2 revenue":
  ["Revenue increased in Q2.",
   "Q2 financial results showed growth across key metrics.",
   "Q2 earnings and revenue figures were reported."]

2. canonical: If the query targets a specific subject entity AND/OR time period, extract \
them. Use STANDARD formats for period: "Q1", "Q2", "Q3", "Q4" (quarter only, no year \
unless the query explicitly states it), or "Q2 2024" (quarter + year). Otherwise null.
   Fields: subject (entity, e.g. "revenue", "headcount"), \
   period (e.g. "Q2", "Q2 2024"), predicate (what is measured — optional).

Output valid JSON only — no prose, no markdown fences."""

# ── Period normalisation ──────────────────────────────────────────────────────

_QUARTER_ALIASES = {
    "first quarter": "Q1",
    "second quarter": "Q2",
    "third quarter": "Q3",
    "fourth quarter": "Q4",
    "q1": "Q1",
    "q2": "Q2",
    "q3": "Q3",
    "q4": "Q4",
}


def normalize_subject(subject: str | None) -> str | None:
    """Normalise a canonical subject to lowercase stripped form for consistent filtering.

    "Revenue Growth" → "revenue growth", " ARR " → "arr"
    """
    if not subject:
        return None
    return subject.strip().lower()


def normalize_period(period: str | None) -> str | None:
    """Normalise a period string to a standard form for consistent filtering.

    "q2 2024", "Q2-2024", "second quarter 2024" → "Q2 2024"
    "Q2", "q2", "second quarter" → "Q2"
    """
    if not period:
        return None
    s = period.strip().lower()
    # Replace separators so "Q2-2024" and "Q2 2024" both work
    s = re.sub(r"[-/]", " ", s)
    s = re.sub(r"\s+", " ", s)

    for alias, canonical_q in _QUARTER_ALIASES.items():
        if s.startswith(alias):
            remainder = s[len(alias):].strip()
            return f"{canonical_q} {remainder}".strip() if remainder else canonical_q

    # Already in unknown format — title-case and return
    return period.strip().title()


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class _QueryCanonical(BaseModel):
    subject: str | None = None
    predicate: str | None = None
    period: str | None = None


class _QueryProcessResponse(BaseModel):
    hypotheses: list[str]
    canonical: _QueryCanonical | None = None

    @field_validator("hypotheses")
    @classmethod
    def strip_hypotheses(cls, v: list[str]) -> list[str]:
        return [h.strip() for h in v if h.strip()]


class ProcessedQuery(BaseModel):
    hypotheses: list[str]
    canonical: dict | None = None  # {subject?, predicate?, period?} — period is normalised


async def process_query(raw_query: str) -> ProcessedQuery:
    """Convert a raw query into k diverse declarative hypotheses for multi-embedding search.

    On any error (LLM failure, parse error, degenerate output), falls back to
    [raw_query] as the single hypothesis. Never raises.
    """
    try:
        raw = await chat(_SYSTEM, raw_query, response_format=_QueryProcessResponse, temperature=0.0)
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object found in LLM response")
        parsed = _QueryProcessResponse.model_validate_json(raw[start : end + 1])
        hypotheses = [h for h in parsed.hypotheses if len(h.split()) >= 3]
        if not hypotheses:
            hypotheses = [raw_query]
        canonical: dict | None = None
        if parsed.canonical:
            data = parsed.canonical.model_dump(exclude_none=True)
            if data:
                if "period" in data:
                    data["period"] = normalize_period(data["period"])
                if "subject" in data:
                    data["subject"] = normalize_subject(data["subject"])
                canonical = {k: v for k, v in data.items() if v}
        return ProcessedQuery(hypotheses=hypotheses, canonical=canonical or None)
    except Exception as exc:
        logger.warning("process_query failed for %r: %s", raw_query, exc)
        return ProcessedQuery(hypotheses=[raw_query], canonical=None)
