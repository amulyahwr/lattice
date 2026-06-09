"""Tests for Anthropic via OpenAI-compat endpoint.

LLM_PROVIDER=openai + LLM_BASE_URL=https://api.anthropic.com/v1 routes through
the openai-compat client with a custom base URL. No extra_body in this path.
"""
from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module
from lattice.config import Config

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


def _compat_cfg(api_key="sk-ant-testkey") -> Config:
    return Config(
        llm_provider="openai",
        llm_model=ANTHROPIC_MODEL,
        llm_base_url=ANTHROPIC_BASE_URL,
        llm_api_key=api_key,
    )


class TestMakeLlmClientAnthropicCompat:
    def test_base_url_forwarded_to_client(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_compat_cfg())
        assert mock_cls.call_args.kwargs.get("base_url") == ANTHROPIC_BASE_URL

    def test_api_key_forwarded_to_client(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_compat_cfg(api_key="sk-ant-mykey"))
        assert mock_cls.call_args.kwargs.get("api_key") == "sk-ant-mykey"


class TestCompleteAnthropicCompat:
    def test_no_extra_body_for_openai_compat(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hello"}], _compat_cfg())
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" not in call_kwargs

    def test_returns_content(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("result text")
            result = llm_module.complete([{"role": "user", "content": "hello"}], _compat_cfg())
        assert result == "result text"

    def test_missing_api_key_raises(self):
        cfg = Config(llm_provider="openai", llm_model=ANTHROPIC_MODEL,
                     llm_base_url=ANTHROPIC_BASE_URL, llm_api_key=None)
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hello"}], cfg)

    def test_no_base_url_when_not_set(self):
        cfg = Config(llm_provider="openai", llm_model="gpt-4o",
                     llm_api_key="sk-openai-key", llm_base_url=None)
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(cfg)
        assert mock_cls.call_args.kwargs.get("base_url") is None
