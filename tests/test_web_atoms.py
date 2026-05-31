"""Tests for S8: GET /api/atoms/recent endpoint."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lattice.models import Atom
from lattice.web.app import app

client = TestClient(app)

_BASE_DT = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_atom(
    atom_id: str,
    subject: str = "test subject",
    kind: str = "fact",
    observed_at: datetime | None = None,
    source_id: str | None = "src-1",
    is_superseded: bool = False,
) -> Atom:
    return Atom(
        atom_id=atom_id,
        kind=kind,
        source="test",
        subject=subject,
        content="content",
        observed_at=observed_at,
        source_id=source_id,
        is_superseded=is_superseded,
    )


def _patch_db(atoms: list[Atom]):
    """Context manager: patches LatticeDB in app.py so db.all() returns atoms."""
    mock_db = MagicMock()
    mock_db.all.return_value = atoms
    return patch("lattice.web.app.LatticeDB", return_value=mock_db)


# ── basic shape ──────────────────────────────────────────────────────────────

def test_recent_returns_200():
    with _patch_db([]):
        resp = client.get("/api/atoms/recent")
    assert resp.status_code == 200


def test_recent_returns_list():
    with _patch_db([]):
        resp = client.get("/api/atoms/recent")
    assert isinstance(resp.json(), list)


def test_each_item_has_required_keys():
    atom = _make_atom("a1", observed_at=_BASE_DT)
    with _patch_db([atom]):
        resp = client.get("/api/atoms/recent")
    data = resp.json()
    assert len(data) == 1
    item = data[0]
    for key in ("atom_id", "subject", "kind", "observed_at", "source_id"):
        assert key in item, f"missing key: {key}"


# ── filtering ─────────────────────────────────────────────────────────────────

def test_excludes_superseded_atoms():
    active = _make_atom("a1", is_superseded=False, observed_at=_BASE_DT)
    superseded = _make_atom("a2", is_superseded=True, observed_at=_BASE_DT)
    with _patch_db([active, superseded]):
        resp = client.get("/api/atoms/recent")
    ids = [item["atom_id"] for item in resp.json()]
    assert "a1" in ids
    assert "a2" not in ids


# ── limit ─────────────────────────────────────────────────────────────────────

def test_limit_query_param_respected():
    atoms = [
        _make_atom(f"a{i}", observed_at=_BASE_DT.replace(hour=i % 24))
        for i in range(5)
    ]
    with _patch_db(atoms):
        resp = client.get("/api/atoms/recent?limit=2")
    assert len(resp.json()) == 2


def test_default_limit_is_20():
    atoms = [
        _make_atom(f"a{i}", observed_at=_BASE_DT.replace(minute=i % 60))
        for i in range(25)
    ]
    with _patch_db(atoms):
        resp = client.get("/api/atoms/recent")
    assert len(resp.json()) == 20


# ── sorting ───────────────────────────────────────────────────────────────────

def test_sorted_by_observed_at_descending():
    t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 2, 10, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2024, 1, 3, 10, 0, 0, tzinfo=timezone.utc)
    atoms = [
        _make_atom("a_old", observed_at=t1),
        _make_atom("a_mid", observed_at=t2),
        _make_atom("a_new", observed_at=t3),
    ]
    with _patch_db(atoms):
        resp = client.get("/api/atoms/recent")
    ids = [item["atom_id"] for item in resp.json()]
    assert ids == ["a_new", "a_mid", "a_old"]


def test_none_observed_at_sorted_last():
    t1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    atoms = [
        _make_atom("a_none", observed_at=None),
        _make_atom("a_dated", observed_at=t1),
    ]
    with _patch_db(atoms):
        resp = client.get("/api/atoms/recent")
    ids = [item["atom_id"] for item in resp.json()]
    assert ids[0] == "a_dated"
    assert ids[-1] == "a_none"


# ── field values ──────────────────────────────────────────────────────────────

def test_observed_at_is_isoformat_string():
    dt = datetime(2024, 6, 15, 8, 30, 0, tzinfo=timezone.utc)
    atom = _make_atom("a1", observed_at=dt)
    with _patch_db([atom]):
        resp = client.get("/api/atoms/recent")
    item = resp.json()[0]
    assert item["observed_at"] == dt.isoformat()


def test_null_observed_at_returned_as_none():
    atom = _make_atom("a1", observed_at=None)
    with _patch_db([atom]):
        resp = client.get("/api/atoms/recent")
    item = resp.json()[0]
    assert item["observed_at"] is None


def test_source_id_returned():
    atom = _make_atom("a1", source_id="my-source", observed_at=_BASE_DT)
    with _patch_db([atom]):
        resp = client.get("/api/atoms/recent")
    assert resp.json()[0]["source_id"] == "my-source"
