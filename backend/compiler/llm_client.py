"""LLM client — AsyncOpenAI pointed at LM Studio's local server.

LM Studio exposes an OpenAI-compatible API at http://localhost:1234/v1.
No litellm needed — the openai SDK handles everything.

Hard fails on any error: network, timeout, empty response.
"""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from backend.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.lm_studio_base_url,
            api_key="lm-studio",  # LM Studio accepts any non-empty key
            timeout=settings.lm_studio_timeout,
        )
    return _client


async def chat(
    system: str,
    user: str,
    response_format: type[BaseModel] | dict[str, Any],
    temperature: float = 0.1,
) -> str:
    """Single async chat completion against LM Studio.

    response_format is required. Pass a Pydantic model class to enforce a JSON schema
    on the model's output (prevents type hallucinations). Pass a raw dict to forward
    any OpenAI-compatible response_format directly.

    Raises on network errors, timeouts, or empty responses.
    """
    if not settings.lm_studio_model:
        raise RuntimeError(
            "LATTICE_LM_STUDIO_MODEL is not set. "
            "Copy the model name from LM Studio's server tab and set the env var."
        )

    create_kwargs: dict[str, Any] = {
        "model": settings.lm_studio_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }

    if isinstance(response_format, dict):
        create_kwargs["response_format"] = response_format
    else:
        create_kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": response_format.__name__,
                "schema": response_format.model_json_schema(),
                "strict": False,  # strict=True requires OpenAI; False works with LM Studio
            },
        }

    response = await _get_client().chat.completions.create(**create_kwargs)
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty response")
    return content.strip()
