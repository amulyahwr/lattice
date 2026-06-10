from __future__ import annotations

import time
from typing import TYPE_CHECKING

from openai import OpenAI

if TYPE_CHECKING:
    from lattice.config import Config


def _is_anthropic_model(model: str) -> bool:
    return model.startswith("anthropic/") or model.startswith("claude-")


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


def _anthropic_complete(
    messages: list[dict],
    model: str,
    cfg: "Config",
    text_format: type | None = None,
) -> str:
    """Call Claude via native Anthropic SDK for guaranteed structured output."""
    import anthropic

    # Strip the "anthropic/" prefix if routing via OpenRouter
    raw_model = model.removeprefix("anthropic/")

    base_url = cfg.llm_base_url or "https://api.anthropic.com"
    # Anthropic SDK appends /v1 internally — strip trailing /v1 to avoid double path
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    client = anthropic.Anthropic(api_key=cfg.llm_api_key, base_url=base_url)

    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_messages = [m for m in messages if m["role"] != "system"]
    system_text = "\n\n".join(system_parts) if system_parts else anthropic.NOT_GIVEN

    kwargs: dict = {
        "model": raw_model,
        "max_tokens": 4096,
        "messages": user_messages,
    }
    if system_text is not anthropic.NOT_GIVEN:
        kwargs["system"] = system_text

    if text_format is not None:
        import json as _json
        schema = text_format.model_json_schema()
        kwargs["output_config"] = {
            "format": {
                "type": "json_schema",
                "schema": schema,
            }
        }

    resp = client.messages.create(**kwargs)
    return resp.content[0].text if resp.content else ""


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
        self._cfg = cfg
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
        # Use native Anthropic SDK for Claude models — guarantees structured output
        if _is_anthropic_model(self.model) and self._cfg.llm_provider != "ollama":
            return _anthropic_complete(messages, self.model, self._cfg, text_format)
        kw: dict = {"messages": messages}
        if text_format is not None:
            kw["response_format"] = {"type": "json_object"}
        resp = self.create(**kw)
        return resp.choices[0].message.content or ""


_RATE_LIMIT_SIGNALS = ("429", "rate limit", "too many requests", "ratelimit")
_RETRY_DELAYS = (2.0, 5.0, 15.0)  # seconds between retries


def complete(
    messages: list[dict],
    cfg: "Config",
    text_format: type | None = None,
    model: str | None = None,
    num_ctx: int | None = None,
) -> str:
    """Free function used by ingest/supersession. Retries on rate-limit errors."""
    client = LLMClient(cfg, model=model)
    last_exc: Exception | None = None
    for attempt, delay in enumerate((*_RETRY_DELAYS, None)):
        try:
            return client.complete(messages, text_format=text_format)
        except Exception as exc:
            err = str(exc).lower()
            if any(sig in err for sig in _RATE_LIMIT_SIGNALS):
                last_exc = exc
                if delay is not None:
                    time.sleep(delay)
                continue
            raise  # non-rate-limit errors propagate immediately
    raise last_exc  # type: ignore[misc]
