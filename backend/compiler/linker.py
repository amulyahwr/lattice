"""Linker — identify relationships between atoms using LLM.

Given distilled atom contents, asks the LLM to find explicit relationships.
Returns a link list parallel to the atom list.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field, RootModel

from backend.compiler.llm_client import chat
from backend.config import DOMAIN_GROUPS

_SYSTEM = """\
You identify relationships between knowledge atoms.

You receive a JSON array of numbered propositions. Identify explicit relationships
between them that are clearly supported by the text.

Return a JSON array of relationship objects:
{"from": <index>, "to": <index>, "relation": "<type>"}

Relation types:
  causal        — A caused, led to, or drove B
  temporal      — A happened before or after B
  hierarchical  — A contains, categorizes, or is a parent of B
  topical       — A and B describe the same subject or entity
  contradicts   — A and B make conflicting or opposing claims

Rules:
- Only include relationships explicitly present in the propositions
- Do not infer unstated connections
- If no relationships exist, return []
- Output ONLY valid JSON — no explanation, no markdown, no code fences
"""

_BATCH_SIZE = 30  # atoms per linking call


_CROSS_SYSTEM = """\
You identify relationships between two groups of knowledge atoms.

Group A contains NEW atoms. Group B contains EXISTING atoms.
Find relationships ONLY between atoms in Group A and atoms in Group B.
Do NOT link atoms within Group A to each other.
Do NOT link atoms within Group B to each other.

Return a JSON array:
[{"new_index": <index in Group A>, "existing_index": <index in Group B>, "relation": "<type>"}]

Relation types:
  causal        — one caused, led to, or drove the other
  temporal      — one happened before or after the other
  hierarchical  — one contains, categorizes, or is a parent of the other
  topical       — both describe the same subject or entity
  contradicts   — they make conflicting or opposing claims

Rules:
- Only include relationships explicitly supported by the content
- Do not infer unstated connections
- If no cross-group relationships exist, return []
- Output ONLY valid JSON — no explanation, no markdown, no code fences
"""


# ── Response schemas ──────────────────────────────────────────────────────────


class _Link(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    from_: int = Field(alias="from")
    to: int
    relation: str = "topical"


class _LinkResponse(RootModel[list[_Link]]):
    pass


class _CrossLink(BaseModel):
    new_index: int
    existing_index: int
    relation: str = "topical"


class _CrossLinkResponse(RootModel[list[_CrossLink]]):
    pass


# ── Helpers ───────────────────────────────────────────────────────────────────


def expand_domains(domains: list[str]) -> set[str]:
    """Expand a domain list one hop using DOMAIN_GROUPS.

    For each group that overlaps with the input domains, all domains in that
    group are added. Expansion uses the original set only (no chaining), so a
    "sales" atom expands to {sales, finance, product} — not further.
    """
    original = set(domains)
    expanded = set(domains)
    for group in DOMAIN_GROUPS:
        if original & group:
            expanded |= group
    return expanded


def _parse_links(raw: str) -> list[_Link]:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    links = []
    for item in items:
        try:
            links.append(_Link.model_validate(item))
        except Exception:
            continue
    return links


def _parse_cross_links(raw: str) -> list[_CrossLink]:
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        items = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    links = []
    for item in items:
        try:
            links.append(_CrossLink.model_validate(item))
        except Exception:
            continue
    return links


# ── Public API ────────────────────────────────────────────────────────────────


async def cross_link_atoms(
    new_contents: list[str],
    existing_contents: list[str],
) -> list[list[dict]]:
    """Find cross-source relationships between new and existing atoms.

    Args:
        new_contents:      Distilled content of newly ingested atoms.
        existing_contents: Distilled content of candidate existing atoms.

    Returns:
        A list parallel to new_contents. Each entry is a list of:
        [{"existing_index": int, "relation": str}, ...]
    """
    n_new = len(new_contents)
    links: list[list[dict]] = [[] for _ in range(n_new)]

    if not new_contents or not existing_contents:
        return links

    payload = json.dumps(
        {
            "new_atoms": [
                {"index": i, "proposition": c} for i, c in enumerate(new_contents)
            ],
            "existing_atoms": [
                {"index": i, "proposition": c} for i, c in enumerate(existing_contents)
            ],
        },
        ensure_ascii=False,
    )

    output = await chat(_CROSS_SYSTEM, payload, response_format=_CrossLinkResponse)
    raw_links = _parse_cross_links(output)

    for rel in raw_links:
        if not (0 <= rel.new_index < n_new and 0 <= rel.existing_index < len(existing_contents)):
            continue
        links[rel.new_index].append({"existing_index": rel.existing_index, "relation": rel.relation})

    return links


async def link_atoms(contents: list[str]) -> list[list[dict]]:
    """Identify relationships between atoms.

    Args:
        contents: Distilled atom content strings (parallel to atom list).

    Returns:
        A list parallel to contents. Each entry is a list of link dicts:
        [{"target_index": int, "relation": str}, ...]
    """
    n = len(contents)
    links: list[list[dict]] = [[] for _ in range(n)]

    for batch_start in range(0, n, _BATCH_SIZE):
        batch = contents[batch_start : batch_start + _BATCH_SIZE]
        payload = json.dumps(
            [{"index": i, "proposition": c} for i, c in enumerate(batch)],
            ensure_ascii=False,
        )
        output = await chat(_SYSTEM, payload, response_format=_LinkResponse)
        raw_links = _parse_links(output)

        for rel in raw_links:
            global_from = batch_start + rel.from_
            global_to = batch_start + rel.to

            if (
                0 <= global_from < n
                and 0 <= global_to < n
                and global_from != global_to
            ):
                links[global_from].append({"target_index": global_to, "relation": rel.relation})

    return links
