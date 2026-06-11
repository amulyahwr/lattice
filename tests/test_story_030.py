"""Tests for STORY-030 — Memory Depth: grace day, streak reframe, milestones."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lattice.web.app import app
from lattice.telemetry import compute_streak

_compute_streak_with_grace = compute_streak


def _utc_today():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).date()
from lattice.telegram_bot import _get_streak_info

client = TestClient(app)


def run(coro):
    return asyncio.run(coro)


def _iso(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _record(days_ago: int, rtype: str | None = None) -> dict:
    d = (_utc_today() - timedelta(days=days_ago)).isoformat()
    r: dict = {"ts": f"{d}T12:00:00+00:00"}
    if rtype:
        r["type"] = rtype
    else:
        r["query_hash"] = "abc"
        r["selection_ms"] = 10
        r["synthesis_ms"] = 100
        r["atom_count"] = 1
        r["channel"] = "web"
    return r


# ---------------------------------------------------------------------------
# _compute_streak_with_grace
# ---------------------------------------------------------------------------

class TestComputeStreakWithGrace:
    # --- positive ---
    def test_normal_streak_today(self):
        records = [_record(0), _record(1), _record(2)]
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 3
        assert grace is False

    def test_grace_day_active_when_missed_today(self):
        records = [_record(1), _record(2)]  # queried yesterday and before, not today
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 2
        assert grace is True

    def test_no_grace_when_two_days_missed(self):
        records = [_record(2), _record(3)]  # missed today AND yesterday
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 0
        assert grace is False

    def test_grace_not_granted_if_already_used_this_week(self):
        records = [
            _record(1),  # queried yesterday
            _record(0, rtype="grace_day_used"),  # grace already consumed today (shouldn't happen but defensive)
        ]
        # Grace used in last 7 days → no grace
        grace_used = _record(3, rtype="grace_day_used")
        records_with_grace_used = [_record(1), grace_used]
        streak, grace = _compute_streak_with_grace(records_with_grace_used)
        assert grace is False

    def test_streak_zero_no_records(self):
        streak, grace = _compute_streak_with_grace([])
        assert streak == 0
        assert grace is False

    def test_streak_1_queried_only_today(self):
        records = [_record(0)]
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 1
        assert grace is False

    # --- edge ---
    def test_grace_sentinel_excluded_from_query_days(self):
        # A grace_day_used record should not count as a query day
        records = [_record(0, rtype="grace_day_used")]
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 0

    def test_malformed_ts_skipped(self):
        records = [_record(0), {"ts": "not-a-date", "query_hash": "x"}]
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 1

    def test_long_streak_no_grace(self):
        records = [_record(i) for i in range(10)]  # 10 consecutive days including today
        streak, grace = _compute_streak_with_grace(records)
        assert streak == 10
        assert grace is False


# ---------------------------------------------------------------------------
# /api/usage/summary — new fields
# ---------------------------------------------------------------------------

class TestUsageSummaryNewFields:
    def test_returns_grace_day_active(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/summary")
        assert "grace_day_active" in resp.json()

    def test_returns_atom_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/summary")
        assert "atom_count" in resp.json()

    def test_grace_day_active_false_when_queried_today(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        (tmp_path / "usage.jsonl").write_text(
            json.dumps(_record(0)) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["grace_day_active"] is False

    def test_grace_day_active_true_when_missed_today(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        (tmp_path / "usage.jsonl").write_text(
            json.dumps(_record(1)) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["grace_day_active"] is True

    def test_grace_sentinels_excluded_from_today_count(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        (tmp_path / "usage.jsonl").write_text(
            json.dumps({"type": "grace_day_used", "ts": f"{today}T10:00:00+00:00"}) + "\n" +
            json.dumps(_record(0)) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["today"] == 1  # grace sentinel not counted


# ---------------------------------------------------------------------------
# Telegram /status — streak in reply
# ---------------------------------------------------------------------------

class TestTelegramStatus:
    def _make_update(self):
        update = MagicMock()
        update.message.reply_text = AsyncMock()
        update.effective_user.id = 42
        return update

    def _make_context(self):
        ctx = MagicMock()
        ctx.bot_data = {}
        ctx.chat_data = {}
        return ctx

    def test_status_includes_days_deep(self):
        from lattice.telegram_bot import _handle_status
        update = self._make_update()
        ctx = self._make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with patch("lattice.db.LatticeDB") as MockDB:
                with patch("lattice.config.Config") as MockCfg:
                    MockCfg.from_env.return_value.lattice_dir = "/fake"
                    MockDB.return_value.all.return_value = []
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.read.return_value = json.dumps({
                            "streak": 5, "grace_day_active": False, "atom_count": 10
                        }).encode()
                        mock_resp.__enter__ = lambda s: s
                        mock_resp.__exit__ = MagicMock(return_value=False)
                        mock_open.return_value = mock_resp
                        run(_handle_status(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "5 days deep" in reply

    def test_status_shows_rest_day_on_grace(self):
        from lattice.telegram_bot import _handle_status
        update = self._make_update()
        ctx = self._make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with patch("lattice.db.LatticeDB") as MockDB:
                with patch("lattice.config.Config") as MockCfg:
                    MockCfg.from_env.return_value.lattice_dir = "/fake"
                    MockDB.return_value.all.return_value = []
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.read.return_value = json.dumps({
                            "streak": 3, "grace_day_active": True, "atom_count": 5
                        }).encode()
                        mock_resp.__enter__ = lambda s: s
                        mock_resp.__exit__ = MagicMock(return_value=False)
                        mock_open.return_value = mock_resp
                        run(_handle_status(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "rest day" in reply

    def test_status_no_streak_no_deep_label(self):
        from lattice.telegram_bot import _handle_status
        update = self._make_update()
        ctx = self._make_context()
        with patch("lattice.telegram_bot._is_allowed", return_value=True):
            with patch("lattice.db.LatticeDB") as MockDB:
                with patch("lattice.config.Config") as MockCfg:
                    MockCfg.from_env.return_value.lattice_dir = "/fake"
                    MockDB.return_value.all.return_value = []
                    with patch("urllib.request.urlopen") as mock_open:
                        mock_resp = MagicMock()
                        mock_resp.read.return_value = json.dumps({
                            "streak": 0, "grace_day_active": False, "atom_count": 3
                        }).encode()
                        mock_resp.__enter__ = lambda s: s
                        mock_resp.__exit__ = MagicMock(return_value=False)
                        mock_open.return_value = mock_resp
                        run(_handle_status(update, ctx))
        reply = update.message.reply_text.call_args[0][0]
        assert "days deep" not in reply
