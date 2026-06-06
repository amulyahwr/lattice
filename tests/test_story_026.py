"""Tests for STORY-026 — Web UI session-end capture.

JS behaviour (button state, DOM updates) cannot be unit-tested from Python.
These tests verify the server-side contract the JS depends on:
  - POST /api/ingest accepts the conversation-chunk format the JS produces
  - source_id="web" is accepted
  - Multi-turn chunks are ingested correctly
  - Error responses have the right shape so JS can handle them
"""
from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from lattice.web.app import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Server-side contract for the Save session button
# ---------------------------------------------------------------------------

class TestSaveSessionEndpoint:
    # --- positive ---
    def test_single_qa_pair_accepted(self):
        chunk = "user: what is my coffee preference?\nassistant: You prefer dark coffee."
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": ["a1"], "atoms_new": 1, "atoms_updated": 0, "duplicates_skipped": 0}
            resp = client.post("/api/ingest", json={"text": chunk, "source_id": "web"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_multi_qa_pairs_accepted(self):
        chunk = (
            "user: what is my coffee preference?\nassistant: You prefer dark coffee.\n\n"
            "user: what gym do I go to?\nassistant: You go to Planet Fitness."
        )
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": ["a1", "a2"], "atoms_new": 2, "atoms_updated": 0, "duplicates_skipped": 0}
            resp = client.post("/api/ingest", json={"text": chunk, "source_id": "web"})
        assert resp.status_code == 200
        assert len(resp.json()["atom_ids"]) == 2

    def test_source_id_web_passed_to_daemon(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": [], "atoms_new": 0, "atoms_updated": 0, "duplicates_skipped": 0}
            client.post("/api/ingest", json={"text": "user: hi\nassistant: hello", "source_id": "web"})
            call_args = mock_cls.return_value.ingest_full.call_args
            assert "web" in str(call_args)

    def test_conversation_format_reaches_daemon(self):
        """JS formats as 'user: Q\\nassistant: A' — verify it reaches ingest unchanged."""
        chunk = "user: what is my preference?\nassistant: You prefer dark."
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": [], "atoms_new": 0, "atoms_updated": 0, "duplicates_skipped": 0}
            client.post("/api/ingest", json={"text": chunk, "source_id": "web"})
            call_args = mock_cls.return_value.ingest_full.call_args
            assert "user: what is my preference?" in str(call_args)
            assert "assistant: You prefer dark." in str(call_args)

    def test_observed_at_stamped(self):
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": [], "atoms_new": 0, "atoms_updated": 0, "duplicates_skipped": 0}
            client.post("/api/ingest", json={"text": "user: hi\nassistant: hello", "source_id": "web"})
            call_args = mock_cls.return_value.ingest_full.call_args
            assert "observed_at" in str(call_args)

    # --- negative ---
    def test_daemon_down_returns_503(self):
        """JS catches non-ok response and resets button — 503 must be returned."""
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.side_effect = OSError("no socket")
            resp = client.post("/api/ingest", json={"text": "user: hi\nassistant: hello", "source_id": "web"})
        assert resp.status_code == 503
        assert resp.json()["ok"] is False

    def test_missing_text_returns_422(self):
        resp = client.post("/api/ingest", json={"source_id": "web"})
        assert resp.status_code == 422

    # --- edge ---
    def test_empty_chunk_still_accepted(self):
        """JS guards against empty sessionQA, but server shouldn't crash if empty string sent."""
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": [], "atoms_new": 0, "atoms_updated": 0, "duplicates_skipped": 0}
            resp = client.post("/api/ingest", json={"text": "", "source_id": "web"})
        assert resp.status_code == 200

    def test_very_long_session_accepted(self):
        """Long sessions (many Q&A pairs) must not hit any payload limit."""
        pairs = [f"user: question {i}?\nassistant: answer {i}." for i in range(50)]
        chunk = "\n\n".join(pairs)
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest.return_value = [f"a{i}" for i in range(50)]
            resp = client.post("/api/ingest", json={"text": chunk, "source_id": "web"})
        assert resp.status_code == 200

    def test_response_has_atom_ids_list(self):
        """JS doesn't use atom_ids but the shape must be consistent."""
        with patch("lattice.web.app.DaemonClient") as mock_cls:
            mock_cls.return_value.ingest_full.return_value = {"atom_ids": ["a1", "a2"], "atoms_new": 2, "atoms_updated": 0, "duplicates_skipped": 0}
            resp = client.post("/api/ingest", json={"text": "user: hi\nassistant: hey", "source_id": "web"})
        body = resp.json()
        assert isinstance(body["atom_ids"], list)


# ---------------------------------------------------------------------------
# HTML presence — verify button exists in served page
# ---------------------------------------------------------------------------

class TestSaveSessionHtml:
    def test_save_session_button_in_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "save-session" in resp.text

    def test_save_session_button_disabled_by_default(self):
        resp = client.get("/")
        assert "disabled" in resp.text
