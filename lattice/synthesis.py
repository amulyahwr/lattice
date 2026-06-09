from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Generator

from lattice.llm import LLMClient
from lattice.privacy import EntityRedactor, is_active as _pii_active

if TYPE_CHECKING:
    from lattice.config import Config


@dataclass
class SynthesisResult:
    answer: str
    raw_response: str
    tool_calls: list[dict] = field(default_factory=list)
    pii_protected: bool = False


_SYSTEM = """\
You are a knowledge synthesis agent. Given a set of knowledge atoms and a question, produce a concise answer.

Each atom has:
- `src`: a source identifier shown in brackets — use this to cite the atom inline
- `observed_at`: when this fact was mentioned in the source (always present — use this for temporal reasoning)
- `valid_from`: when this fact is explicitly time-bounded (rarely set — only trust it when non-null)

Guidelines:
- Identify which atoms are relevant to the question.
- Cite every atom you use by including [src:<src_id>] immediately after the statement it supports. \
Example: "Alice joined in 2021 [src:abc123]." Use the exact src value from the atom header.
- For temporal questions ("when", "how long ago", "before/after X"):
    Use `observed_at` as the reference date — it records when the fact was stated in the source.
    Resolve relative expressions ("last Saturday", "two months ago") by offsetting from `observed_at`.
    Use the `date_diff` tool to compute exact durations between two ISO dates.
    When reporting a duration in weeks or months, round to the nearest integer (e.g. 2.85 weeks → 3 weeks).
- For time-bounded facts: if `valid_from` is non-null, use it to determine temporal validity.
- For conflicting facts: present both versions with their `observed_at` dates and let the answer reflect the change.
- For counting or totaling questions ("how many", "total", "sum"):
    First check if any atom has kind=count — these are authoritative aggregate facts extracted \
at ingest time. If a count atom exists for the relevant subject, use its value directly.
    If no kind=count atom exists, enumerate every distinct item or value from the atoms explicitly, \
then call `sum_numbers` with those values to get the exact total — do not add them yourself.
- For preference or recommendation questions: ground your answer in the user's known context \
(their preferences, constraints, or situation) as recorded in the atoms before giving advice.
- If the atoms directly or partially answer the question, synthesise an answer from them.
- If atoms only partially answer the question, give a best-effort answer and note the specific gap briefly.
- If the atoms are present but NOT relevant to the question, respond with exactly the token: \
<<NO_INFO>> — nothing else, no explanation, no list of what IS stored.
- Never assume gender. Use the person's name or they/their when gender is not explicitly stated in the atoms.
- Be concise: one to three paragraphs at most.
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "date_diff",
            "description": "Return the number of days between two ISO dates (date2 - date1). Positive means date2 is later.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date1": {"type": "string", "description": "Earlier ISO date, e.g. 2023-11-10"},
                    "date2": {"type": "string", "description": "Later ISO date, e.g. 2024-03-15"},
                },
                "required": ["date1", "date2"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sum_numbers",
            "description": "Return the exact sum of a list of numbers. Use for totaling counts, weights, distances, money amounts, or any numeric aggregation — do not add numbers yourself.",
            "parameters": {
                "type": "object",
                "properties": {
                    "numbers": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "The numbers to sum, e.g. [50, 20] or [1200, 800, 1000]",
                    },
                },
                "required": ["numbers"],
            },
        },
    },
]


def _execute_tool(name: str, args: dict) -> str:
    # Strip model-specific prefixes some models add (e.g. "modelname:date_diff")
    bare_name = name.rsplit(":", 1)[-1]
    if bare_name == "date_diff":
        d1 = date.fromisoformat(args["date1"][:10])
        d2 = date.fromisoformat(args["date2"][:10])
        return str((d2 - d1).days)
    if bare_name == "sum_numbers":
        return str(sum(float(n) for n in args["numbers"]))
    return f"unknown tool: {name}"


_CITATION_RE = re.compile(r"\[src:([^\]]+)\]")

_NO_ANSWER_SENTINEL = "<<NO_INFO>>"

_NO_ANSWER_RE = re.compile(
    r"(i can'?t determine|cannot determine|not mentioned|no information about|"
    r"atoms do not|do not contain|doesn'?t contain|don'?t contain|"
    r"there is no|there are no|no record|nothing in the|"
    r"not stored|not in the lattice|no relevant|not available)",
    re.IGNORECASE,
)

_NO_ANSWER_PHRASE = "Nothing saved on that yet — drop a note into Lattice and it'll be here next time you ask."


def _is_no_answer(text: str) -> bool:
    """Return True when the LLM signalled no relevant answer.

    Checks for the <<NO_INFO>> sentinel first (exact prompt instruction),
    then falls back to fuzzy regex for LLMs that paraphrase instead.
    """
    if _NO_ANSWER_SENTINEL in text:
        return True
    return bool(_NO_ANSWER_RE.search(text))


def _atom_src_key(a: dict) -> str:
    """Citation key — uses pre-assigned src_key if present, else atom_id."""
    return str(a.get("src_key") or a.get("atom_id") or a.get("source_id") or a.get("source") or "unknown")


def replace_citations(text: str, atoms: list[dict]) -> str:
    """Replace [src:id] markers in *text* with labelled citation markers.

    Each marker becomes ``[<title_or_subject>][src:<id>]`` so callers can
    render it as a tooltip or link. Unknown source_ids are left unchanged —
    never silently drop a citation the model emitted (Rule 6).
    """
    index: dict[str, dict] = {}
    for a in atoms:
        for key in filter(None, (_atom_src_key(a), a.get("source_id"))):
            index.setdefault(key, a)

    def _replace(m: re.Match) -> str:
        src_id = m.group(1)
        atom = index.get(src_id)
        if not atom:
            return m.group(0)  # unknown — leave intact
        label = atom.get("source_title") or atom.get("subject") or src_id
        return f"[{label}][src:{src_id}]"

    return _CITATION_RE.sub(_replace, text)


def _redact_atoms(atoms: list[dict], cfg: "Config") -> tuple[list[dict], dict[str, str]]:
    """Redact PII from atom content + subject before sending to cloud LLM.

    Returns (redacted_atoms, entity_map). Caller must restore entity_map in the response.
    Pass original atoms (not redacted) to replace_citations() so citation labels keep real names.
    """
    from lattice.privacy import _apply_replacements
    redactor = EntityRedactor()
    texts = [a.get("content", "") for a in atoms]
    redacted_texts, entity_map = redactor.redact_batch(texts, cfg)
    if not entity_map:
        return atoms, {}
    orig_to_tag = {v: k for k, v in entity_map.items()}
    redacted: list[dict] = []
    for a, rt in zip(atoms, redacted_texts):
        ra = dict(a)
        ra["content"] = rt
        if ra.get("subject"):
            ra["subject"] = _apply_replacements(ra["subject"], orig_to_tag)
        redacted.append(ra)
    return redacted, entity_map


def _build_messages(query: str, atoms: list[dict], query_date: date | None) -> list[dict]:
    today = (query_date or datetime.now(tz=timezone.utc).date()).isoformat()
    atoms_text = "\n\n".join(
        (
            f"[src:{_atom_src_key(a)} "
            f"/ {a['subject']} / {a['kind']} / valid_from={a.get('valid_from', 'null')} "
            f"/ observed_at={a.get('observed_at', 'null')} "
            f"/ title={a.get('source_title') or 'n/a'}]\n"
            f"{a['content']}"
        )
        for a in atoms
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Today's date: {today}\n\nQuery: {query}\n\nKnowledge atoms:\n{atoms_text}"},
    ]


def _run_tool_loop(
    client: "LLMClient",
    messages: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Run the tool-calling agent loop until the model stops calling tools or hits 5 rounds.

    Returns (messages_with_tool_results, tool_calls_log).
    Only appends messages when tools are actually called — the caller is responsible
    for generating the final text response (streaming or non-streaming).
    """
    tool_calls_log: list[dict] = []
    for _ in range(5):
        resp = client.create(messages=messages, tools=_TOOLS, tool_choice="auto")
        msg = resp.choices[0].message
        if not msg.tool_calls:
            break
        messages.append(msg)
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _execute_tool(tc.function.name, args)
            tool_calls_log.append({"tool": tc.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})
    return messages, tool_calls_log


def synthesize(
    query: str,
    atoms: list[dict],
    cfg: "Config",
    query_date: date | None = None,
) -> SynthesisResult:
    if not atoms:
        return SynthesisResult(answer="No relevant information found in the lattice.", raw_response="")

    client = LLMClient(cfg, model=cfg.synthesis_model)
    redacted_atoms, entity_map = _redact_atoms(atoms, cfg)
    messages = _build_messages(query, redacted_atoms, query_date)
    messages, tool_calls_log = _run_tool_loop(client, messages)

    resp = client.create(messages=messages)
    raw = resp.choices[0].message.content or ""
    if entity_map:
        raw = EntityRedactor().restore(raw, entity_map)
    answer = _NO_ANSWER_PHRASE if _is_no_answer(raw) else raw
    return SynthesisResult(answer=answer, raw_response=raw, tool_calls=tool_calls_log, pii_protected=bool(entity_map))


def stream_synthesis(
    query: str,
    atoms: list[dict],
    cfg: "Config",
    query_date: date | None = None,
) -> "Generator[str, None, None]":
    """Stream the final synthesis answer as SSE-formatted strings.

    Yields ``data: <json>\\n\\n`` lines. Event shapes:
    - ``{"type": "token", "text": "..."}`` — one chunk of the answer
    - ``{"type": "done"}`` — stream complete
    - ``{"type": "error", "message": "..."}`` — degradation: signals a failure to the caller
      (Rule 6: never silently swallow errors mid-stream)

    Note: tool-call rounds run synchronously before streaming begins. Only the final
    answer turn is streamed. This is intentional — tool execution requires a full round-trip.
    """
    if not atoms:
        yield f'data: {json.dumps({"type": "token", "text": "No relevant information found in the lattice."})}\n\n'
        yield 'data: {"type": "done"}\n\n'
        return

    try:
        client = LLMClient(cfg, model=cfg.synthesis_model)
    except EnvironmentError as exc:
        # Rule 6: make degradation visible — signal provider gap to the caller
        yield f'data: {json.dumps({"type": "error", "message": str(exc)})}\n\n'
        return

    redacted_atoms, entity_map = _redact_atoms(atoms, cfg)
    _redactor = EntityRedactor()
    messages = _build_messages(query, redacted_atoms, query_date)
    try:
        messages, tool_calls_log = _run_tool_loop(client, messages)
    except Exception as exc:
        yield f'data: {json.dumps({"type": "error", "message": f"Tool loop failed: {exc}"})}\n\n'
        return

    full_answer: list[str] = []
    try:
        stream = client.create(messages=messages, stream=True)
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                full_answer.append(delta.content)
                yield f'data: {json.dumps({"type": "token", "text": delta.content})}\n\n'
    except Exception as exc:
        yield f'data: {json.dumps({"type": "error", "message": f"Streaming failed: {exc}"})}\n\n'
        return

    # Citation markers may span chunk boundaries — assemble full text before sending.
    assembled = "".join(full_answer)
    if entity_map:
        assembled = _redactor.restore(assembled, entity_map)
    if _is_no_answer(assembled):
        assembled = _NO_ANSWER_PHRASE
    # Build first-appearance number map server-side so client doesn't recompute.
    num_map: dict[str, int] = {}
    counter = 1
    for m in re.finditer(r"\[src:([^\]]+)\]", assembled):
        if m.group(1) not in num_map:
            num_map[m.group(1)] = counter
            counter += 1
    yield f'data: {json.dumps({"type": "citations_applied", "answer": assembled, "num_map": num_map, "pii_protected": bool(entity_map)})}\n\n'
    yield 'data: {"type": "done"}\n\n'
