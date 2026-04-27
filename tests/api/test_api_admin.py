"""HTTP-level tests for admin endpoints — /admin/relink, /admin/stats, /admin/activity."""

import json
import uuid

import pytest

from backend.models.atoms import AtomSource
from tests.helpers import make_vector


# ── /admin/relink ─────────────────────────────────────────────────────────────


async def test_admin_relink_empty_db_returns_zero_counts(http_client):
    """Relink on an empty database should succeed and report nothing processed."""
    resp = await http_client.post("/api/v1/admin/relink")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sources_processed"] == 0
    assert data["cross_links_added"] == 0


async def test_admin_relink_single_source_no_candidates(
    http_client, db_session, make_source, make_atom
):
    """A single source has no other-source atoms to link against."""
    source = await make_source("solo.txt")
    atom = await make_atom(content="Solo atom content here.", domain=["engineering"])
    db_session.add(AtomSource(atom_id=atom.id, source_id=source.id, is_primary=True))
    await db_session.flush()

    resp = await http_client.post("/api/v1/admin/relink")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sources_processed"] == 1
    assert data["cross_links_added"] == 0


async def test_admin_relink_adds_cross_links_between_related_domains(
    http_client, db_session, mock_chat, make_source, make_atom
):
    """Finance and sales atoms are linked because their domains overlap via DOMAIN_GROUPS."""
    source1 = await make_source("finance.txt")
    source2 = await make_source("sales.txt")

    # Both atoms share the same vector → cosine similarity = 1.0 → above threshold
    atom1 = await make_atom(
        content="Revenue grew 20% in Q2.",
        domain=["finance"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )
    atom2 = await make_atom(
        content="Sales pipeline hit record numbers in Q2.",
        domain=["sales"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )

    db_session.add(AtomSource(atom_id=atom1.id, source_id=source1.id, is_primary=True))
    db_session.add(AtomSource(atom_id=atom2.id, source_id=source2.id, is_primary=True))
    await db_session.flush()

    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"}
    ])

    resp = await http_client.post("/api/v1/admin/relink")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sources_processed"] == 2
    assert data["cross_links_added"] >= 1


async def test_admin_relink_skips_unrelated_domains(
    http_client, db_session, mock_chat, make_source, make_atom
):
    """Engineering and HR atoms are not linked — no domain group connects them."""
    source1 = await make_source("engineering.txt")
    source2 = await make_source("hr.txt")

    atom1 = await make_atom(
        content="Deploy Kubernetes cluster in us-east-1.",
        domain=["engineering"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )
    atom2 = await make_atom(
        content="New hire onboarding checklist and policy.",
        domain=["hr"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )

    db_session.add(AtomSource(atom_id=atom1.id, source_id=source1.id, is_primary=True))
    db_session.add(AtomSource(atom_id=atom2.id, source_id=source2.id, is_primary=True))
    await db_session.flush()

    # mock_chat should NOT be called since no candidates pass domain filter
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"}
    ])

    resp = await http_client.post("/api/v1/admin/relink")
    assert resp.status_code == 200
    data = resp.json()
    assert data["cross_links_added"] == 0


async def test_admin_relink_does_not_duplicate_existing_links(
    http_client, db_session, mock_chat, make_source, make_atom
):
    """Running relink twice does not create duplicate links on atoms."""
    source1 = await make_source("finance2.txt")
    source2 = await make_source("sales2.txt")

    atom1 = await make_atom(
        content="Revenue grew 20% in Q2.",
        domain=["finance"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )
    atom2 = await make_atom(
        content="Sales pipeline record Q2.",
        domain=["sales"],
        dense_vec=make_vector(0),
        access_mask=0xFF,
    )

    db_session.add(AtomSource(atom_id=atom1.id, source_id=source1.id, is_primary=True))
    db_session.add(AtomSource(atom_id=atom2.id, source_id=source2.id, is_primary=True))
    await db_session.flush()

    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"}
    ])

    resp1 = await http_client.post("/api/v1/admin/relink")
    first_run = resp1.json()["cross_links_added"]

    # Second run — links already exist, should add nothing new
    resp2 = await http_client.post("/api/v1/admin/relink")
    assert resp2.status_code == 200
    assert resp2.json()["cross_links_added"] == 0


# ── /admin/stats ──────────────────────────────────────────────────────────────


async def test_admin_stats_returns_expected_fields(http_client):
    resp = await http_client.get("/api/v1/admin/stats")
    assert resp.status_code == 200
    data = resp.json()
    for field in ["total_atoms", "total_agents", "total_sources", "atoms_by_kind", "total_queries"]:
        assert field in data, f"Missing field: {field}"


async def test_admin_stats_counts_are_non_negative(http_client):
    resp = await http_client.get("/api/v1/admin/stats")
    data = resp.json()
    assert data["total_atoms"] >= 0
    assert data["total_agents"] >= 0
    assert data["total_sources"] >= 0
    assert data["total_queries"] >= 0


# ── /admin/activity ───────────────────────────────────────────────────────────


async def test_admin_activity_returns_events_list(http_client):
    resp = await http_client.get("/api/v1/admin/activity")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert "total" in data
    assert isinstance(data["events"], list)


async def test_admin_activity_respects_limit(http_client):
    resp = await http_client.get("/api/v1/admin/activity?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()["events"]) <= 5
