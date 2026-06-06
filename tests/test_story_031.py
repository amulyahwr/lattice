"""Tests for STORY-031 — Weekly memory report + topic depth cards."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from starlette.testclient import TestClient

from lattice.web.app import app, _utc_today
from lattice.telegram_bot import _topic_depth_message

client = TestClient(app)


def run(coro):
    return asyncio.run(coro)


def _make_atom(subject: str, kind: str = "fact", ingested_days_ago: int = 0,
               is_superseded: bool = False) -> MagicMock:
    a = MagicMock()
    a.subject = subject
    a.kind = kind
    a.is_superseded = is_superseded
    ts = datetime.now(timezone.utc) - timedelta(days=ingested_days_ago)
    a.ingested_at = ts
    a.observed_at = ts
    a.atom_id = f"atom_{subject}_{ingested_days_ago}"
    a.source_id = "test"
    return a


# ---------------------------------------------------------------------------
# GET /api/usage/weekly
# ---------------------------------------------------------------------------

class TestApiUsageWeekly:
    def test_returns_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/weekly")
        assert resp.status_code == 200
        body = resp.json()
        for field in ["atoms_this_week", "recalls_this_week", "topics_this_week", "new_topics", "top_topic", "streak"]:
            assert field in body

    def test_counts_recalls_this_week(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        (tmp_path / "usage.jsonl").write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 0, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"ts": f"{today}T11:00:00+00:00", "query_hash": "b", "selection_ms": 10, "synthesis_ms": 0, "atom_count": 1, "channel": "telegram"}) + "\n"
        )
        resp = client.get("/api/usage/weekly")
        assert resp.json()["recalls_this_week"] == 2

    def test_excludes_grace_day_sentinels_from_recall_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        (tmp_path / "usage.jsonl").write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 0, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"type": "grace_day_used", "ts": f"{today}T12:00:00+00:00"}) + "\n"
        )
        resp = client.get("/api/usage/weekly")
        assert resp.json()["recalls_this_week"] == 1

    def test_new_topics_excludes_older_subjects(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [
            _make_atom("coffee", ingested_days_ago=3),   # this week
            _make_atom("hiking", ingested_days_ago=10),  # older
        ]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/usage/weekly")
        body = resp.json()
        assert "coffee" in body["new_topics"]
        assert "hiking" not in body["new_topics"]

    def test_top_topic_is_most_frequent_this_week(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [
            _make_atom("coffee", ingested_days_ago=1),
            _make_atom("coffee", ingested_days_ago=2),
            _make_atom("hiking", ingested_days_ago=3),
        ]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/usage/weekly")
        assert resp.json()["top_topic"] == "coffee"

    def test_empty_returns_zeros(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/weekly")
        body = resp.json()
        assert body["atoms_this_week"] == 0
        assert body["recalls_this_week"] == 0
        assert body["new_topics"] == []
        assert body["top_topic"] is None

    def test_old_recalls_not_counted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        old = (_utc_today() - timedelta(days=10)).isoformat()
        (tmp_path / "usage.jsonl").write_text(
            json.dumps({"ts": f"{old}T10:00:00+00:00", "query_hash": "x", "selection_ms": 10, "synthesis_ms": 0, "atom_count": 1, "channel": "web"}) + "\n"
        )
        resp = client.get("/api/usage/weekly")
        assert resp.json()["recalls_this_week"] == 0


# ---------------------------------------------------------------------------
# GET /api/topic/depth
# ---------------------------------------------------------------------------

class TestApiTopicDepth:
    def test_returns_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [_make_atom("coffee"), _make_atom("coffee"), _make_atom("hiking")]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/topic/depth?subject=coffee")
        assert resp.json()["count"] == 2

    def test_case_insensitive_match(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [_make_atom("Coffee"), _make_atom("COFFEE")]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/topic/depth?subject=coffee")
        assert resp.json()["count"] == 2

    def test_excludes_superseded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [_make_atom("coffee"), _make_atom("coffee", is_superseded=True)]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/topic/depth?subject=coffee")
        assert resp.json()["count"] == 1

    def test_unknown_subject_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = []
            resp = client.get("/api/topic/depth?subject=unknown")
        assert resp.json()["count"] == 0

    def test_returns_subject_in_response(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = []
            resp = client.get("/api/topic/depth?subject=hiking")
        assert resp.json()["subject"] == "hiking"


# ---------------------------------------------------------------------------
# GET /api/atoms/recent — includes ingested_at
# ---------------------------------------------------------------------------

class TestAtomsRecentIngestedAt:
    def test_includes_ingested_at_field(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [_make_atom("coffee", ingested_days_ago=2)]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/atoms/recent")
        assert "ingested_at" in resp.json()[0]

    def test_ingested_at_is_iso_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        atoms = [_make_atom("coffee", ingested_days_ago=5)]
        with patch("lattice.web.app._get_db") as mock_db:
            mock_db.return_value.all.return_value = atoms
            resp = client.get("/api/atoms/recent")
        val = resp.json()[0]["ingested_at"]
        # Should parse as ISO datetime
        datetime.fromisoformat(val)


# ---------------------------------------------------------------------------
# _topic_depth_message
# ---------------------------------------------------------------------------

class TestTopicDepthMessage:
    # --- positive ---
    def test_threshold_5(self):
        msg = _topic_depth_message("coffee", 5)
        assert msg is not None
        assert "5" in msg
        assert "coffee" in msg
        assert "know well" in msg

    def test_threshold_10(self):
        msg = _topic_depth_message("hiking", 10)
        assert "thought about" in msg

    def test_threshold_20(self):
        msg = _topic_depth_message("lattice", 20)
        assert "know best" in msg

    def test_highest_threshold_wins(self):
        # 25 atoms → should hit 20 threshold
        msg = _topic_depth_message("books", 25)
        assert "know best" in msg

    # --- negative ---
    def test_below_threshold_returns_none(self):
        assert _topic_depth_message("coffee", 4) is None
        assert _topic_depth_message("hiking", 0) is None

    # --- edge ---
    def test_exactly_5_triggers(self):
        assert _topic_depth_message("x", 5) is not None

    def test_exactly_10_triggers(self):
        msg = _topic_depth_message("x", 10)
        assert "thought about" in msg

    def test_exactly_20_triggers(self):
        msg = _topic_depth_message("x", 20)
        assert "know best" in msg


# ---------------------------------------------------------------------------
# Telegram weekly summary
# ---------------------------------------------------------------------------

class TestTelegramWeeklySummary:
    def _make_update(self):
        update = MagicMock()
        update.message.text = "what do I prefer?"
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 42
        update.effective_chat.id = 123
        return update

    def _make_context(self):
        ctx = MagicMock()
        ctx.chat_data = {}
        ctx.bot_data = {}
        ctx.args = []
        return ctx

    def test_weekly_summary_sent_on_monday(self):
        from lattice.telegram_bot import _send_weekly_summary_if_due
        update = self._make_update()
        ctx = self._make_context()
        monday = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)  # a Monday
        with patch("lattice.telegram_bot._get_weekly_summary", return_value={
            "atoms_this_week": 10, "recalls_this_week": 5, "topics_this_week": 3,
            "new_topics": ["travel"], "top_topic": "coffee", "streak": 8
        }):
            with patch("datetime.datetime") as mock_dt:
                mock_dt.now.return_value = monday
                run(_send_weekly_summary_if_due(update, ctx))
        update.message.reply_text.assert_called_once()
        reply = update.message.reply_text.call_args[0][0]
        assert "10 things saved" in reply
        assert "coffee" in reply

    def test_no_summary_when_streak_less_than_7(self):
        from lattice.telegram_bot import _send_weekly_summary_if_due
        update = self._make_update()
        ctx = self._make_context()
        monday = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
        with patch("lattice.telegram_bot._get_weekly_summary", return_value={
            "atoms_this_week": 5, "recalls_this_week": 2, "topics_this_week": 1,
            "new_topics": [], "top_topic": None, "streak": 3
        }):
            with patch("datetime.datetime") as mock_dt:
                mock_dt.now.return_value = monday
                run(_send_weekly_summary_if_due(update, ctx))
        update.message.reply_text.assert_not_called()

    def test_no_summary_on_non_monday(self):
        from lattice.telegram_bot import _send_weekly_summary_if_due
        update = self._make_update()
        ctx = self._make_context()
        tuesday = datetime(2026, 6, 9, 10, 0, tzinfo=timezone.utc)  # Tuesday
        with patch("lattice.telegram_bot._get_weekly_summary") as mock_weekly:
            with patch("datetime.datetime") as mock_dt:
                mock_dt.now.return_value = tuesday
                run(_send_weekly_summary_if_due(update, ctx))
        mock_weekly.assert_not_called()
        update.message.reply_text.assert_not_called()

    def test_summary_not_sent_twice_same_week(self):
        from lattice.telegram_bot import _send_weekly_summary_if_due
        update = self._make_update()
        monday = datetime(2026, 6, 8, 10, 0, tzinfo=timezone.utc)
        iso_week = monday.isocalendar()
        week_key = f"weekly_report_{iso_week[0]}_{iso_week[1]}"
        ctx = self._make_context()
        ctx.bot_data[week_key] = True  # already sent this week
        with patch("lattice.telegram_bot._get_weekly_summary") as mock_weekly:
            with patch("datetime.datetime") as mock_dt:
                mock_dt.now.return_value = monday
                run(_send_weekly_summary_if_due(update, ctx))
        mock_weekly.assert_not_called()
