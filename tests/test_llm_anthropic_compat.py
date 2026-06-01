"""Tests for Anthropic via OpenAI-compat endpoint.

LLM_PROVIDER=openai + LLM_BASE_URL=https://api.anthropic.com/v1 routes through
the openai-compat client with a custom base URL. No extra_body in this path.
"""
from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _make_completion(text: str):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.fixture(autouse=True)
def clear_env(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def _compat_env(monkeypatch, api_key="sk-ant-testkey"):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", ANTHROPIC_MODEL)
    monkeypatch.setenv("LLM_BASE_URL", ANTHROPIC_BASE_URL)
    if api_key is not None:
        monkeypatch.setenv("LLM_API_KEY", api_key)


class TestMakeLlmClientAnthropicCompat:
    def test_base_url_forwarded_to_client(self, monkeypatch):
        _compat_env(monkeypatch)
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        assert mock_cls.call_args.kwargs.get("base_url") == ANTHROPIC_BASE_URL

    def test_api_key_forwarded_to_client(self, monkeypatch):
        _compat_env(monkeypatch, api_key="sk-ant-mykey")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        assert mock_cls.call_args.kwargs.get("api_key") == "sk-ant-mykey"


class TestCompleteAnthropicCompat:
    def test_no_extra_body_for_openai_compat(self, monkeypatch):
        _compat_env(monkeypatch)
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hello"}])
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" not in call_kwargs

    def test_returns_content(self, monkeypatch):
        _compat_env(monkeypatch)
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("result text")
            result = llm_module.complete([{"role": "user", "content": "hello"}])
        assert result == "result text"

    def test_missing_api_key_raises(self, monkeypatch):
        _compat_env(monkeypatch, api_key=None)
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hello"}])

    def test_no_base_url_when_env_not_set(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("LLM_API_KEY", "sk-openai-key")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        assert mock_cls.call_args.kwargs.get("base_url") is None
