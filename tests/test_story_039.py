"""STORY-039 — Multi-turn query reformulation tests."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lattice.config import Config
from lattice.conversation import is_followup, reformulate


# ── is_followup tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("query", [
    # fast-path phrases
    "why",
    "why?",
    "how?",
    "more?",
    "what else?",
    "tell me more",
    "go on",
    "elaborate",
    # anaphoric short
    "when was that?",
    "what did it say?",
    "tell me about it",
    "how did that go?",
    "what happened then?",
    "who did that?",
    # no proper noun, short
    "what were the reasons?",
    "can you explain more?",
])
def test_is_followup_true(query):
    assert is_followup(query) is True


@pytest.mark.parametrize("query", [
    "What did I decide about Postgres?",
    "What do I know about React hooks?",
    "Tell me about my travel plans to Japan",
    "What is the status of the Lattice project?",
    "How does BM25 ranking work in Lattice?",
    "What did John Doe say about the database migration?",
])
def test_is_followup_false(query):
    assert is_followup(query) is False


def test_is_followup_empty_returns_false():
    assert is_followup("") is False


def test_is_followup_single_word_anaphoric():
    assert is_followup("when?") is True


def test_is_followup_spell_typo_short():
    # Short typo query with no proper nouns — should trigger
    assert is_followup("whn was that") is True


# ── reformulate tests ──────────────────────────────────────────────────────────

@pytest.fixture
def cfg(tmp_path):
    return Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")


def test_reformulate_no_history_returns_original(cfg):
    result = reformulate("when was that?", [], cfg)
    assert result == "when was that?"


def test_reformulate_calls_llm_and_returns_result(cfg):
    history = [{"question": "What did I decide about Postgres?", "answer": "You chose Postgres over SQLite."}]
    with patch("lattice.conversation.complete", return_value="When did I decide to use Postgres over SQLite?") as mock_complete:
        result = reformulate("when was that?", history, cfg)
    assert result == "When did I decide to use Postgres over SQLite?"
    mock_complete.assert_called_once()


def test_reformulate_falls_back_on_empty_response(cfg):
    history = [{"question": "What is my coffee preference?", "answer": "You prefer oat milk lattes."}]
    with patch("lattice.conversation.complete", return_value=""):
        result = reformulate("why?", history, cfg)
    assert result == "why?"


def test_reformulate_falls_back_on_identical_response(cfg):
    history = [{"question": "Tell me about Postgres", "answer": "Postgres is a database."}]
    with patch("lattice.conversation.complete", return_value="when was that?"):
        result = reformulate("when was that?", history, cfg)
    assert result == "when was that?"


def test_reformulate_falls_back_on_too_long_response(cfg):
    history = [{"question": "What did I decide?", "answer": "You decided X."}]
    # 4× length of original query = too long
    long_response = "When did I decide " + "something " * 50
    with patch("lattice.conversation.complete", return_value=long_response):
        result = reformulate("when?", history, cfg)
    assert result == "when?"


def test_reformulate_falls_back_on_exception(cfg):
    history = [{"question": "What do I prefer?", "answer": "You prefer tea."}]
    with patch("lattice.conversation.complete", side_effect=RuntimeError("LLM error")):
        result = reformulate("why?", history, cfg)
    assert result == "why?"


def test_reformulate_uses_reformulation_model(tmp_path):
    cfg = Config(
        lattice_dir=tmp_path,
        llm_provider="openai",
        llm_model="gpt-4o",
        reformulation_model="gpt-4o-mini",
    )
    history = [{"question": "What is my favourite coffee?", "answer": "You prefer oat milk lattes."}]
    with patch("lattice.conversation.complete", return_value="What is my favourite coffee?") as mock_complete:
        reformulate("what about it?", history, cfg)
    call_kwargs = mock_complete.call_args
    assert call_kwargs.kwargs.get("model") == "gpt-4o-mini" or call_kwargs.args[2] == "gpt-4o-mini"


def test_reformulate_falls_back_to_ingest_model(tmp_path):
    cfg = Config(
        lattice_dir=tmp_path,
        llm_provider="openai",
        llm_model="gpt-4o",
        ingest_model="gpt-4o-mini",
        reformulation_model=None,
    )
    history = [{"question": "What is my favourite coffee?", "answer": "You prefer oat milk lattes."}]
    with patch("lattice.conversation.complete", return_value="What is my favourite coffee?") as mock_complete:
        reformulate("what about it?", history, cfg)
    call_kwargs = mock_complete.call_args
    assert call_kwargs.kwargs.get("model") == "gpt-4o-mini" or call_kwargs.args[2] == "gpt-4o-mini"


def test_reformulate_strips_quotes(cfg):
    history = [{"question": "What is my coffee preference?", "answer": "You prefer oat milk lattes."}]
    with patch("lattice.conversation.complete", return_value='"What is my coffee preference?"'):
        result = reformulate("what about it?", history, cfg)
    assert result == "What is my coffee preference?"


def test_reformulate_history_truncated_to_conversation_turns(tmp_path):
    cfg = Config(
        lattice_dir=tmp_path,
        llm_provider="ollama",
        llm_model="test-model",
        conversation_turns=2,
    )
    # 4 turns provided — only last 2 should be passed to reformulate in practice
    # (truncation happens in app.py; here we just verify reformulate handles whatever it gets)
    history = [
        {"question": "Q1", "answer": "A1"},
        {"question": "Q2", "answer": "A2"},
    ]
    with patch("lattice.conversation.complete", return_value="Reformulated question") as mock_complete:
        result = reformulate("what about it?", history, cfg)
    assert result == "Reformulated question"
    # Verify LLM prompt contains both history turns
    prompt = mock_complete.call_args.args[0][-1]["content"]
    assert "Q1" in prompt
    assert "Q2" in prompt


# ── config tests ───────────────────────────────────────────────────────────────

def test_config_reformulation_defaults(tmp_path):
    cfg = Config(lattice_dir=tmp_path)
    assert cfg.reformulation_enabled is True
    assert cfg.conversation_turns == 2
    assert cfg.reformulation_model is None


def test_config_reformulation_env(tmp_path, monkeypatch):
    monkeypatch.setenv("LATTICE_REFORMULATION", "0")
    monkeypatch.setenv("LATTICE_CONVERSATION_TURNS", "3")
    monkeypatch.setenv("REFORMULATION_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
    cfg = Config.from_env()
    assert cfg.reformulation_enabled is False
    assert cfg.conversation_turns == 3
    assert cfg.reformulation_model == "gpt-4o-mini"
