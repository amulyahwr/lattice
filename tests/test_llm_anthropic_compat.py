"""Tests for Anthropic via OpenAI-compat endpoint (S11).

Uses LLM_PROVIDER=openai + LLM_BASE_URL=https://api.anthropic.com/v1 to route
through the openai litellm provider with a custom base URL.
"""
from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _make_response(text: str):
    resp = MagicMock()
    resp.output_text = text
    return resp


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


class TestModelStringOpenAICompat:
    def test_openai_provider_with_anthropic_model(self, monkeypatch):
        """Using provider=openai + anthropic model produces openai/<model> string."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", ANTHROPIC_MODEL)
        assert llm_module._model_string() == f"openai/{ANTHROPIC_MODEL}"

    def test_model_string_ignores_base_url(self, monkeypatch):
        """_model_string does not encode base URL — that's a complete() concern."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", ANTHROPIC_MODEL)
        monkeypatch.setenv("LLM_BASE_URL", ANTHROPIC_BASE_URL)
        assert llm_module._model_string() == f"openai/{ANTHROPIC_MODEL}"


class TestCompleteAnthropicCompat:
    def _compat_env(self, monkeypatch, api_key="sk-ant-testkey"):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", ANTHROPIC_MODEL)
        monkeypatch.setenv("LLM_BASE_URL", ANTHROPIC_BASE_URL)
        if api_key is not None:
            monkeypatch.setenv("LLM_API_KEY", api_key)

    def test_api_base_passed_to_litellm(self, monkeypatch):
        """complete() forwards LLM_BASE_URL as api_base to litellm.responses."""
        self._compat_env(monkeypatch)
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ok")) as mock:
            llm_module.complete([{"role": "user", "content": "hello"}])
        _, kwargs = mock.call_args
        assert kwargs.get("api_base") == ANTHROPIC_BASE_URL

    def test_model_string_is_openai_prefixed(self, monkeypatch):
        """complete() uses openai/<model> string when provider=openai."""
        self._compat_env(monkeypatch)
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ok")) as mock:
            llm_module.complete([{"role": "user", "content": "hello"}])
        _, kwargs = mock.call_args
        assert kwargs.get("model") == f"openai/{ANTHROPIC_MODEL}"

    def test_api_key_forwarded(self, monkeypatch):
        """complete() forwards the Anthropic API key to litellm."""
        self._compat_env(monkeypatch, api_key="sk-ant-mykey")
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ok")) as mock:
            llm_module.complete([{"role": "user", "content": "hello"}])
        _, kwargs = mock.call_args
        assert kwargs.get("api_key") == "sk-ant-mykey"

    def test_messages_forwarded(self, monkeypatch):
        """complete() passes messages as input kwarg."""
        self._compat_env(monkeypatch)
        messages = [{"role": "user", "content": "what is lattice?"}]
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ans")) as mock:
            llm_module.complete(messages)
        _, kwargs = mock.call_args
        assert kwargs.get("input") == messages

    def test_returns_output_text(self, monkeypatch):
        """complete() returns the output_text from the litellm response."""
        self._compat_env(monkeypatch)
        with patch("lattice.llm.litellm.responses", return_value=_make_response("result text")):
            result = llm_module.complete([{"role": "user", "content": "hello"}])
        assert result == "result text"

    def test_missing_api_key_raises_environment_error(self, monkeypatch):
        """Missing LLM_API_KEY with provider=openai raises EnvironmentError."""
        self._compat_env(monkeypatch, api_key=None)
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hello"}])

    def test_no_api_base_when_base_url_not_set(self, monkeypatch):
        """When LLM_BASE_URL is not set, api_base is NOT passed to litellm."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("LLM_API_KEY", "sk-openai-key")
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ok")) as mock:
            llm_module.complete([{"role": "user", "content": "hello"}])
        _, kwargs = mock.call_args
        assert "api_base" not in kwargs

    def test_no_extra_body_for_openai_compat(self, monkeypatch):
        """extra_body (ollama context window) is not set for openai-compat path."""
        self._compat_env(monkeypatch)
        with patch("lattice.llm.litellm.responses", return_value=_make_response("ok")) as mock:
            llm_module.complete([{"role": "user", "content": "hello"}])
        _, kwargs = mock.call_args
        assert "extra_body" not in kwargs
