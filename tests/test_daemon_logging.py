"""Tests for S5: daemon JSON-lines logging and enhanced status subcommand."""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lattice.daemon import (
    _JsonFormatter,
    _count_atoms,
    _dispatch,
    _parse_last_ingest,
    status,
)


# ---------------------------------------------------------------------------
# _JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    def _make_record(self, msg: str, level=logging.INFO, extra: dict | None = None) -> logging.LogRecord:
        record = logging.LogRecord(
            name="lattice.daemon",
            level=level,
            pathname=__file__,
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        if extra:
            for k, v in extra.items():
                setattr(record, k, v)
        return record

    def test_emits_valid_json(self):
        fmt = _JsonFormatter()
        record = self._make_record("hello world")
        line = fmt.format(record)
        obj = json.loads(line)  # must not raise
        assert isinstance(obj, dict)

    def test_required_fields_present(self):
        fmt = _JsonFormatter()
        record = self._make_record("test message")
        obj = json.loads(fmt.format(record))
        assert "ts" in obj
        assert "level" in obj
        assert "msg" in obj
        assert obj["msg"] == "test message"
        assert obj["level"] == "INFO"

    def test_ts_is_iso_format(self):
        fmt = _JsonFormatter()
        record = self._make_record("ts test")
        obj = json.loads(fmt.format(record))
        # Should parse as ISO 8601 without raising
        from datetime import datetime
        datetime.fromisoformat(obj["ts"])

    def test_extra_fields_included(self):
        fmt = _JsonFormatter()
        record = self._make_record("with extra", extra={"event": "ingest_start", "source_id": "src-abc"})
        obj = json.loads(fmt.format(record))
        assert obj["event"] == "ingest_start"
        assert obj["source_id"] == "src-abc"

    def test_error_level(self):
        fmt = _JsonFormatter()
        record = self._make_record("something went wrong", level=logging.ERROR)
        obj = json.loads(fmt.format(record))
        assert obj["level"] == "ERROR"

    def test_exc_info_included(self):
        fmt = _JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="lattice.daemon",
            level=logging.ERROR,
            pathname=__file__,
            lineno=0,
            msg="error occurred",
            args=(),
            exc_info=exc_info,
        )
        obj = json.loads(fmt.format(record))
        assert "exc" in obj
        assert "ValueError" in obj["exc"]


# ---------------------------------------------------------------------------
# _dispatch ingest logging
# ---------------------------------------------------------------------------

class TestDispatchLogging:
    def test_ingest_logs_start_and_end(self, tmp_path, caplog):
        """_dispatch ingest op should log ingest_start and ingest_end events."""
        import lattice.daemon as daemon_mod

        mock_result = {"atoms_created": 1, "atom_ids": ["atom-001"], "duplicate_atom_ids": []}

        with patch("lattice.daemon._db", None):
            with patch("lattice.ingest.ingest", return_value=mock_result) as mock_ingest:
                with caplog.at_level(logging.INFO, logger="lattice.daemon"):
                    result = _dispatch({"op": "ingest", "text": "hello world", "source_id": "test-src"})

        assert result["ok"] is True
        assert "atom-001" in result["atom_ids"]

        # Find log records with event field
        events = [r for r in caplog.records if getattr(r, "event", None) in ("ingest_start", "ingest_end")]
        event_names = [r.event for r in events]
        assert "ingest_start" in event_names
        assert "ingest_end" in event_names

    def test_ingest_start_has_source_id_and_text_len(self, caplog):
        mock_result = {"atoms_created": 1, "atom_ids": ["atom-002"], "duplicate_atom_ids": []}

        with patch("lattice.daemon._db", None):
            with patch("lattice.ingest.ingest", return_value=mock_result):
                with caplog.at_level(logging.INFO, logger="lattice.daemon"):
                    _dispatch({"op": "ingest", "text": "hello world", "source_id": "my-source"})

        start_rec = next(r for r in caplog.records if getattr(r, "event", None) == "ingest_start")
        assert start_rec.source_id == "my-source"
        assert start_rec.text_len == len("hello world")

    def test_ingest_end_has_atom_count_and_duration(self, caplog):
        mock_result = {"atoms_created": 3, "atom_ids": [f"a-{i}" for i in range(3)], "duplicate_atom_ids": []}

        with patch("lattice.daemon._db", None):
            with patch("lattice.ingest.ingest", return_value=mock_result):
                with caplog.at_level(logging.INFO, logger="lattice.daemon"):
                    _dispatch({"op": "ingest", "text": "some text", "source_id": "s"})

        end_rec = next(r for r in caplog.records if getattr(r, "event", None) == "ingest_end")
        assert end_rec.atom_count == 3
        assert isinstance(end_rec.duration_ms, int)
        assert end_rec.duration_ms >= 0

    def test_ingest_logs_error_on_exception(self, caplog):
        with patch("lattice.daemon._db", None):
            with patch("lattice.ingest.ingest", side_effect=RuntimeError("fail")):
                with caplog.at_level(logging.ERROR, logger="lattice.daemon"):
                    with pytest.raises(RuntimeError):
                        _dispatch({"op": "ingest", "text": "text", "source_id": "s"})

        error_rec = next(r for r in caplog.records if getattr(r, "event", None) == "ingest_error")
        assert error_rec.levelno == logging.ERROR
        assert error_rec.source_id == "s"

    def test_dispatch_logs_written_to_file(self, tmp_path):
        """Integration: file handler receives JSON lines with event fields."""
        logger = logging.getLogger("lattice.daemon")
        original_level = logger.level
        logger.setLevel(logging.INFO)
        log_path = tmp_path / "daemon.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(_JsonFormatter())
        logger.addHandler(fh)

        mock_result = {"atoms_created": 1, "atom_ids": ["a-file"], "duplicate_atom_ids": []}

        try:
            with patch("lattice.daemon._db", None):
                with patch("lattice.ingest.ingest", return_value=mock_result):
                    _dispatch({"op": "ingest", "text": "abc", "source_id": "file-src"})
        finally:
            logger.removeHandler(fh)
            fh.close()
            logger.setLevel(original_level)

        lines = [l.strip() for l in log_path.read_text().splitlines() if l.strip()]
        objects = [json.loads(l) for l in lines]
        events = {o.get("event") for o in objects}
        assert "ingest_start" in events
        assert "ingest_end" in events


# ---------------------------------------------------------------------------
# _parse_last_ingest
# ---------------------------------------------------------------------------

class TestParseLastIngest:
    def test_returns_none_when_log_missing(self, tmp_path):
        result = _parse_last_ingest(tmp_path / "nonexistent.log")
        assert result is None

    def test_returns_none_when_no_ingest_end(self, tmp_path):
        log_path = tmp_path / "daemon.log"
        log_path.write_text(
            json.dumps({"ts": "2025-01-01T00:00:00+00:00", "level": "INFO", "msg": "started"}) + "\n"
        )
        assert _parse_last_ingest(log_path) is None

    def test_returns_last_ingest_end_ts(self, tmp_path):
        log_path = tmp_path / "daemon.log"
        entries = [
            {"ts": "2025-01-01T10:00:00+00:00", "level": "INFO", "msg": "ingest job end", "event": "ingest_end", "atom_count": 2},
            {"ts": "2025-01-01T11:00:00+00:00", "level": "INFO", "msg": "ingest job end", "event": "ingest_end", "atom_count": 5},
        ]
        log_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        result = _parse_last_ingest(log_path)
        assert result == "2025-01-01T11:00:00+00:00"

    def test_skips_malformed_lines(self, tmp_path):
        log_path = tmp_path / "daemon.log"
        log_path.write_text(
            "not valid json\n"
            + json.dumps({"ts": "2025-02-01T00:00:00+00:00", "event": "ingest_end"}) + "\n"
        )
        result = _parse_last_ingest(log_path)
        assert result == "2025-02-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# status() function
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_stopped_no_pid_file(self, tmp_path, capsys):
        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        out = capsys.readouterr().out
        obj = json.loads(out)
        assert obj["status"] == "stopped"
        assert obj["last_ingest"] is None
        assert obj["atom_count"] == 0

    def test_status_stopped_with_log_file(self, tmp_path, capsys):
        log_path = tmp_path / "daemon.log"
        log_path.write_text(
            json.dumps({
                "ts": "2025-06-01T09:00:00+00:00",
                "level": "INFO",
                "msg": "ingest job end",
                "event": "ingest_end",
                "atom_count": 7,
            }) + "\n"
        )
        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        obj = json.loads(capsys.readouterr().out)
        assert obj["status"] == "stopped"
        assert obj["last_ingest"] == "2025-06-01T09:00:00+00:00"

    def test_status_running_with_pid(self, tmp_path, capsys):
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text(str(os.getpid()))  # current process is running

        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        obj = json.loads(capsys.readouterr().out)
        assert obj["status"] == "running"
        assert obj["pid"] == os.getpid()
        assert "last_ingest" in obj
        assert "atom_count" in obj

    def test_status_stale_pid_shows_stopped(self, tmp_path, capsys):
        # PID that definitely doesn't exist
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("99999999")

        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        obj = json.loads(capsys.readouterr().out)
        assert obj["status"] == "stopped"

    def test_status_atom_count_reflects_db(self, tmp_path, capsys):
        # Write a couple of fake atom files
        from lattice.models import Atom
        from lattice.db import LatticeDB
        db = LatticeDB(tmp_path)
        atom1 = Atom(subject="test subject 1", content="content 1", kind="fact", source="document")
        atom2 = Atom(subject="test subject 2", content="content 2", kind="fact", source="document")
        db.write(atom1)
        db.write(atom2)

        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        obj = json.loads(capsys.readouterr().out)
        assert obj["atom_count"] == 2

    def test_status_superseded_atoms_not_counted(self, tmp_path, capsys):
        from lattice.models import Atom
        from lattice.db import LatticeDB
        db = LatticeDB(tmp_path)
        atom1 = Atom(subject="topic", content="old", kind="fact", source="document")
        atom2 = Atom(subject="topic", content="new", kind="fact", source="document")
        db.write(atom1)
        db.supersede(atom1.atom_id, atom2)

        with patch.dict(os.environ, {"LATTICE_DIR": str(tmp_path)}):
            status()
        obj = json.loads(capsys.readouterr().out)
        # atom1 is superseded, only atom2 counts
        assert obj["atom_count"] == 1


# ---------------------------------------------------------------------------
# _count_atoms
# ---------------------------------------------------------------------------

class TestCountAtoms:
    def test_returns_zero_for_missing_dir(self, tmp_path):
        missing = tmp_path / "nonexistent"
        assert _count_atoms(missing) == 0

    def test_counts_only_non_superseded(self, tmp_path):
        from lattice.models import Atom
        from lattice.db import LatticeDB
        db = LatticeDB(tmp_path)
        a = Atom(subject="s", content="c", kind="fact", source="document")
        db.write(a)
        a.is_superseded = True
        db.write(a)
        assert _count_atoms(tmp_path) == 0
