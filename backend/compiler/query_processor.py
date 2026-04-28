"""HyDE query processor — converts raw queries into kind-aware declarative hypotheses.

Classifies the query's intent kind(s) (metric/event/decision/procedure/fact) using the
same taxonomy as atoms, then generates hypotheses written to sound like atoms of those
kinds. This bridges query space and atom space using the same vocabulary on both sides,
replacing random angle diversity with structured kind diversity.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, field_validator

from backend.compiler.llm_client import chat
from backend.compiler.period_utils import extract_period_from_text, normalize_period, normalize_subject

logger = logging.getLogger(__name__)

HYPOTHESES_K = 3

_ATOM_KINDS = {"metric", "decision", "event", "procedure", "fact"}

_SYSTEM = """\
You are a knowledge-base query assistant. Atoms in the knowledge base are classified \
into exactly these kinds: metric, event, decision, procedure, fact.

Given a user query, produce:

1. kinds: Identify which atom kind(s) the query is seeking. Choose 1–2 from: \
metric, event, decision, procedure, fact.
  - "top deals", "contracts closed", "what happened" → ["event"]
  - "revenue", "growth rate", "how much", "numbers" → ["metric"]
  - "why did we", "strategy", "policy", "chose to" → ["decision"]
  - "how to", "steps to", "process for" → ["procedure"]
  - "what is", "background on", "context about" → ["fact"]
  - Mixed queries like "deals and revenue" → ["event", "metric"]

2. hypotheses: Exactly 3 SHORT declarative statements (≤20 words each), written to \
sound like atoms of the identified kind(s). If multiple kinds, distribute hypotheses \
across them. CRITICAL RULES:
  - Write each hypothesis to MATCH ITS KIND:
      event → a specific occurrence, signing, announcement, or outcome
      metric → a number, rate, or measurement with context
      decision → a choice made, policy adopted, or direction set
      procedure → a step, process, or method described
      fact → a general truth, definition, or background statement
  - Do NOT hallucinate entity names, dollar amounts, or values not in the query.
  - Keep language GENERIC enough to match any relevant atom, not just one specific atom.

Example for "top deals in Q2" → kinds: ["event"]
  ["A major enterprise contract was closed in Q2.",
   "A large multi-year deal was signed with a key customer in Q2.",
   "The sales team secured a high-value annual contract in Q2."]

Example for "Q2 revenue" → kinds: ["metric"]
  ["Revenue reached a new high in Q2.",
   "Q2 total revenue grew compared to the prior quarter.",
   "Quarterly financial results showed strong revenue performance in Q2."]

Example for "deals and revenue in Q2" → kinds: ["event", "metric"]
  ["A major enterprise contract was closed in Q2.",
   "Q2 revenue from closed deals reached a significant total.",
   "Multiple high-value accounts were won in Q2."]

3. canonical: If the query targets a specific subject entity AND/OR time period, extract \
them. Use STANDARD formats for period: "Q1", "Q2", "Q3", "Q4" (quarter only, no year \
unless explicitly stated), or "Q2 2024" (with year). Otherwise null.
   Fields: subject (entity, e.g. "revenue", "headcount"), \
   period (e.g. "Q2", "Q2 2024"), predicate (what is measured — optional).

Output valid JSON only — no prose, no markdown fences."""



# ── Pydantic schemas ──────────────────────────────────────────────────────────


class _QueryCanonical(BaseModel):
    subject: str | None = None
    predicate: str | None = None
    period: str | None = None


class _QueryProcessResponse(BaseModel):
    kinds: list[str] = []
    hypotheses: list[str]
    canonical: _QueryCanonical | None = None

    @field_validator("kinds")
    @classmethod
    def validate_kinds(cls, v: list[str]) -> list[str]:
        return [k.lower() for k in v if k.lower() in _ATOM_KINDS]

    @field_validator("hypotheses")
    @classmethod
    def strip_hypotheses(cls, v: list[str]) -> list[str]:
        return [h.strip() for h in v if h.strip()]


class ProcessedQuery(BaseModel):
    hypotheses: list[str]
    kinds: list[str] = []       # atom kind(s) the query is seeking, e.g. ["event"]
    canonical: dict | None = None  # {subject?, predicate?, period?} — period is normalised


async def process_query(raw_query: str) -> ProcessedQuery:
    """Convert a raw query into kind-aware declarative hypotheses for multi-embedding search.

    Extracts the time period from the raw query deterministically via regex before calling
    the LLM. This detected period is injected as a hint so hypotheses carry it, and used
    as a fallback if the LLM returns null for canonical.period. Never raises.
    """
    # Deterministic period extraction — independent of LLM reliability
    detected_period = extract_period_from_text(raw_query)
    detected_period_norm = normalize_period(detected_period) if detected_period else None

    # Inject detected period as a hint so the LLM includes it in hypotheses
    llm_input = raw_query
    if detected_period_norm:
        llm_input = f"{raw_query}\n[Time period detected: {detected_period_norm}]"

    try:
        raw = await chat(_SYSTEM, llm_input, response_format=_QueryProcessResponse, temperature=0.0)
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

        # Regex fallback — if LLM missed the period, use the deterministically extracted one
        if detected_period_norm:
            if canonical is None:
                canonical = {"period": detected_period_norm}
            elif "period" not in canonical:
                canonical["period"] = detected_period_norm

        return ProcessedQuery(hypotheses=hypotheses, kinds=parsed.kinds, canonical=canonical or None)
    except Exception as exc:
        logger.warning("process_query failed for %r: %s", raw_query, exc)
        fallback_canonical = {"period": detected_period_norm} if detected_period_norm else None
        return ProcessedQuery(hypotheses=[raw_query], kinds=[], canonical=fallback_canonical)
