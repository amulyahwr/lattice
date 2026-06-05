"""Tests for STORY-013 — local usage telemetry + streak."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from starlette.testclient import TestClient

from lattice.web.app import app, _compute_streak, _load_usage, _record_usage, _utc_today

client = TestClient(app)


# ---------------------------------------------------------------------------
# _record_usage — writes to usage.jsonl
# ---------------------------------------------------------------------------

class TestRecordUsage:
    # --- positive ---
    def test_creates_usage_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("what is my name?", 50, 300, 2, "web")
        assert (tmp_path / "usage.jsonl").exists()

    def test_record_has_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("what is my name?", 50, 300, 2, "web")
        record = json.loads((tmp_path / "usage.jsonl").read_text())
        assert "ts" in record
        assert "query_hash" in record
        assert "selection_ms" in record
        assert "synthesis_ms" in record
        assert "atom_count" in record
        assert "channel" in record

    def test_query_hash_is_sha1_not_plaintext(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("what is my name?", 50, 300, 2, "web")
        record = json.loads((tmp_path / "usage.jsonl").read_text())
        assert record["query_hash"] != "what is my name?"
        assert len(record["query_hash"]) == 40  # SHA-1 hex

    def test_channel_recorded_correctly(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("test", 10, 100, 1, "telegram")
        record = json.loads((tmp_path / "usage.jsonl").read_text())
        assert record["channel"] == "telegram"

    def test_multiple_records_appended(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("q1", 10, 100, 1, "web")
        _record_usage("q2", 20, 200, 2, "mcp")
        lines = (tmp_path / "usage.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    def test_same_question_different_hash_preserved(self, tmp_path, monkeypatch):
        """Two queries with same text still both recorded."""
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("same question", 10, 100, 1, "web")
        _record_usage("same question", 15, 150, 1, "telegram")
        lines = (tmp_path / "usage.jsonl").read_text().strip().split("\n")
        assert len(lines) == 2

    # --- edge ---
    def test_empty_question_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("", 0, 0, 0, "web")
        assert (tmp_path / "usage.jsonl").exists()

    def test_zero_latency_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        _record_usage("test", 0, 0, 0, "web")
        record = json.loads((tmp_path / "usage.jsonl").read_text())
        assert record["selection_ms"] == 0
        assert record["synthesis_ms"] == 0


# ---------------------------------------------------------------------------
# _compute_streak — streak calculation logic
# ---------------------------------------------------------------------------

class TestComputeStreak:
    def _record(self, day_offset: int) -> dict:
        d = (_utc_today() + timedelta(days=day_offset)).isoformat()
        return {"ts": f"{d}T12:00:00+00:00"}

    # --- positive ---
    def test_streak_1_today_only(self):
        records = [self._record(0)]
        assert _compute_streak(records) == 1

    def test_streak_3_consecutive_days(self):
        records = [self._record(0), self._record(-1), self._record(-2)]
        assert _compute_streak(records) == 3

    def test_streak_counts_regardless_of_channel(self):
        records = [
            {**self._record(0), "channel": "web"},
            {**self._record(-1), "channel": "telegram"},
            {**self._record(-2), "channel": "mcp"},
        ]
        assert _compute_streak(records) == 3

    def test_multiple_queries_same_day_count_as_one(self):
        records = [self._record(0), self._record(0), self._record(0)]
        assert _compute_streak(records) == 1

    # --- negative ---
    def test_streak_0_no_query_today_or_yesterday(self):
        # Missed both today AND yesterday — no grace day eligible → streak 0
        records = [self._record(-2), self._record(-3)]
        assert _compute_streak(records) == 0

    def test_streak_0_empty_records(self):
        assert _compute_streak([]) == 0

    def test_streak_breaks_on_gap(self):
        # today + 3 days ago but NOT 2 days ago = gap → streak = 1
        records = [self._record(0), self._record(-3)]
        assert _compute_streak(records) == 1

    # --- edge ---
    def test_streak_ignores_malformed_ts(self):
        records = [self._record(0), {"ts": "not-a-date"}]
        assert _compute_streak(records) == 1

    def test_streak_ignores_missing_ts(self):
        records = [self._record(0), {"channel": "web"}]
        assert _compute_streak(records) == 1

    def test_future_dates_do_not_extend_streak(self):
        records = [self._record(0), self._record(1)]  # tomorrow doesn't count back
        assert _compute_streak(records) == 1


# ---------------------------------------------------------------------------
# GET /api/usage/summary
# ---------------------------------------------------------------------------

class TestUsageSummary:
    # --- positive ---
    def test_returns_required_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert "today" in body
        assert "last_7_days" in body
        assert "avg_latency_ms" in body
        assert "streak" in body

    def test_empty_usage_returns_zeros(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        resp = client.get("/api/usage/summary")
        body = resp.json()
        assert body["today"] == 0
        assert body["last_7_days"] == 0
        assert body["streak"] == 0

    def test_counts_todays_queries(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        path = tmp_path / "usage.jsonl"
        path.write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"ts": f"{today}T11:00:00+00:00", "query_hash": "b", "selection_ms": 20, "synthesis_ms": 200, "atom_count": 2, "channel": "telegram"}) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["today"] == 2

    def test_streak_reflects_consecutive_days(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        yesterday = (_utc_today() - timedelta(days=1)).isoformat()
        path = tmp_path / "usage.jsonl"
        path.write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"ts": f"{yesterday}T10:00:00+00:00", "query_hash": "b", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["streak"] == 2

    def test_avg_latency_calculated(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        path = tmp_path / "usage.jsonl"
        path.write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 100, "synthesis_ms": 200, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"ts": f"{today}T11:00:00+00:00", "query_hash": "b", "selection_ms": 200, "synthesis_ms": 300, "atom_count": 1, "channel": "web"}) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["avg_latency_ms"] == 400  # (300+500)/2

    # --- edge ---
    def test_last_7_days_excludes_older(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        today = _utc_today().isoformat()
        old = (_utc_today() - timedelta(days=10)).isoformat()
        path = tmp_path / "usage.jsonl"
        path.write_text(
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n" +
            json.dumps({"ts": f"{old}T10:00:00+00:00", "query_hash": "b", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n"
        )
        resp = client.get("/api/usage/summary")
        body = resp.json()
        assert body["last_7_days"] == 1
        assert body["today"] == 1

    def test_malformed_lines_in_jsonl_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        path = tmp_path / "usage.jsonl"
        today = _utc_today().isoformat()
        path.write_text(
            "not json\n" +
            json.dumps({"ts": f"{today}T10:00:00+00:00", "query_hash": "a", "selection_ms": 10, "synthesis_ms": 100, "atom_count": 1, "channel": "web"}) + "\n"
        )
        resp = client.get("/api/usage/summary")
        assert resp.json()["today"] == 1


# ---------------------------------------------------------------------------
# Usage recorded from api_query and api_answer
# ---------------------------------------------------------------------------

class TestUsageRecordedFromEndpoints:
    def test_api_query_records_usage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[{"content": "test"}]):
            with patch("lattice.web.app.stream_synthesis") as mock_stream:
                mock_stream.return_value = iter([
                    f'data: {json.dumps({"type": "citations_applied", "answer": "answer"})}\n\n',
                    'data: {"type": "done"}\n\n',
                ])
                resp = client.post("/api/query", json={"question": "test?"})
                # consume the stream
                list(resp.iter_lines())
        assert (tmp_path / "usage.jsonl").exists()

    def test_api_answer_records_usage(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[{"content": "test"}]):
            with patch("lattice.web.app.synthesize") as mock_synth:
                mock_synth.return_value = MagicMock(answer="You prefer dark coffee.")
                client.post("/api/answer", json={"question": "what do I prefer?"})
        record = json.loads((tmp_path / "usage.jsonl").read_text())
        assert record["channel"] == "telegram"

    def test_api_answer_no_atoms_does_not_record(self, tmp_path, monkeypatch):
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch("lattice.web.app.select", return_value=[]):
            client.post("/api/answer", json={"question": "what?"})
        assert not (tmp_path / "usage.jsonl").exists()
