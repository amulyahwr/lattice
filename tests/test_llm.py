from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module
from lattice.config import Config


def _cfg(**kwargs) -> Config:
    kwargs.setdefault("llm_model", "test-model")
    return Config(**kwargs)


def _make_completion(text: str):
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestMakeLlmClient:
    def test_ollama_uses_localhost(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="ollama"))
        kwargs = mock_cls.call_args.kwargs
        assert "localhost:11434" in kwargs.get("base_url", "")

    def test_ollama_api_key_is_ollama(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="ollama"))
        assert mock_cls.call_args.kwargs.get("api_key") == "ollama"

    def test_openai_uses_provided_api_key(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="openai", llm_api_key="sk-mykey"))
        assert mock_cls.call_args.kwargs.get("api_key") == "sk-mykey"

    def test_explicit_base_url_forwarded(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(
                llm_provider="openai",
                llm_api_key="sk-test",
                llm_base_url="https://api.example.com/v1",
            ))
        assert mock_cls.call_args.kwargs.get("base_url") == "https://api.example.com/v1"


class TestComplete:
    def test_returns_content_string(self):
        cfg = _cfg(llm_provider="ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("hello")
            result = llm_module.complete([{"role": "user", "content": "hi"}], cfg)
        assert result == "hello"

    def test_messages_forwarded(self):
        cfg = _cfg(llm_provider="ollama")
        messages = [{"role": "user", "content": "what is 2+2?"}]
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("4")
            llm_module.complete(messages, cfg)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("messages") == messages

    def test_ollama_gets_extra_body(self):
        cfg = _cfg(llm_provider="ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hi"}], cfg)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" in call_kwargs
        assert call_kwargs["extra_body"].get("think") is False

    def test_openai_no_extra_body(self):
        cfg = _cfg(llm_provider="openai", llm_api_key="sk-test")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hi"}], cfg)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" not in call_kwargs

    def test_missing_llm_model_raises(self):
        cfg = Config(llm_provider="ollama", llm_model=None)
        with pytest.raises(EnvironmentError, match="LLM_MODEL"):
            llm_module.complete([{"role": "user", "content": "hi"}], cfg)

    def test_missing_api_key_raises_for_openai(self):
        cfg = _cfg(llm_provider="openai", llm_api_key=None)
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hi"}], cfg)

    def test_missing_api_key_ok_for_ollama(self):
        cfg = _cfg(llm_provider="ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            result = llm_module.complete([{"role": "user", "content": "hi"}], cfg)
        assert result == "ok"

    def test_text_format_sets_json_response_format(self):
        cfg = _cfg(llm_provider="ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("{}")
            llm_module.complete([{"role": "user", "content": "hi"}], cfg, text_format=dict)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}


class TestResolveModel:
    def test_returns_cfg_model(self):
        cfg = _cfg(llm_model="gpt-4o")
        assert llm_module.resolve_model(cfg) == "gpt-4o"

    def test_override_takes_priority(self):
        cfg = _cfg(llm_model="gpt-4o")
        assert llm_module.resolve_model(cfg, override="claude-3") == "claude-3"

    def test_raises_when_no_model(self):
        cfg = Config(llm_model=None)
        with pytest.raises(EnvironmentError, match="LLM_MODEL"):
            llm_module.resolve_model(cfg)

    def test_ollama_timeout_set(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="ollama"))
        assert mock_cls.call_args.kwargs.get("timeout") == 90.0

    def test_openai_no_timeout(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="openai", llm_api_key="sk-x"))
        assert "timeout" not in mock_cls.call_args.kwargs

    def test_openai_no_base_url_when_not_set(self):
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(_cfg(llm_provider="openai", llm_api_key="sk-x", llm_base_url=None))
        assert "base_url" not in mock_cls.call_args.kwargs

    def test_ollama_extra_body_uses_cfg_num_ctx(self):
        cfg = _cfg(llm_provider="ollama", llm_num_ctx=8192)
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hi"}], cfg)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs["extra_body"]["num_ctx"] == 8192
