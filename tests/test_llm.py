from unittest.mock import MagicMock, patch

import pytest

import lattice.llm as llm_module


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
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL", "LLM_NUM_CTX"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LLM_MODEL", "test-model")


class TestMakeLlmClient:
    def test_ollama_uses_localhost(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        kwargs = mock_cls.call_args.kwargs
        assert "localhost:11434" in kwargs.get("base_url", "")

    def test_ollama_api_key_is_ollama(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        assert mock_cls.call_args.kwargs.get("api_key") == "ollama"

    def test_openai_uses_provided_api_key(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_API_KEY", "sk-mykey")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client()
        assert mock_cls.call_args.kwargs.get("api_key") == "sk-mykey"

    def test_explicit_base_url_forwarded(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("lattice.llm.OpenAI") as mock_cls:
            llm_module.make_llm_client(base_url="https://api.example.com/v1")
        assert mock_cls.call_args.kwargs.get("base_url") == "https://api.example.com/v1"


class TestComplete:
    def test_returns_content_string(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("hello")
            result = llm_module.complete([{"role": "user", "content": "hi"}])
        assert result == "hello"

    def test_messages_forwarded(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        messages = [{"role": "user", "content": "what is 2+2?"}]
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("4")
            llm_module.complete(messages)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("messages") == messages

    def test_ollama_gets_extra_body(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hi"}])
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" in call_kwargs
        assert call_kwargs["extra_body"].get("think") is False

    def test_openai_no_extra_body(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_API_KEY", "sk-test")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            llm_module.complete([{"role": "user", "content": "hi"}])
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert "extra_body" not in call_kwargs

    def test_missing_llm_model_raises(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        with pytest.raises(EnvironmentError, match="LLM_MODEL"):
            llm_module.complete([{"role": "user", "content": "hi"}])

    def test_missing_api_key_raises_for_openai(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        with pytest.raises(EnvironmentError, match="LLM_API_KEY"):
            llm_module.complete([{"role": "user", "content": "hi"}])

    def test_missing_api_key_ok_for_ollama(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("ok")
            result = llm_module.complete([{"role": "user", "content": "hi"}])
        assert result == "ok"

    def test_text_format_sets_json_response_format(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        with patch("lattice.llm.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _make_completion("{}")
            llm_module.complete([{"role": "user", "content": "hi"}], text_format=dict)
        call_kwargs = mock_cls.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs.get("response_format") == {"type": "json_object"}
