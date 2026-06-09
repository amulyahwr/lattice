from __future__ import annotations

from typing import TYPE_CHECKING

from openai import OpenAI

if TYPE_CHECKING:
    from lattice.config import Config


def make_llm_client(cfg: "Config") -> OpenAI:
    resolved_url = (
        "http://localhost:11434/v1" if cfg.llm_provider == "ollama"
        else cfg.llm_base_url
    )
    resolved_key = "ollama" if cfg.llm_provider == "ollama" else cfg.llm_api_key
    kwargs: dict = {"api_key": resolved_key}
    if resolved_url:
        kwargs["base_url"] = resolved_url
    if cfg.llm_provider == "ollama":
        kwargs["timeout"] = 90.0
    return OpenAI(**kwargs)


def resolve_model(cfg: "Config", override: str | None = None) -> str:
    """Return model name, preferring *override* then cfg.llm_model.

    Raises EnvironmentError with a clear message if neither is set.
    """
    m = override or cfg.llm_model
    if not m:
        raise EnvironmentError(
            "LLM_MODEL is required but not set. "
            "Set it to a model name supported by your provider, e.g. "
            "LLM_MODEL=gpt-4o (openai) or LLM_MODEL=qwen3:4b (ollama)."
        )
    return m


def complete(
    messages: list[dict],
    cfg: "Config",
    text_format: type | None = None,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    if cfg.llm_provider != "ollama" and not cfg.llm_api_key:
        raise EnvironmentError(f"LLM_API_KEY is required for provider '{cfg.llm_provider}'")

    client = make_llm_client(cfg)
    m = resolve_model(cfg, model)

    kwargs: dict = {"model": m, "messages": messages}
    if text_format is not None:
        kwargs["response_format"] = {"type": "json_object"}
    if cfg.llm_provider == "ollama":
        ctx = num_ctx or cfg.llm_num_ctx
        kwargs["extra_body"] = {"num_ctx": ctx, "think": False}

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""
