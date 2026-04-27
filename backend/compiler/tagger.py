"""Tagger — assign access masks, domains, and kind to atoms.

Evolved from engine/access.py. The core insight: access control is computed
at compile time (bitmask on atom) rather than query time (policy engine).
Runtime access check is a single AND: agent.role_mask & atom.access_mask != 0.

Domain suggestion is LLM-based (one batched call for all atoms), replacing
the old keyword-scoring heuristic.
"""

from __future__ import annotations

import json
import logging
import re

from backend.compiler.llm_client import chat

logger = logging.getLogger(__name__)

# ── Bitmask mapping for MVP ──
# bit 0 = sales, bit 1 = finance, bit 2 = engineering,
# bit 3 = hr, bit 4 = legal, bit 5 = product

DOMAIN_BIT_MAP: dict[str, int] = {
    "sales": 0,
    "finance": 1,
    "engineering": 2,
    "hr": 3,
    "legal": 4,
    "product": 5,
}

INTERNAL_BITS = (1 << 6) - 1  # 0x3F fallback — all departments

_VALID_DOMAINS = frozenset(DOMAIN_BIT_MAP.keys())

_BATCH_SIZE = 50  # domain classification is cheap, handle more per call

_SYSTEM_DOMAIN = """\
You are a domain classifier for enterprise knowledge atoms.

Valid domains: sales, finance, engineering, hr, legal, product

Rules:
- Choose only from the valid domain list above.
- An atom may belong to multiple domains (e.g. a budget decision is both finance and sales).
- If no specific domain applies, return an empty array for that atom.
- Return ONLY a JSON object mapping each item's 0-based index (as a string key) to its domain array.
- You MUST include an entry for every index from "0" to "N-1". Do not skip any index.
- CRITICAL: Classify each item independently, even if items are similar or identical.

Example input:  ["Q2 pipeline hit 120% of quota.", "Deploy the Kubernetes cluster.", "New hire onboarding checklist."]
Example output: {"0": ["sales","finance"], "1": ["engineering"], "2": ["hr"]}"""


def _domains_to_mask(domains: list[str]) -> int:
    """OR together the bit for each named domain. Falls back to INTERNAL_BITS if none match."""
    mask = 0
    for d in domains:
        bit = DOMAIN_BIT_MAP.get(d.lower())
        if bit is not None:
            mask |= 1 << bit
    return mask if mask else INTERNAL_BITS


def mask_to_domains(mask: int) -> list[str]:
    """Convert an access_mask back to a sorted list of domain names."""
    return sorted(d for d, bit in DOMAIN_BIT_MAP.items() if (mask >> bit) & 1)


async def suggest_domains(text: str) -> list[str]:
    """Suggest domain tags for a single text via LLM."""
    batch = await _suggest_domains_batch([text])
    return batch[0]


async def _suggest_domains_batch(texts: list[str]) -> list[list[str]]:
    """Classify domains for all texts in as few LLM calls as possible."""
    results: list[list[str]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        raw = await chat(_SYSTEM_DOMAIN, json.dumps(batch), temperature=0.0)
        results.extend(_parse_domain_response(raw, expected=len(batch)))
    return results


def _parse_domain_response(raw: str, expected: int) -> list[list[str]]:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"LLM domain response contains no JSON object: {raw!r}")
    try:
        parsed = json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM domain response is not valid JSON: {raw!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM domain response is not a JSON object: {raw!r}")

    # Detect which indices the LLM dropped — we can now fill exactly the right slots.
    present = {int(k) for k in parsed if k.isdigit()}
    missing = set(range(expected)) - present
    if missing:
        logger.warning(
            f"Domain classification missing indices {sorted(missing)} "
            f"(expected {expected} entries). Falling back to [] for those atoms."
        )

    results: list[list[str]] = []
    for i in range(expected):
        item = parsed.get(str(i), [])
        if isinstance(item, str):
            item = [item]
        elif not isinstance(item, list):
            item = []
        domains = [
            d.lower()
            for d in item
            if isinstance(d, str) and d.lower() in _VALID_DOMAINS
        ]
        results.append(domains)
    return results


async def tag_atoms(
    contents: list[str],
    kinds: list[str],
) -> list[dict]:
    """Tag a batch of atoms with access_mask and LLM-suggested domains.

    access_mask is ATOM-level: derived directly from the atom's own domain tags.
    An atom tagged [sales, finance] gets exactly sales_bit | finance_bit, making
    it visible only to agents whose role_mask overlaps those domains.

    Fallback: atoms with no recognisable domains (LLM returned [] after filtering)
    inherit the source-level majority-vote mask, so they don't become world-readable.
    """
    llm_domain_lists = await _suggest_domains_batch(contents)
    source_mask = _source_level_mask(llm_domain_lists)  # fallback for domain-less atoms

    return [
        {
            "access_mask": _domains_to_mask(llm_domains) if llm_domains else source_mask,
            "domain": llm_domains,
            "kind": kind,
        }
        for kind, llm_domains in zip(kinds, llm_domain_lists)
    ]


def _source_level_mask(llm_domain_lists: list[list[str]]) -> int:
    """Compute a single access_mask for the whole source via majority vote.

    Tallies all domain tags across every atom. Domains within
    80% of the top count are all included, to avoid over-narrowing mixed sources.
    Falls back to INTERNAL_BITS when no domains are found.
    """
    from collections import Counter

    tally: Counter[str] = Counter(
        d for domains in llm_domain_lists for d in domains if d in DOMAIN_BIT_MAP
    )
    if not tally:
        return INTERNAL_BITS

    top_count = tally.most_common(1)[0][1]
    dominant = [d for d, c in tally.items() if c >= top_count * 0.8]
    return _domains_to_mask(dominant)
