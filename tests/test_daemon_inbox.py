"""S2 acceptance tests: inbox folder watcher."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from lattice.config import Config
from lattice.daemon import InboxEventHandler, _start_inbox_watcher
from lattice.db import LatticeDB

_EXTRACTION = '{"atoms": [{"subject": "inbox file", "source": "document", "content": "test note about inbox files.", "kind": "fact", "valid_from": null, "valid_until": null}]}'
_SUPERSESSION = '{"superseded_atom_id": null}'


@pytest.fixture()
def tmp_db(tmp_path):
    return LatticeDB(tmp_path / "lattice")


@pytest.fixture()
def dirs(tmp_path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    processed.mkdir()
    return inbox, processed


def _make_handler(tmp_db, dirs):
    _, processed = dirs
    return InboxEventHandler(db=tmp_db, processed_dir=processed)


# ---------------------------------------------------------------------------
# Unit tests — handler logic without a live observer
# ---------------------------------------------------------------------------

class _FakeCreatedEvent:
    is_directory = False
    def __init__(self, path): self.src_path = str(path)

class _FakeMovedEvent:
    is_directory = False
    def __init__(self, dest): self.dest_path = str(dest)


def test_handler_ingests_md_file(tmp_db, dirs):
    inbox, processed = dirs
    f = inbox / "note.md"
    f.write_text("My test note about inbox files.")

    handler = _make_handler(tmp_db, dirs)
    with patch("lattice.ingest.complete", side_effect=[_EXTRACTION, _SUPERSESSION]):
        handler.on_created(_FakeCreatedEvent(f))

    atoms = [a for a in tmp_db.all() if not a.is_superseded]
    assert len(atoms) == 1
    assert not f.exists(), "file should be moved out of inbox"
    assert (processed / "note.md").exists(), "file should be in processed/"


def test_handler_ingests_txt_file(tmp_db, dirs):
    inbox, processed = dirs
    f = inbox / "note.txt"
    f.write_text("Plain text note.")

    handler = _make_handler(tmp_db, dirs)
    with patch("lattice.ingest.complete", side_effect=[_EXTRACTION, _SUPERSESSION]):
        handler.on_created(_FakeCreatedEvent(f))

    assert (processed / "note.txt").exists()
    assert not f.exists()


def test_handler_moves_binary_file_to_processed(tmp_db, dirs):
    """Binary files are attempted, rejected as binary, moved to processed (not left in inbox)."""
    inbox, processed = dirs
    f = inbox / "image.png"
    # Write clearly binary content (high ratio of non-UTF8 bytes)
    f.write_bytes(bytes(range(256)) * 10)

    handler = _make_handler(tmp_db, dirs)
    handler.on_created(_FakeCreatedEvent(f))

    # Binary file moves to processed (not stuck in inbox), no atoms created
    assert not f.exists() or (processed / "image.png").exists()
    assert tmp_db.all() == []


def test_handler_on_moved(tmp_db, dirs):
    inbox, processed = dirs
    f = inbox / "moved.md"
    f.write_text("Moved file content.")

    handler = _make_handler(tmp_db, dirs)
    with patch("lattice.ingest.complete", side_effect=[_EXTRACTION, _SUPERSESSION]):
        handler.on_moved(_FakeMovedEvent(f))

    assert (processed / "moved.md").exists()


def test_handler_ignores_directory_events(tmp_db, dirs):
    """Directory created events must not trigger ingest."""
    inbox, processed = dirs

    class _DirEvent:
        is_directory = True
        src_path = str(inbox / "subdir")

    handler = _make_handler(tmp_db, dirs)
    handler.on_created(_DirEvent())  # should not raise or ingest
    assert tmp_db.all() == []


# ---------------------------------------------------------------------------
# Integration test — live watchdog observer
# ---------------------------------------------------------------------------

def test_live_observer_ingests_dropped_file(tmp_path):
    lattice_dir = tmp_path / "lattice"
    lattice_dir.mkdir()
    db = LatticeDB(lattice_dir)

    import os
    inbox_dir = lattice_dir / "inbox"

    with patch.dict(os.environ, {"LATTICE_DIR": str(lattice_dir), "LATTICE_INBOX": str(inbox_dir)}):
        observer = _start_inbox_watcher(db, Config.from_env())

    try:
        f = inbox_dir / "live.md"
        with patch("lattice.ingest.complete", side_effect=[_EXTRACTION, _SUPERSESSION]):
            f.write_text("Live observer test.")
            deadline = time.time() + 5
            while time.time() < deadline:
                if not f.exists():
                    break
                time.sleep(0.1)

        assert not f.exists(), "file should have been moved within 5s"
        processed = lattice_dir / "processed" / "live.md"
        assert processed.exists()
    finally:
        observer.stop()
        observer.join(timeout=3)
