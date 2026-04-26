"""Tests for search_atoms — real pgvector DB, embed_text mocked."""

import pytest
from sqlalchemy import select

from backend.models.atoms import AtomSource
from backend.serving.l3_search import count_atoms_by_source, get_atoms_by_source, search_atoms
from tests.helpers import make_vector


async def test_search_atoms_returns_accessible_atom(db_session, mock_embed_text, make_atom):
    atom = await make_atom(content="Revenue grew 20% in Q2.", access_mask=0xFF)
    results = await search_atoms(db_session, "revenue", role_mask=0xFF)
    atom_ids = [r["atom_id"] for r in results]
    assert str(atom.id) in atom_ids


async def test_search_atoms_excludes_non_overlapping_mask(db_session, mock_embed_text, make_atom):
    # Atom has only finance bit (0b100); agent has only sales bit (0b010)
    await make_atom(content="Finance-only content here.", access_mask=0b100, domain=["finance"])
    results = await search_atoms(db_session, "finance", role_mask=0b010)
    assert results == []


async def test_search_atoms_excludes_wrong_domain(db_session, mock_embed_text, make_atom):
    await make_atom(content="Engineering architecture decision.", domain=["engineering"], access_mask=0xFF)
    results = await search_atoms(
        db_session, "architecture", role_mask=0xFF, domain_filter=["sales"]
    )
    assert results == []


async def test_search_atoms_includes_general_domain_in_filter(db_session, mock_embed_text, make_atom):
    await make_atom(content="General knowledge fact here.", domain=["general"], access_mask=0xFF)
    # Filter includes 'general' → atom should be returned
    results = await search_atoms(
        db_session, "knowledge", role_mask=0xFF, domain_filter=["sales", "general"]
    )
    assert any(r["domain"] == ["general"] for r in results)


async def test_search_atoms_min_relevance_filters_low_scores(db_session, mock_embed_text, make_atom):
    # Query and atom vector are both make_vector(0) → cosine distance=0 → relevance=1.0
    await make_atom(
        content="Highly relevant content match.",
        access_mask=0xFF,
        dense_vec=make_vector(0),
    )
    results = await search_atoms(db_session, "query", role_mask=0xFF, min_relevance=0.99)
    # relevance=1.0 passes threshold
    assert len(results) >= 1


async def test_search_atoms_min_relevance_excludes_all_when_threshold_too_high(
    db_session, mock_embed_text, make_atom
):
    await make_atom(
        content="Some content here.",
        access_mask=0xFF,
        dense_vec=make_vector(10),  # different from query vector make_vector(0)
    )
    # Patch to return a very different query vector
    from unittest.mock import patch
    with patch("backend.engine.embeddings.embed_text") as m:
        m.return_value = make_vector(100)  # far from make_vector(10)
        results = await search_atoms(db_session, "query", role_mask=0xFF, min_relevance=0.999)
    # With very different vectors, relevance will be well below 0.999
    assert results == []


async def test_search_atoms_result_has_required_fields(db_session, mock_embed_text, make_atom):
    await make_atom(access_mask=0xFF)
    results = await search_atoms(db_session, "query", role_mask=0xFF)
    assert len(results) >= 1
    r = results[0]
    for field in ["atom_id", "content", "kind", "domain", "access_mask", "relevance_score", "links"]:
        assert field in r, f"Missing field: {field}"


async def test_search_atoms_top_k_limits_results(db_session, mock_embed_text, make_atom):
    for i in range(5):
        await make_atom(content=f"Unique fact number {i} about revenue growth.", access_mask=0xFF)
    results = await search_atoms(db_session, "revenue", role_mask=0xFF, top_k=2)
    assert len(results) <= 2


async def test_search_atoms_no_atoms_returns_empty(db_session, mock_embed_text):
    results = await search_atoms(db_session, "query", role_mask=0xFF)
    assert results == []


async def test_search_atoms_relevance_score_between_zero_and_one(db_session, mock_embed_text, make_atom):
    await make_atom(access_mask=0xFF, dense_vec=make_vector(0))
    results = await search_atoms(db_session, "query", role_mask=0xFF)
    for r in results:
        assert 0.0 <= r["relevance_score"] <= 1.0


# ── count_atoms_by_source ─────────────────────────────────────────────────────


async def test_count_atoms_by_source_returns_zero_for_new_source(db_session, make_source):
    source = await make_source()
    count = await count_atoms_by_source(db_session, source.id)
    assert count == 0


async def test_count_atoms_by_source_counts_linked_atoms(db_session, make_source, make_atom):
    source = await make_source()
    atom1 = await make_atom(content="First atom content here.")
    atom2 = await make_atom(content="Second atom content here.")

    db_session.add(AtomSource(atom_id=atom1.id, source_id=source.id, is_primary=True))
    db_session.add(AtomSource(atom_id=atom2.id, source_id=source.id, is_primary=True))
    await db_session.flush()

    count = await count_atoms_by_source(db_session, source.id)
    assert count == 2


# ── get_atoms_by_source ───────────────────────────────────────────────────────


async def test_get_atoms_by_source_returns_linked_atoms(db_session, make_source, make_atom):
    source = await make_source()
    atom = await make_atom(content="Source atom content.")
    db_session.add(AtomSource(atom_id=atom.id, source_id=source.id, is_primary=True))
    await db_session.flush()

    atoms = await get_atoms_by_source(db_session, source.id)
    assert len(atoms) == 1
    assert atoms[0]["atom_id"] == str(atom.id)
    assert atoms[0]["content"] == "Source atom content."


async def test_get_atoms_by_source_respects_limit(db_session, make_source, make_atom):
    source = await make_source()
    for i in range(5):
        atom = await make_atom(content=f"Atom content number {i}.")
        db_session.add(AtomSource(atom_id=atom.id, source_id=source.id, is_primary=True))
    await db_session.flush()

    atoms = await get_atoms_by_source(db_session, source.id, limit=2)
    assert len(atoms) == 2


async def test_get_atoms_by_source_empty_source(db_session, make_source):
    source = await make_source()
    atoms = await get_atoms_by_source(db_session, source.id)
    assert atoms == []
