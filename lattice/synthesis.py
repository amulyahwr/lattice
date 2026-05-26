from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from openai import OpenAI


@dataclass
class SynthesisResult:
    answer: str
    raw_response: str
    tool_calls: list[dict] = field(default_factory=list)


_SYSTEM = """\
You are a knowledge synthesis agent. Given a set of knowledge atoms and a question, produce a concise answer.

Each atom has:
- `observed_at`: when this fact was mentioned in the source (always present — use this for temporal reasoning)
- `valid_from`: when this fact is explicitly time-bounded (rarely set — only trust it when non-null)

Guidelines:
- Identify which atoms are relevant to the question.
- For temporal questions ("when", "how long ago", "before/after X"):
    Use `observed_at` as the reference date — it records when the fact was stated in the source.
    Resolve relative expressions ("last Saturday", "two months ago") by offsetting from `observed_at`.
    Use the `date_diff` tool to compute exact durations between two ISO dates.
- For time-bounded facts: if `valid_from` is non-null, use it to determine temporal validity.
- For conflicting facts: present both versions with their `observed_at` dates and let the answer reflect the change.
- If atoms are present, always derive an answer from them. Do not say "no information found."
- If atoms only partially answer the question, give a best-effort answer and note the gap.
- Only return "no information" if the atoms list is literally empty.
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
    }
]


def _make_client() -> OpenAI:
    provider = os.environ.get("LLM_PROVIDER", "anthropic")
    api_key = os.environ.get("LLM_API_KEY")
    if provider == "ollama":
        return OpenAI(base_url="http://localhost:11434/v1", api_key="ollama", timeout=90.0)
    if provider == "openai":
        return OpenAI(api_key=api_key)
    raise NotImplementedError(
        f"Synthesis agent does not yet support provider '{provider}'. "
        "Set LLM_PROVIDER=ollama or LLM_PROVIDER=openai."
    )


def _execute_tool(name: str, args: dict) -> str:
    # Strip model-specific prefixes some models add (e.g. "google:gemma:date_diff")
    bare_name = name.rsplit(":", 1)[-1]
    if bare_name == "date_diff":
        d1 = date.fromisoformat(args["date1"])
        d2 = date.fromisoformat(args["date2"])
        return str((d2 - d1).days)
    return f"unknown tool: {name}"


def synthesize(
    query: str,
    atoms: list[dict],
    query_date: date | None = None,
) -> SynthesisResult:
    if not atoms:
        return SynthesisResult(
            answer="No relevant information found in the lattice.",
            raw_response="",
        )

    today = (query_date or datetime.now(tz=timezone.utc).date()).isoformat()
    tool_calls_log: list[dict] = []

    atoms_text = "\n\n".join(
        (
            f"[{a['subject']} / {a['kind']} / valid_from={a.get('valid_from', 'null')} "
            f"/ observed_at={a.get('observed_at', 'null')} / source={a.get('source_title') or a.get('source_id') or a.get('source')}]\n"
            f"{a['content']}"
        )
        for a in atoms
    )

    model = os.environ.get("SYNTHESIS_MODEL") or os.environ.get("LLM_MODEL", "gemma4:e4b")
    client = _make_client()
    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Today's date: {today}\n\nQuery: {query}\n\nKnowledge atoms:\n{atoms_text}"},
    ]

    # Agent loop: up to 5 rounds to allow chained tool calls
    for _ in range(5):
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=_TOOLS, tool_choice="auto",
            extra_body={"num_ctx": 4096},
        )
        msg = resp.choices[0].message
        messages.append(msg)

        if not msg.tool_calls:
            answer = msg.content or ""
            return SynthesisResult(answer=answer, raw_response=answer, tool_calls=tool_calls_log)

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = _execute_tool(tc.function.name, args)
            tool_calls_log.append({
                "tool": tc.function.name,
                "args": args,
                "result": result,
            })
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # Fallback: ask for final answer after max rounds
    resp = client.chat.completions.create(model=model, messages=messages, extra_body={"num_ctx": 4096})
    answer = resp.choices[0].message.content or ""
    return SynthesisResult(answer=answer, raw_response=answer, tool_calls=tool_calls_log)
