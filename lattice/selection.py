from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date

from openai import OpenAI

from lattice.db import LatticeDB
from lattice.models import Atom
from lattice.query import parse_query


@dataclass
class SelectionResult:
    atoms: list[dict]
    agent_tool_calls: list[dict] = field(default_factory=list)

_RECOMMENDATION_CAP = int(os.environ.get("LATTICE_RECOMMENDATION_CAP", "5"))
_PROBE_K = 7       # seeds used to measure session diversity
_POINTED_MAX = 14  # max atoms for single-session path (allows supersession expansion)


def _apply_recommendation_cap(atoms: list[dict]) -> list[dict]:
    rec_seen = 0
    result = []
    for atom in atoms:
        if atom.get("kind") == "recommendation":
            if rec_seen < _RECOMMENDATION_CAP:
                result.append(atom)
                rec_seen += 1
        else:
            result.append(atom)
    return result


def _atom_to_dict(a: Atom) -> dict:
    return {
        "atom_id": a.atom_id,
        "subject": a.subject,
        "kind": a.kind,
        "source": a.source,
        "content": a.content,
        "valid_from": a.valid_from.isoformat() if a.valid_from else None,
        "valid_until": a.valid_until.isoformat() if a.valid_until else None,
        "is_superseded": a.is_superseded,
        "supersedes": a.supersedes,
        "superseded_by": a.superseded_by,
        # Keep flat provenance fields for product/synthesis callers.
        "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
        "observed_at": a.observed_at.isoformat() if a.observed_at else None,
        "source_id": a.source_id,
        "source_title": a.source_title,
        "session_id": a.session_id,
        "segment_id": a.segment_id,
        "source_type": a.source_type,
        "source_span": a.source_span,
        # Mirror eval debug payload shape so select/bm25 modes differ only by
        # retrieval behavior, not metadata structure.
        "provenance": {
            "source_id": a.source_id,
            "source_title": a.source_title,
            "source_type": a.source_type,
            "session_id": a.session_id,
            "segment_id": a.segment_id,
            "source_span": a.source_span,
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
            "ingested_at": a.ingested_at.isoformat() if a.ingested_at else None,
        },
        "dedup": {
            "content_hash": a.content_hash,
            "normalized_content_hash": a.normalized_content_hash,
        },
    }


def _session_diversity(seeds: list[Atom]) -> int:
    """Count distinct session_ids in the probe seeds."""
    return len({a.session_id for a in seeds if a.session_id})


def select(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> list[dict]:
    if db is None:
        db = LatticeDB()

    intent = parse_query(query)
    seeds = db.search(query, as_of=as_of, top_k=top_k)
    if not seeds:
        return []

    # Session-diversity probe: top _PROBE_K seeds tell us whether the answer
    # is concentrated in one session (pointed) or spread across sessions (expand).
    probe = seeds[:_PROBE_K]
    n_sessions = _session_diversity(probe)

    if n_sessions <= 1:
        # Pointed path: answer concentrated in one session. Use probe seeds only
        # with small max_atoms to allow supersession chain traversal but suppress
        # cross-session noise.
        active_seeds = probe
        max_atoms = _POINTED_MAX
    else:
        # Expansion path: answer spans sessions. Full BFS needed.
        active_seeds = seeds
        max_atoms = max(top_k, top_k * 3)

    graph = db.graph

    if graph.graph.number_of_nodes() > 0:
        result = _graph_select(active_seeds, graph, db, as_of, max_atoms)
    else:
        result = _fallback_select(active_seeds, db, as_of, max_atoms)

    # Kind fallback: if query has a primary kind and BFS found none, scan all.
    if intent.primary_kind is not None:
        present_kinds = {a["kind"] for a in result}
        if intent.primary_kind not in present_kinds:
            seen_ids = {a["atom_id"] for a in result}
            for fa in db.list_by_kind(intent.primary_kind, as_of=as_of):
                if fa.atom_id not in seen_ids:
                    result.append(_atom_to_dict(fa))

    return _apply_recommendation_cap(result)


def _graph_select(
    seeds: list,
    graph,
    db: LatticeDB,
    as_of: date | None,
    max_atoms: int,
) -> list[dict]:
    expanded_ids = graph.bfs_expand(
        [s.atom_id for s in seeds],
        max_depth=4,
        max_atoms=max_atoms,
    )

    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    result: list[Atom] = []

    for atom_id in expanded_ids:
        if atom_id in seen_ids:
            continue
        seen_ids.add(atom_id)
        try:
            atom = db.read(atom_id)
        except Exception:
            continue

        # Temporal validity filter
        if as_of is not None:
            if atom.valid_from is not None and atom.valid_from > as_of:
                continue
            if atom.valid_until is not None and atom.valid_until < as_of:
                continue

        # Collapse exact duplicates by normalized content hash
        if atom.normalized_content_hash:
            if atom.normalized_content_hash in seen_hashes:
                continue
            seen_hashes.add(atom.normalized_content_hash)

        result.append(atom)

    return [_atom_to_dict(a) for a in result]


def _fallback_select(
    seeds: list,
    db: LatticeDB,
    as_of: date | None,
    max_atoms: int,
) -> list[dict]:
    selected = []
    seen: set[str] = set()
    for seed in seeds:
        for atom in db.evidence_pack(seed, as_of=as_of):
            if atom.atom_id in seen:
                continue
            selected.append(atom)
            seen.add(atom.atom_id)
            if len(selected) >= max_atoms:
                return [_atom_to_dict(a) for a in selected]
    return [_atom_to_dict(a) for a in selected]


# ── Selection agent ───────────────────────────────────────────────────────────

_AGENT_SYSTEM = """\
You are a retrieval agent for a personal memory lattice — a store of knowledge atoms extracted from conversations.

Each atom has:
- subject: a broad topic label (e.g. "hiking", "cooking", "travel")
- kind: fact | event | preference | recommendation | doc
- content: the actual information
- observed_at: when this was stated in the source conversation

Your job: retrieve the atoms most useful for answering the query. You will be told the query type — use it.

Tools:
- search(query, top_k): BM25 keyword search. Returns atom_id, subject, kind, content preview, observed_at.
- expand(atom_ids, max_depth, max_atoms): Graph BFS from seed atoms. Follows same_subject_as edges \
(semantic — connects atoms on the same topic across different sessions) and segment edges (structural — \
connects atoms from the same conversation segment).
- finish(atom_ids): Return the final atom set for synthesis. YOU MUST ALWAYS CALL THIS.

Strategy by query type:
- factual / single-session: search(top_k=10) → finish. Do NOT over-search. One search is enough.
- temporal: search(top_k=15) → finish with atoms that have observed_at dates. One search is enough.
- preference / recommendation: search(top_k=10) → expand(max_atoms=30) → finish. \
  Expand is required — preferences are scattered across sessions.
- multi-session / aggregation ("list all", "every time", "how many", "across conversations"): \
  search(top_k=15) → expand(max_atoms=40) → finish. \
  Expand is MANDATORY — same_subject_as edges connect atoms from different sessions on the same topic.
- knowledge-update ("latest", "current", "changed"): search(top_k=10) → finish with the most recent atoms.

Rules:
- Do not repeat search with different keywords. One or two searches maximum.
- After expand, call finish immediately — do not search again.
- Always call finish at the end. Never stop without calling it.
- 10–25 atoms is enough for synthesis. Do not over-retrieve.
"""

_AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "BM25 keyword search over all atoms in the lattice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {"type": "integer", "description": "Number of results (default 10, max 30)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expand",
            "description": (
                "Graph BFS from seed atom_ids. Follows same_subject_as (semantic) and "
                "segment edges (structural). Use to find related atoms from other sessions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "atom_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Seed atom IDs (from search results)",
                    },
                    "max_depth": {"type": "integer", "description": "BFS depth (default 3)"},
                    "max_atoms": {"type": "integer", "description": "Max atoms to return (default 25)"},
                },
                "required": ["atom_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finish",
            "description": "Return the final atom_ids for synthesis. Call this when done.",
            "parameters": {
                "type": "object",
                "properties": {
                    "atom_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Final atom IDs to pass to synthesis",
                    },
                },
                "required": ["atom_ids"],
            },
        },
    },
]


def _collect_atoms(atom_ids: list[str], db: LatticeDB, as_of: date | None) -> list[dict]:
    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()
    result = []
    for aid in atom_ids:
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        try:
            a = db.read(aid)
        except Exception:
            continue
        if as_of is not None:
            if a.valid_from and a.valid_from > as_of:
                continue
            if a.valid_until and a.valid_until < as_of:
                continue
        if a.normalized_content_hash:
            if a.normalized_content_hash in seen_hashes:
                continue
            seen_hashes.add(a.normalized_content_hash)
        result.append(_atom_to_dict(a))
    return result


def select_agent(
    query: str,
    as_of: date | None = None,
    db: LatticeDB | None = None,
    top_k: int = 20,
) -> SelectionResult:
    """LLM-driven selection agent. Falls back to deterministic select() for unsupported providers."""
    if db is None:
        db = LatticeDB()

    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    if provider not in ("ollama", "openai"):
        return SelectionResult(atoms=select(query, as_of=as_of, db=db, top_k=top_k))

    model = os.environ.get("SELECTION_MODEL") or os.environ.get("LLM_MODEL", "qwen3.5:4b")
    if provider == "ollama":
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=90.0)
        extra: dict = {"num_ctx": 4096}
    else:
        client = OpenAI(api_key=os.environ.get("LLM_API_KEY"))
        extra = {}

    # ── Tool implementations ──────────────────────────────────────────────────

    def _exec_search(q: str, k: int = 10) -> str:
        atoms = db.search(q, as_of=as_of, top_k=min(k, 30))
        return json.dumps([{
            "atom_id": a.atom_id,
            "subject": a.subject,
            "kind": a.kind,
            "content": a.content[:200],
            "observed_at": a.observed_at.isoformat() if a.observed_at else None,
        } for a in atoms])

    def _exec_expand(atom_ids: list[str], max_depth: int = 3, max_atoms: int = 25) -> str:
        graph = db.graph
        if graph.graph.number_of_nodes() == 0:
            return json.dumps([])
        seed_set = set(atom_ids)
        expanded_ids = graph.bfs_expand(atom_ids, max_depth=max_depth, max_atoms=min(max_atoms, 60))
        result = []
        for aid in expanded_ids:
            if aid in seed_set:
                continue
            try:
                a = db.read(aid)
                result.append({
                    "atom_id": a.atom_id,
                    "subject": a.subject,
                    "kind": a.kind,
                    "content": a.content[:200],
                    "observed_at": a.observed_at.isoformat() if a.observed_at else None,
                })
            except Exception:
                continue
        return json.dumps(result)

    # ── Agent loop ────────────────────────────────────────────────────────────

    intent = parse_query(query)
    _shape_label = {
        "temporal": "temporal",
        "recommendation": "preference / recommendation",
        "preference": "preference / recommendation",
        "factual": "factual / single-session",
    }
    query_type_hint = _shape_label.get(intent.shape.value, "factual / single-session")
    if intent.primary_kind:
        query_type_hint += f", looking for kind={intent.primary_kind}"

    messages: list[dict] = [
        {"role": "system", "content": _AGENT_SYSTEM},
        {"role": "user", "content": f"Query type: {query_type_hint}\nQuery: {query}"},
    ]
    accumulated_ids: list[str] = []
    tool_calls_log: list[dict] = []
    _MAX_ROUNDS = 4

    for round_i in range(_MAX_ROUNDS):
        # On the last round, force the agent to call finish
        is_last_round = (round_i == _MAX_ROUNDS - 1)
        if is_last_round and accumulated_ids:
            messages.append({
                "role": "user",
                "content": f"You have collected {len(set(accumulated_ids))} atoms. Call finish now with the most relevant atom_ids.",
            })

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=_AGENT_TOOLS,
            tool_choice="required" if is_last_round else "auto",
            extra_body=extra,
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            break

        for tc in msg.tool_calls:
            name = tc.function.name.rsplit(":", 1)[-1]
            args = json.loads(tc.function.arguments)

            if name == "search":
                result_str = _exec_search(args.get("query", query), args.get("top_k", 10))
                hits = json.loads(result_str)
                for item in hits:
                    accumulated_ids.append(item["atom_id"])
                tool_calls_log.append({"tool": "search", "args": args, "n_results": len(hits)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

            elif name == "expand":
                result_str = _exec_expand(
                    args.get("atom_ids", []),
                    args.get("max_depth", 3),
                    args.get("max_atoms", 25),
                )
                hits = json.loads(result_str)
                for item in hits:
                    accumulated_ids.append(item["atom_id"])
                tool_calls_log.append({"tool": "expand", "args": args, "n_results": len(hits)})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result_str})

            elif name == "finish":
                finish_ids = args.get("atom_ids", [])
                # Safety net: if agent is too selective, fall back to all accumulated ids
                all_unique = list(dict.fromkeys(accumulated_ids))
                if len(finish_ids) < 5 and len(all_unique) > len(finish_ids):
                    final_ids = all_unique
                else:
                    final_ids = finish_ids or all_unique
                tool_calls_log.append({
                    "tool": "finish",
                    "args": {"n_atoms": len(finish_ids)},
                    "fallback_to_accumulated": final_ids is all_unique and finish_ids != all_unique,
                })
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": "ok"})
                final = _apply_recommendation_cap(_collect_atoms(final_ids, db, as_of))
                return SelectionResult(atoms=final, agent_tool_calls=tool_calls_log)

            else:
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": f"unknown tool: {name}"})

    # Fallback: return accumulated atoms, or deterministic select if nothing collected
    if accumulated_ids:
        final = _apply_recommendation_cap(
            _collect_atoms(list(dict.fromkeys(accumulated_ids)), db, as_of)
        )
        return SelectionResult(atoms=final, agent_tool_calls=tool_calls_log)
    return SelectionResult(atoms=select(query, as_of=as_of, db=db, top_k=top_k))
