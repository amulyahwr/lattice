"""S4 acceptance tests: server.py lattice_ingest delegates to DaemonClient."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We need to import the call_tool handler from server.py.
# server.py calls LatticeDB() and preload() at import time, so we must patch those.


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def patched_server(tmp_path, monkeypatch):
    """Import server with DB + env patched so module-level init is harmless."""
    monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
    # Patch LatticeDB to avoid actual DB init
    with patch("lattice.db.LatticeDB") as mock_db_cls:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        # Force fresh import each time by removing from sys.modules
        import sys
        sys.modules.pop("server", None)
        import server as srv
        yield srv, tmp_path


# ---------------------------------------------------------------------------
# Test 1: daemon running — atom IDs returned
# ---------------------------------------------------------------------------

def test_ingest_with_daemon_running(patched_server):
    srv, tmp_path = patched_server
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.ingest.return_value = ["id1", "id2"]

    with patch("server.DaemonClient", return_value=mock_client):
        result = _run(srv.call_tool("lattice_ingest", {"source": "some text"}))

    assert len(result) == 1
    body = json.loads(result[0].text)
    assert body["atom_ids"] == ["id1", "id2"]
    mock_client.ingest.assert_called_once_with("some text", source_id="mcp")


def test_ingest_passes_source_id_from_metadata(patched_server):
    srv, tmp_path = patched_server
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.ingest.return_value = ["id1"]

    with patch("server.DaemonClient", return_value=mock_client):
        result = _run(srv.call_tool(
            "lattice_ingest",
            {"source": "text", "metadata": {"source_id": "my-src"}}
        ))

    mock_client.ingest.assert_called_once_with("text", source_id="my-src")
    body = json.loads(result[0].text)
    assert body["atom_ids"] == ["id1"]


# ---------------------------------------------------------------------------
# Test 2: daemon not running — inbox drop
# ---------------------------------------------------------------------------

def test_ingest_inbox_drop_when_daemon_down(patched_server):
    srv, tmp_path = patched_server
    mock_client = MagicMock()
    mock_client.ping.return_value = False

    with patch("server.DaemonClient", return_value=mock_client):
        result = _run(srv.call_tool("lattice_ingest", {"source": "queued content"}))

    assert len(result) == 1
    assert "queued" in result[0].text

    # A file must have been written to inbox/
    inbox_dir = tmp_path / "inbox"
    assert inbox_dir.exists(), "inbox/ dir should be created"
    files = list(inbox_dir.glob("*.md"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == "queued content"


def test_ingest_inbox_files_have_unique_names(patched_server):
    srv, tmp_path = patched_server
    mock_client = MagicMock()
    mock_client.ping.return_value = False

    with patch("server.DaemonClient", return_value=mock_client):
        _run(srv.call_tool("lattice_ingest", {"source": "first"}))
        _run(srv.call_tool("lattice_ingest", {"source": "second"}))

    inbox_dir = tmp_path / "inbox"
    files = list(inbox_dir.glob("*.md"))
    assert len(files) == 2, "Two separate inbox files should exist"
    names = {f.name for f in files}
    assert len(names) == 2, "Filenames must be unique"


# ---------------------------------------------------------------------------
# Test 3: lattice_query / lattice_select / lattice_answer still work
# ---------------------------------------------------------------------------

def test_lattice_select_still_works(patched_server):
    srv, tmp_path = patched_server
    fake_atoms = [{"id": "a1", "content": "hello"}]

    with patch("server.select", return_value=fake_atoms) as mock_sel:
        result = _run(srv.call_tool("lattice_select", {"query": "anything"}))

    assert len(result) == 1
    assert json.loads(result[0].text) == fake_atoms


def test_lattice_answer_still_works(patched_server):
    srv, tmp_path = patched_server
    fake_atoms = [{"id": "a1", "content": "fact"}]
    fake_synthesis = MagicMock()
    fake_synthesis.answer = "The answer is 42."

    with patch("server.select", return_value=fake_atoms), \
         patch("server.synthesize", return_value=fake_synthesis):
        result = _run(srv.call_tool("lattice_answer", {"query": "what?"}))

    assert result[0].text == "The answer is 42."
