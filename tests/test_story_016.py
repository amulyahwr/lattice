"""STORY-016: _db staleness — preload_if_stale() correctness and server integration."""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from lattice.db import LatticeDB
from lattice.models import Atom


def make_atom(subject="Alpha", content="Alpha does X.", **kwargs) -> Atom:
    return Atom(kind="fact", source="user", subject=subject, content=content, **kwargs)


# ---------------------------------------------------------------------------
# Unit tests: LatticeDB.preload_if_stale()
# ---------------------------------------------------------------------------

class TestPreloadIfStale:
    def test_hot_path_no_glob_when_manifest_matches(self, tmp_path):
        """When manifest atom_count == cache size, preload() must not be called."""
        db = LatticeDB(lattice_dir=tmp_path)
        atom = make_atom()
        db.write(atom)  # writes atom + saves manifest with atom_count=1

        assert len(db._atom_cache) == 1

        with patch.object(db, "preload") as mock_preload:
            db.preload_if_stale()
            mock_preload.assert_not_called()

    def test_cold_path_calls_preload_when_stale(self, tmp_path):
        """When manifest atom_count > cache size, preload() is called."""
        db = LatticeDB(lattice_dir=tmp_path)
        atom = make_atom()
        db.write(atom)

        # Simulate server startup with empty cache (clear it)
        db._atom_cache.clear()
        assert len(db._atom_cache) == 0
        # Manifest still says 1 atom — stale

        with patch.object(db, "preload") as mock_preload:
            db.preload_if_stale()
            mock_preload.assert_called_once()

    def test_no_manifest_calls_preload(self, tmp_path):
        """Missing manifest (empty lattice) → falls through to preload()."""
        db = LatticeDB(lattice_dir=tmp_path)
        # No writes → no manifest
        with patch.object(db, "preload") as mock_preload:
            db.preload_if_stale()
            mock_preload.assert_called_once()

    def test_new_atoms_become_visible_after_preload_if_stale(self, tmp_path):
        """End-to-end: second DB instance simulates daemon writes; first instance picks them up."""
        # Simulate server startup with empty lattice
        server_db = LatticeDB(lattice_dir=tmp_path)
        server_db.preload()
        assert len(server_db._atom_cache) == 0

        # Simulate daemon writing a new atom (separate DB instance)
        daemon_db = LatticeDB(lattice_dir=tmp_path)
        atom = make_atom(subject="Mountain retreat", content="Best retreat: mountains.")
        daemon_db.write(atom)

        # Before preload_if_stale: server_db doesn't see it
        assert atom.atom_id not in server_db._atom_cache

        # After preload_if_stale: server_db picks up the new atom
        server_db.preload_if_stale()
        assert atom.atom_id in server_db._atom_cache

    def test_hot_path_idempotent_multiple_calls(self, tmp_path):
        """Repeated preload_if_stale() calls with no new atoms don't mutate state."""
        db = LatticeDB(lattice_dir=tmp_path)
        atom = make_atom()
        db.write(atom)

        call_count = 0
        original_preload = db.preload

        def counting_preload():
            nonlocal call_count
            call_count += 1
            original_preload()

        db.preload = counting_preload  # type: ignore[method-assign]

        db.preload_if_stale()
        db.preload_if_stale()
        db.preload_if_stale()

        assert call_count == 0

    def test_corrupted_manifest_falls_through_to_preload(self, tmp_path):
        """Corrupted manifest JSON → preload() called, no crash."""
        db = LatticeDB(lattice_dir=tmp_path)
        atom = make_atom()
        db.write(atom)

        manifest_path = tmp_path / "graph" / "manifest.json"
        manifest_path.write_text("not valid json", encoding="utf-8")

        with patch.object(db, "preload") as mock_preload:
            db.preload_if_stale()
            mock_preload.assert_called_once()


# ---------------------------------------------------------------------------
# Server integration: lattice_select and lattice_answer call preload_if_stale
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def patched_server(tmp_path, monkeypatch):
    monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
    with patch("lattice.db.LatticeDB") as mock_db_cls:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        sys.modules.pop("server", None)
        import server as srv
        yield srv, mock_db


class TestServerCallsPreloadIfStale:
    def test_lattice_select_calls_preload_if_stale(self, patched_server):
        srv, mock_db = patched_server
        fake_atoms = [{"id": "a1", "content": "hello"}]

        with patch("server.select", return_value=fake_atoms):
            _run(srv.call_tool("lattice_select", {"query": "mountains"}))

        mock_db.preload_if_stale.assert_called_once()

    def test_lattice_answer_calls_preload_if_stale(self, patched_server):
        srv, mock_db = patched_server
        fake_atoms = [{"id": "a1", "content": "fact"}]
        fake_synthesis = MagicMock()
        fake_synthesis.answer = "Mountains are great."

        with patch("server.select", return_value=fake_atoms), \
             patch("server.synthesize", return_value=fake_synthesis):
            _run(srv.call_tool("lattice_answer", {"query": "best retreat?"}))

        mock_db.preload_if_stale.assert_called_once()

    def test_lattice_ingest_does_not_call_preload_if_stale(self, patched_server):
        """Ingest doesn't need staleness check — it delegates to daemon."""
        srv, mock_db = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["id1"]

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_ingest", {"source": "text"}))

        mock_db.preload_if_stale.assert_not_called()
