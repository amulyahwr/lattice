from __future__ import annotations

import os

from openai import OpenAI


def make_llm_client(base_url: str | None = None, api_key: str | None = None) -> OpenAI:
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    resolved_url = base_url or (
        "http://localhost:11434/v1" if provider == "ollama"
        else os.environ.get("LLM_BASE_URL")
    )
    resolved_key = api_key or (
        "ollama" if provider == "ollama"
        else os.environ.get("LLM_API_KEY")
    )
    kwargs: dict = {"api_key": resolved_key}
    if resolved_url:
        kwargs["base_url"] = resolved_url
    if provider == "ollama":
        kwargs["timeout"] = 90.0
    return OpenAI(**kwargs)


def resolve_model(override: str | None = None) -> str:
    """Return the model name to use, preferring *override* then LLM_MODEL env var.

    Raises EnvironmentError with a clear message if neither is set.
    """
    m = override or os.environ.get("LLM_MODEL")
    if not m:
        raise EnvironmentError(
            "LLM_MODEL is required but not set. "
            "Set it to a model name supported by your provider, e.g. "
            "LLM_MODEL=gpt-4o (openai) or LLM_MODEL=qwen3:4b (ollama)."
        )
    return m


def complete(
    messages: list[dict],
    text_format: type | None = None,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    provider = os.environ.get("LLM_PROVIDER", "ollama")
    api_key = os.environ.get("LLM_API_KEY")
    if provider != "ollama" and not api_key:
        raise EnvironmentError(f"LLM_API_KEY is required for provider '{provider}'")

    client = make_llm_client()
    m = resolve_model(model)

    kwargs: dict = {"model": m, "messages": messages}
    if text_format is not None:
        kwargs["response_format"] = {"type": "json_object"}
    if provider == "ollama":
        ctx = num_ctx or int(os.environ.get("LLM_NUM_CTX", "4096"))
        kwargs["extra_body"] = {"num_ctx": ctx, "think": False}

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
