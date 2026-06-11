"""Tests for STORY-029 — Memory Sparks (now: journey tree + /start)."""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lattice.telegram_bot import _build_journey_text


def run(coro):
    return asyncio.run(coro)


def _make_atom(subject: str, kind: str = "fact", is_superseded: bool = False) -> MagicMock:
    a = MagicMock()
    a.subject = subject
    a.kind = kind
    a.is_superseded = is_superseded
    return a


def _make_update(user_id: int = 42):
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user.id = user_id
    update.effective_chat.id = 123
    return update


def _make_context():
    ctx = MagicMock()
    ctx.chat_data = {}
    ctx.args = []
    return ctx


# ---------------------------------------------------------------------------
# _build_journey_text — cross-channel journey tree
# ---------------------------------------------------------------------------

class TestBuildJourneyText:
    def test_groups_by_query_topic(self):
        turns = [
            {"question": "Tell me about Topic A", "query_topic": "Topic A", "subjects": ["unrelated subject"]},
            {"question": "what is its detail?", "subjects": [], "context_reset": False},
        ]
        text = _build_journey_text(turns)
        assert "● Topic A" in text
        assert "Tell me about Topic A" in text

    def test_empty_turns_returns_empty(self):
        assert _build_journey_text([]) == ""

    def test_turns_without_topic_or_subject_skipped(self):
        turns = [{"question": "why?", "subjects": []}]
        assert _build_journey_text(turns) == ""

    def test_falls_back_to_subjects_when_no_query_topic(self):
        turns = [{"question": "how about connections?", "subjects": ["Postgres"]}]
        text = _build_journey_text(turns)
        assert "● Postgres" in text

    def test_multiple_branches(self):
        turns = [
            {"question": "Tell me about Mars", "query_topic": "Mars", "subjects": []},
            {"question": "Tell me about Jupiter", "query_topic": "Jupiter", "subjects": []},
        ]
        text = _build_journey_text(turns)
        assert "● Mars" in text
        assert "● Jupiter" in text

    def test_followup_uses_context_reset_flag(self):
        turns = [
            {"question": "Tell me about Topic B", "query_topic": "Topic B", "subjects": [], "context_reset": True},
            {"question": "what is its detail?", "subjects": [], "context_reset": False},
        ]
        text = _build_journey_text(turns)
        assert "● Topic B" in text
        assert text.count("●") == 1, "follow-up should not create a new branch"
        assert "what is its detail?" in text

    def test_possessive_folds_into_existing_branch(self):
        turns = [
            {"question": "Tell me about Alpha", "query_topic": "Alpha", "subjects": [], "context_reset": True},
            {"question": "What is Alphas' detail?", "query_topic": "Alpha", "subjects": [], "context_reset": True},
        ]
        text = _build_journey_text(turns)
        assert "● Alpha" in text
        assert text.count("●") == 1, "possessive overlap should fold into existing branch"

    def test_context_reset_true_starts_new_branch(self):
        turns = [
            {"question": "Tell me about Topic C", "query_topic": "Topic C", "subjects": [], "context_reset": True},
            {"question": "Tell me about Topic D", "query_topic": "Topic D", "subjects": [], "context_reset": True},
        ]
        text = _build_journey_text(turns)
        assert "● Topic C" in text
        assert "● Topic D" in text
        assert text.count("●") == 2


# ---------------------------------------------------------------------------
# Telegram /start — no atom suggestions, just commands
# ---------------------------------------------------------------------------

class TestTelegramStart:
    def test_start_shows_commands(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "/ask" in reply
        assert "/journey" in reply
        assert "/status" in reply

    def test_start_not_allowed_sends_nothing(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update(user_id=999)
        ctx = _make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=False):
            run(_handle_start(update, ctx))
        update.message.reply_text.assert_not_called()


# ---------------------------------------------------------------------------
# lc status — topics line
# ---------------------------------------------------------------------------

def _run_lc_status(atoms: list, capsys):
    import lattice.cli as cli_mod
    with patch("lattice.db.LatticeDB") as MockDB:
        with patch("lattice.config.Config") as MockCfg:
            MockCfg.from_env.return_value.lattice_dir = "/fake"
            MockDB.return_value.all.return_value = atoms
            sys.argv = ["lc", "status"]
            cli_mod.lc()
    return capsys.readouterr().out


class TestLcStatus:
    def test_status_shows_memory_count(self, capsys):
        atoms = [_make_atom("coffee"), _make_atom("hiking")]
        out = _run_lc_status(atoms, capsys)
        assert "2" in out

    def test_status_shows_topics(self, capsys):
        atoms = [_make_atom("coffee", "preference"), _make_atom("hiking", "fact")]
        out = _run_lc_status(atoms, capsys)
        assert "coffee" in out or "hiking" in out

    def test_status_no_atoms_no_topics(self, capsys):
        out = _run_lc_status([], capsys)
        assert "0" in out
        assert "Topics:" not in out

    def test_status_skips_superseded(self, capsys):
        atoms = [
            _make_atom("coffee", is_superseded=True),
            _make_atom("hiking", is_superseded=False),
        ]
        out = _run_lc_status(atoms, capsys)
        assert "1" in out
        assert "coffee" not in out

    def test_status_shows_at_most_5_topics(self, capsys):
        atoms = [_make_atom(f"topic{i}") for i in range(10)]
        out = _run_lc_status(atoms, capsys)
        # Topics: topic0…topic4 — max 5
        topic_count = sum(1 for i in range(10) if f"topic{i}" in out)
        assert topic_count <= 5

    def test_status_skips_atoms_with_no_subject(self, capsys):
        atoms = [_make_atom(None), _make_atom("coffee")]
        out = _run_lc_status(atoms, capsys)
        assert "coffee" in out
