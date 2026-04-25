"""Tagger — assign access masks, domains, and kind to atoms.

Evolved from engine/access.py. The core insight: access control is computed
at compile time (bitmask on atom) rather than query time (policy engine).
Runtime access check is a single AND: agent.role_mask & atom.access_mask != 0.
"""

from __future__ import annotations

# ── Bitmask mapping for MVP ──
# bit 0 = public, bit 1 = sales, bit 2 = finance, bit 3 = engineering,
# bit 4 = hr, bit 5 = legal, bit 6 = product, bit 7 = executive

DOMAIN_BIT_MAP: dict[str, int] = {
    "public": 0,
    "sales": 1,
    "finance": 2,
    "engineering": 3,
    "hr": 4,
    "legal": 5,
    "product": 6,
    "executive": 7,
}

ALL_BITS = (1 << 8) - 1  # 0xFF — all 8 bits set
INTERNAL_BITS = ALL_BITS & ~1  # bits 1-7 (everything except public-only)
EXECUTIVE_ONLY = 1 << DOMAIN_BIT_MAP["executive"]  # bit 7

# Domain keyword detection (carried from summarize.py suggest_domains)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "finance": [
        "revenue", "financial", "profit", "budget", "ebitda",
        "forecast", "earnings", "fiscal", "cost", "margin",
    ],
    "engineering": [
        "api", "architecture", "system", "code", "deploy",
        "infrastructure", "technical", "database", "software", "pipeline",
    ],
    "legal": [
        "contract", "compliance", "regulation", "liability",
        "agreement", "policy", "legal", "law",
    ],
    "sales": [
        "customer", "pipeline", "deal", "crm", "prospect",
        "quota", "sales", "revenue target", "account",
    ],
    "hr": [
        "employee", "hiring", "onboarding", "performance review",
        "benefits", "compensation", "headcount",
    ],
    "product": [
        "roadmap", "feature", "user experience", "product",
        "release", "sprint", "backlog",
    ],
}


def compute_access_mask(classification: str, domains: list[str] | None = None) -> int:
    """Compute a 64-bit access mask from source classification and domains.

    Mapping:
    - public: all bits set (everyone can see)
    - internal: bits 1-7 (all departments, not anonymous public)
    - confidential: only bits for specified domains
    - restricted: executive only (bit 7)
    """
    if classification == "public":
        return ALL_BITS
    elif classification == "internal":
        return INTERNAL_BITS
    elif classification == "confidential":
        if domains:
            mask = 0
            for d in domains:
                bit = DOMAIN_BIT_MAP.get(d.lower())
                if bit is not None:
                    mask |= 1 << bit
            return mask if mask else INTERNAL_BITS
        return INTERNAL_BITS
    elif classification == "restricted":
        return EXECUTIVE_ONLY
    else:
        return INTERNAL_BITS


def suggest_domains(text: str) -> list[str]:
    """Suggest domain tags based on text content.

    Returns a list of matching domain names.
    """
    text_lower = text.lower()
    matched: list[str] = []

    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score >= 2:
            matched.append(domain)

    return matched if matched else ["general"]


def tag_atoms(
    contents: list[str],
    kinds: list[str],
    source_classification: str,
    source_domains: list[str] | None = None,
) -> list[dict]:
    """Tag a batch of atoms with access_mask and refined domains.

    Returns list of dicts: [{"access_mask": int, "domain": list[str], "kind": str}]
    """
    base_mask = compute_access_mask(source_classification, source_domains)
    results: list[dict] = []

    for content, kind in zip(contents, kinds):
        # Refine domains per atom
        atom_domains = suggest_domains(content)
        if source_domains:
            # Merge source-level domains
            atom_domains = list(set(atom_domains) | set(source_domains))

        results.append({
            "access_mask": base_mask,
            "domain": atom_domains,
            "kind": kind,
        })

    return results
