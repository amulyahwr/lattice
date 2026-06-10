"""Tests for Anthropic model routing in llm.py.

Claude models (starting with "claude-" or "anthropic/") now route through the
native Anthropic SDK for guaranteed structured output. Non-Claude models on
openai-compat endpoints still use the OpenAI client.
"""
from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module
from lattice.config import Config

ANTHROPIC_BASE_URL = "https://openrouter.ai/api/v1"
CLAUDE_MODEL = "anthropic/claude-haiku-4-5"
OPENAI_MODEL = "openai/gpt-4o-mini"


def _make_anthropic_response(text: str):
    content_block = MagicMock()
    content_block.text = text
    resp = MagicMock()
    resp.content = [content_block]
    return resp


def _make_openai_completion(text: str):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _claude_cfg(api_key="sk-or-testkey") -> Config:
    return Config(
        llm_provider="openai",
        llm_model=CLAUDE_MODEL,
        llm_base_url=ANTHROPIC_BASE_URL,
        llm_api_key=api_key,
    )


def _openai_cfg(api_key="sk-openai-key") -> Config:
    return Config(
        llm_provider="openai",
        llm_model=OPENAI_MODEL,
        llm_base_url=None,
        llm_api_key=api_key,
    )


class TestMakeLlmClientAnthropicCompat:
    def test_base_url_forwarded_to_client(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_claude_cfg())
        assert mock_cls.call_args.kwargs.get("base_url") == ANTHROPIC_BASE_URL

    def test_api_key_forwarded_to_client(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_claude_cfg(api_key="sk-or-mykey"))
        assert mock_cls.call_args.kwargs.get("api_key") == "sk-or-mykey"


class TestCompleteAnthropicNativeSDK:
    """Claude models route through native Anthropic SDK regardless of base_url."""

    def test_claude_model_uses_anthropic_sdk(self):
        with patch("lattice.llm._anthropic_complete") as mock_native:
            mock_native.return_value = '{"atoms": []}'
            llm_module.complete([{"role": "user", "content": "hello"}], _claude_cfg())
        mock_native.assert_called_once()

    def test_claude_model_returns_content(self):
        with patch("lattice.llm._anthropic_complete") as mock_native:
            mock_native.return_value = "result text"
            result = llm_module.complete(
                [{"role": "user", "content": "hello"}], _claude_cfg()
            )
        assert result == "result text"

    def test_openai_model_uses_openai_client(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = (
                _make_openai_completion("ok")
            )
            llm_module.complete(
                [{"role": "user", "content": "hello"}], _openai_cfg()
            )
        mock_cls.return_value.chat.completions.create.assert_called_once()

    def test_openai_model_no_extra_body(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = (
                _make_openai_completion("ok")
            )
            llm_module.complete(
                [{"role": "user", "content": "hello"}], _openai_cfg()
            )
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" not in call_kwargs

    def test_missing_api_key_raises(self):
        cfg = Config(
            llm_provider="openai",
            llm_model=CLAUDE_MODEL,
            llm_base_url=ANTHROPIC_BASE_URL,
            llm_api_key=None,
        )
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hello"}], cfg)

    def test_no_base_url_when_not_set(self):
        cfg = Config(
            llm_provider="openai",
            llm_model=OPENAI_MODEL,
            llm_api_key="sk-openai-key",
            llm_base_url=None,
        )
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(cfg)
        assert mock_cls.call_args.kwargs.get("base_url") is None
