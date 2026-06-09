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
    m = override or cfg.llm_model
    if not m:
        raise EnvironmentError(
            "LLM_MODEL is required but not set. "
            "Set it to a model name supported by your provider, e.g. "
            "LLM_MODEL=gpt-4o (openai) or LLM_MODEL=qwen3:4b (ollama)."
        )
    return m


class LLMClient:
    """Single seam for all LLM calls. Encapsulates provider routing, model
    resolution, and Ollama-specific extra_body. Callers use complete() or
    create() — no provider awareness leaks out."""

    def __init__(self, cfg: "Config", model: str | None = None) -> None:
        if cfg.llm_provider != "ollama" and not cfg.llm_api_key:
            raise EnvironmentError(
                f"LLM_API_KEY is required for provider '{cfg.llm_provider}'"
            )
        self.model = resolve_model(cfg, model)
        self._client = make_llm_client(cfg)
        self._extra: dict | None = (
            {"num_ctx": cfg.llm_num_ctx, "think": False}
            if cfg.llm_provider == "ollama" else None
        )

    def create(self, **kwargs):
        """Call chat.completions.create with model + extra_body injected."""
        kwargs.setdefault("model", self.model)
        if self._extra and "extra_body" not in kwargs:
            kwargs["extra_body"] = self._extra
        return self._client.chat.completions.create(**kwargs)

    def complete(self, messages: list[dict], text_format: type | None = None) -> str:
        kw: dict = {"messages": messages}
        if text_format is not None:
            kw["response_format"] = {"type": "json_object"}
        resp = self.create(**kw)
        return resp.choices[0].message.content or ""


def complete(
    messages: list[dict],
    cfg: "Config",
    text_format: type | None = None,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Free function used by ingest/supersession. Delegates to LLMClient."""
    return LLMClient(cfg, model=model).complete(messages, text_format=text_format)
