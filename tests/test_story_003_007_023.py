"""Tests for STORY-003 (POST /api/ingest), STORY-007 (lc CLI), STORY-023 (lc status)."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lattice.web.app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# STORY-003 — POST /api/ingest
# ---------------------------------------------------------------------------

class TestApiIngest:
    # --- positive ---
    def test_returns_ok_and_atom_ids(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = ["atom-1", "atom-2"]
            resp = client.post("/api/ingest", json={"text": "I prefer dark coffee"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["atom_ids"] == ["atom-1", "atom-2"]

    def test_default_source_id_is_http(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            client.post("/api/ingest", json={"text": "test"})
            call_args = mock_cls.return_value.ingest.call_args
            assert call_args[0][1] == "http" or call_args[1].get("source_id") == "http"

    def test_custom_source_id_passed_through(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            client.post("/api/ingest", json={"text": "test", "source_id": "vscode"})
            call_args = mock_cls.return_value.ingest.call_args
            assert "vscode" in str(call_args)

    def test_observed_at_stamped_in_metadata(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            client.post("/api/ingest", json={"text": "test"})
            call_args = mock_cls.return_value.ingest.call_args
            assert "observed_at" in str(call_args)

    def test_metadata_passthrough(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            client.post("/api/ingest", json={
                "text": "test",
                "metadata": {"title": "My Page", "url": "https://example.com"}
            })
            call_args = mock_cls.return_value.ingest.call_args
            assert "My Page" in str(call_args)

    def test_caller_observed_at_overwritten_by_server(self):
        """Caller-supplied observed_at must be replaced by server clock."""
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            client.post("/api/ingest", json={
                "text": "test",
                "metadata": {"observed_at": "2000-01-01T00:00:00+00:00"}
            })
            call_args = mock_cls.return_value.ingest.call_args
            metadata = call_args[1].get("metadata", {})
            assert metadata.get("observed_at") != "2000-01-01T00:00:00+00:00"

    def test_zero_atom_ids_returns_ok(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            resp = client.post("/api/ingest", json={"text": "test"})
        assert resp.status_code == 200
        assert resp.json()["atom_ids"] == []

    # --- negative / edge ---
    def test_daemon_down_returns_503(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.side_effect = OSError("no socket")
            resp = client.post("/api/ingest", json={"text": "test"})
        assert resp.status_code == 503
        body = resp.json()
        assert body["ok"] is False
        assert "daemon" in body["error"].lower()

    def test_runtime_error_returns_503(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.side_effect = RuntimeError("ingest failed")
            resp = client.post("/api/ingest", json={"text": "test"})
        assert resp.status_code == 503

    def test_missing_text_returns_422(self):
        resp = client.post("/api/ingest", json={"source_id": "test"})
        assert resp.status_code == 422

    def test_malformed_json_returns_422(self):
        resp = client.post("/api/ingest", content=b"not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 422

    def test_empty_text_still_accepted(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = []
            resp = client.post("/api/ingest", json={"text": ""})
        assert resp.status_code == 200

    def test_get_not_allowed(self):
        resp = client.get("/api/ingest")
        assert resp.status_code == 405

    def test_503_body_structure(self):
        """503 body must always have ok=False and error field."""
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.side_effect = OSError("gone")
            resp = client.post("/api/ingest", json={"text": "test"})
        body = resp.json()
        assert "ok" in body
        assert "error" in body


# ---------------------------------------------------------------------------
# STORY-007 + STORY-023 — lc CLI
# ---------------------------------------------------------------------------

class TestLcCli:
    # --- positive ---
    def test_capture_success(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "I prefer dark coffee"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.return_value = ["atom-1"]
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "Saved" in captured.out
        assert "1" in captured.out

    def test_capture_plural(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "test"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.return_value = ["a1", "a2"]
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "2" in captured.out
        assert "things" in captured.out

    def test_capture_singular_grammar(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "test"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.return_value = ["a1"]
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "thing" in captured.out
        assert "things" not in captured.out

    def test_capture_multiword_text_joined(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "decided", "to", "use", "postgres"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.return_value = ["a1"]
                cli_mod.lc()
        call_args = mock_cls.return_value.ingest.call_args
        assert call_args[0][0] == "decided to use postgres"

    def test_status_returns_count(self, tmp_path, capsys, monkeypatch):
        import lattice.cli as cli_mod
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch.object(sys, "argv", ["lc", "status"]):
            with patch("lattice.db.LatticeDB") as mock_db_cls:
                mock_atom = MagicMock()
                mock_atom.is_superseded = False
                mock_db_cls.return_value.all.return_value = [mock_atom, mock_atom]
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "2" in captured.out
        assert "memories" in captured.out

    def test_status_excludes_superseded(self, tmp_path, capsys, monkeypatch):
        import lattice.cli as cli_mod
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch.object(sys, "argv", ["lc", "status"]):
            with patch("lattice.db.LatticeDB") as mock_db_cls:
                live = MagicMock(); live.is_superseded = False
                dead = MagicMock(); dead.is_superseded = True
                mock_db_cls.return_value.all.return_value = [live, dead]
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "1" in captured.out

    def test_status_zero_memories(self, tmp_path, capsys, monkeypatch):
        import lattice.cli as cli_mod
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch.object(sys, "argv", ["lc", "status"]):
            with patch("lattice.db.LatticeDB") as mock_db_cls:
                mock_db_cls.return_value.all.return_value = []
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "0" in captured.out

    def test_status_does_not_require_daemon(self, tmp_path, monkeypatch):
        """lc status reads DB directly — daemon not needed."""
        import lattice.cli as cli_mod
        monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
        with patch.object(sys, "argv", ["lc", "status"]):
            with patch("lattice.db.LatticeDB") as mock_db_cls:
                mock_db_cls.return_value.all.return_value = []
                # DaemonClient must NOT be called
                with patch("lattice.client.DaemonClient") as daemon_mock:
                    cli_mod.lc()
                    daemon_mock.assert_not_called()

    # --- negative / edge ---
    def test_no_args_exits_1(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc"]):
            with pytest.raises(SystemExit) as exc:
                cli_mod.lc()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "Usage" in captured.err

    def test_no_args_shows_status_in_usage(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc"]):
            with pytest.raises(SystemExit):
                cli_mod.lc()
        captured = capsys.readouterr()
        assert "status" in captured.err

    def test_capture_daemon_down_exits_1(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "test"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.side_effect = OSError("no socket")
                with pytest.raises(SystemExit) as exc:
                    cli_mod.lc()
        assert exc.value.code == 1
        captured = capsys.readouterr()
        assert "daemon" in captured.err.lower()

    def test_capture_runtime_error_exits_1(self, capsys):
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "test"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.side_effect = RuntimeError("failed")
                with pytest.raises(SystemExit) as exc:
                    cli_mod.lc()
        assert exc.value.code == 1

    def test_capture_zero_atoms_still_succeeds(self, capsys):
        """0 atoms returned is not an error — dedup may have fired."""
        import lattice.cli as cli_mod
        with patch.object(sys, "argv", ["lc", "test"]):
            with patch("lattice.client.DaemonClient") as mock_cls:
                mock_cls.return_value.ingest.return_value = []
                cli_mod.lc()  # must not raise
        captured = capsys.readouterr()
        assert "0" in captured.out
