"""Tests for STORY-032 — Rediscovery highlight."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lattice.web.app import app

client = TestClient(app)


def run(coro):
    return asyncio.run(coro)


def _make_update(text: str, user_id: int = 42, chat_id: int = 123):
    update = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    update.effective_user.id = user_id
    update.effective_chat.id = chat_id
    return update


def _make_context(chat_data: dict | None = None):
    ctx = MagicMock()
    ctx.chat_data = chat_data or {}
    ctx.args = []
    return ctx


def _iso(days_ago: int) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return ts.isoformat()


# ---------------------------------------------------------------------------
# /api/answer — atoms metadata in response
# ---------------------------------------------------------------------------

class TestApiAnswerAtomsMetadata:
    def test_response_includes_atoms_field(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[
            {"atom_id": "a1", "ingested_at": _iso(5), "content": "test", "subject": "s", "kind": "fact"}
        ]):
            with patch("lattice.web.app.synthesize") as mock_synth:
                mock_synth.return_value = MagicMock(answer="You prefer dark coffee.")
                resp = client.post("/api/answer", json={"question": "what do I like?"})
        assert "atoms" in resp.json()

    def test_atoms_field_contains_ingested_at(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        ingested = _iso(40)
        with patch("lattice.web.app.select", return_value=[
            {"atom_id": "a1", "ingested_at": ingested, "content": "test", "subject": "s", "kind": "fact"}
        ]):
            with patch("lattice.web.app.synthesize") as mock_synth:
                mock_synth.return_value = MagicMock(answer="Coffee preference noted.")
                resp = client.post("/api/answer", json={"question": "q"})
        atoms = resp.json()["atoms"]
        assert len(atoms) == 1
        assert atoms[0]["ingested_at"] == ingested

    def test_atoms_field_contains_atom_id(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[
            {"atom_id": "abc123", "ingested_at": _iso(5), "content": "x", "subject": "s", "kind": "fact"}
        ]):
            with patch("lattice.web.app.synthesize") as mock_synth:
                mock_synth.return_value = MagicMock(answer="Answer.")
                resp = client.post("/api/answer", json={"question": "q"})
        assert resp.json()["atoms"][0]["atom_id"] == "abc123"

    def test_no_atoms_returns_empty_list(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[]):
            resp = client.post("/api/answer", json={"question": "q"})
        # When no atoms, atom_count=0 and atoms key absent (returns early)
        assert resp.json()["atom_count"] == 0

    def test_multiple_atoms_all_included(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[
            {"atom_id": "a1", "ingested_at": _iso(5), "content": "x", "subject": "s1", "kind": "fact"},
            {"atom_id": "a2", "ingested_at": _iso(60), "content": "y", "subject": "s2", "kind": "fact"},
        ]):
            with patch("lattice.web.app.synthesize") as mock_synth:
                mock_synth.return_value = MagicMock(answer="Both facts noted.")
                resp = client.post("/api/answer", json={"question": "q"})
        assert len(resp.json()["atoms"]) == 2


# ---------------------------------------------------------------------------
# Telegram _do_recall — old-memory note
# ---------------------------------------------------------------------------

class TestTelegramRediscovery:
    def _mock_resp(self, answer: str, atoms: list[dict], atom_count: int = 1) -> MagicMock:
        body = {"ok": True, "answer": answer, "atom_count": atom_count, "atoms": atoms}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    # --- positive ---
    def test_old_atom_appends_rediscovery_note(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("what do I prefer?")
        ctx = _make_context()
        atoms = [{"atom_id": "a1", "ingested_at": _iso(34)}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("You prefer dark coffee.", atoms)):
            run(_do_recall(update, ctx, "what do I prefer?"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "34 days ago" in all_replies

    def test_note_uses_oldest_atom_when_multiple_old(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [
            {"atom_id": "a1", "ingested_at": _iso(35)},
            {"atom_id": "a2", "ingested_at": _iso(50)},
        ]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms, atom_count=2)):
            run(_do_recall(update, ctx, "q"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "50 days ago" in all_replies

    def test_note_not_appended_for_recent_atoms(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [{"atom_id": "a1", "ingested_at": _iso(5)}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Fresh answer.", atoms)):
            run(_do_recall(update, ctx, "q"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "days ago" not in all_replies

    def test_boundary_exactly_30_days_triggers_note(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [{"atom_id": "a1", "ingested_at": _iso(30)}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms)):
            run(_do_recall(update, ctx, "q"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "days ago" in all_replies

    def test_boundary_29_days_no_note(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [{"atom_id": "a1", "ingested_at": _iso(29)}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms)):
            run(_do_recall(update, ctx, "q"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "days ago" not in all_replies

    # --- negative ---
    def test_no_atoms_field_in_body_no_crash(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        body = {"ok": True, "answer": "Answer.", "atom_count": 1}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(body).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            run(_do_recall(update, ctx, "q"))  # must not raise
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "days ago" not in all_replies

    def test_malformed_ingested_at_skipped(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [{"atom_id": "a1", "ingested_at": "not-a-date"}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms)):
            run(_do_recall(update, ctx, "q"))  # must not raise
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "days ago" not in all_replies

    def test_missing_ingested_at_skipped(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [{"atom_id": "a1"}]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms)):
            run(_do_recall(update, ctx, "q"))  # must not raise

    # --- edge ---
    def test_mix_old_and_recent_atoms_shows_oldest(self):
        from lattice.telegram_bot import _do_recall
        update = _make_update("q")
        ctx = _make_context()
        atoms = [
            {"atom_id": "a1", "ingested_at": _iso(5)},   # recent — skip
            {"atom_id": "a2", "ingested_at": _iso(45)},  # old — include
        ]
        with patch("urllib.request.urlopen", return_value=self._mock_resp("Answer.", atoms, atom_count=2)):
            run(_do_recall(update, ctx, "q"))
        all_replies = " ".join(c[0][0] for c in update.message.reply_text.call_args_list)
        assert "45 days ago" in all_replies
