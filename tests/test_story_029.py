"""Tests for STORY-029 — Memory Sparks."""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lattice.telegram_bot import _spark_question


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
# _spark_question — question generation
# ---------------------------------------------------------------------------

class TestSparkQuestion:
    # --- positive ---
    def test_decision_kind(self):
        atom = _make_atom("postgres", kind="decision")
        assert _spark_question(atom) == "What did I decide about postgres?"

    def test_preference_kind(self):
        atom = _make_atom("coffee", kind="preference")
        assert _spark_question(atom) == "What do I prefer about coffee?"

    def test_fact_kind_uses_tell_me(self):
        atom = _make_atom("travel", kind="fact")
        assert _spark_question(atom) == "Tell me about travel"

    def test_unknown_kind_uses_tell_me(self):
        atom = _make_atom("books", kind="goal")
        assert _spark_question(atom) == "Tell me about books"

    # --- edge ---
    def test_no_subject_falls_back_to_that(self):
        atom = _make_atom(None, kind="preference")
        assert _spark_question(atom) == "What do I prefer about that?"

    def test_empty_subject_falls_back_to_that(self):
        atom = _make_atom("", kind="decision")
        assert _spark_question(atom) == "What did I decide about that?"


# ---------------------------------------------------------------------------
# Telegram /start — with atoms
# ---------------------------------------------------------------------------

def _patch_db(atoms):
    """Patch LatticeDB at source so lazy imports in telegram_bot and cli pick it up."""
    mock_db = MagicMock()
    mock_db.all.return_value = atoms
    mock_db_cls = MagicMock(return_value=mock_db)
    return patch("lattice.db.LatticeDB", mock_db_cls)


class TestTelegramStart:
    # --- positive ---
    def test_start_with_atoms_shows_suggestions(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        atoms = [
            _make_atom("coffee", "preference"),
            _make_atom("postgres", "decision"),
            _make_atom("travel", "fact"),
        ]
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with _patch_db(atoms):
                run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "coffee" in reply or "postgres" in reply or "travel" in reply

    def test_start_with_atoms_shows_at_most_3_suggestions(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        atoms = [_make_atom(f"topic{i}", "fact") for i in range(6)]
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with _patch_db(atoms):
                run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        # Count "Tell me about" occurrences — should be exactly 3
        assert reply.count("Tell me about") == 3

    def test_start_without_atoms_shows_empty_message(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with _patch_db([]):
                run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "what's on your mind" in reply.lower() or "good to have you" in reply.lower()

    def test_start_excludes_superseded_atoms(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        atoms = [
            _make_atom("coffee", "preference", is_superseded=True),
            _make_atom("hiking", "fact", is_superseded=False),
        ]
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with _patch_db(atoms):
                run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "hiking" in reply
        assert "coffee" not in reply

    # --- negative ---
    def test_start_not_allowed_sends_nothing(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update(user_id=999)
        ctx = _make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=False):
            run(_handle_start(update, ctx))
        update.message.reply_text.assert_not_called()

    # --- edge ---
    def test_start_with_one_atom_shows_one_suggestion(self):
        from lattice.telegram_bot import _handle_start
        update = _make_update()
        ctx = _make_context()
        atoms = [_make_atom("sleep", "preference")]
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with _patch_db(atoms):
                run(_handle_start(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "sleep" in reply


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
