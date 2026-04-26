"""LLM client — AsyncOpenAI pointed at LM Studio's local server.

LM Studio exposes an OpenAI-compatible API at http://localhost:1234/v1.
No litellm needed — the openai SDK handles everything.

Hard fails on any error: network, timeout, empty response.
"""

from __future__ import annotations

from openai import AsyncOpenAI

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


async def chat(system: str, user: str, temperature: float = 0.1) -> str:
    """Single async chat completion against LM Studio.

    Raises on network errors, timeouts, or empty responses.
    """
    if not settings.lm_studio_model:
        raise RuntimeError(
            "LATTICE_LM_STUDIO_MODEL is not set. "
            "Copy the model name from LM Studio's server tab and set the env var."
        )

    response = await _get_client().chat.completions.create(
        model=settings.lm_studio_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError("LLM returned an empty response")
    return content.strip()
