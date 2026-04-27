"""Tests for search_atoms — real pgvector DB, embed_text mocked."""

import pytest
from sqlalchemy import select

from backend.models.atoms import AtomSource
from backend.serving.l3_search import count_atoms_by_source, get_atoms_by_source, search_atoms
from tests.helpers import make_vector


# ── Basic access control and domain filtering ─────────────────────────────────


async def test_search_atoms_returns_accessible_atom(db_session, mock_embed_text, make_atom):
    atom = await make_atom(content="Revenue grew 20% in Q2.", access_mask=0xFF)
    results = await search_atoms(db_session, ["revenue"], role_mask=0xFF)
    assert str(atom.id) in [r["atom_id"] for r in results]


async def test_search_atoms_excludes_non_overlapping_mask(db_session, mock_embed_text, make_atom):
    await make_atom(content="Finance-only content here.", access_mask=0b100, domain=["finance"])
    results = await search_atoms(db_session, ["finance"], role_mask=0b010)
    assert results == []


async def test_search_atoms_excludes_wrong_domain(db_session, mock_embed_text, make_atom):
    await make_atom(content="Engineering architecture decision.", domain=["engineering"], access_mask=0xFF)
    results = await search_atoms(db_session, ["architecture"], role_mask=0xFF, domain_filter=["sales"])
    assert results == []


async def test_search_atoms_includes_general_domain_in_filter(db_session, mock_embed_text, make_atom):
    await make_atom(content="General knowledge fact here.", domain=["general"], access_mask=0xFF)
    results = await search_atoms(
        db_session, ["knowledge"], role_mask=0xFF, domain_filter=["sales", "general"]
    )
    assert any(r["domain"] == ["general"] for r in results)


async def test_search_atoms_min_relevance_filters_low_scores(db_session, mock_embed_text, make_atom):
    await make_atom(content="Highly relevant content match.", access_mask=0xFF, dense_vec=make_vector(0))
    results = await search_atoms(db_session, ["query"], role_mask=0xFF, min_relevance=0.99)
    assert len(results) >= 1


async def test_search_atoms_min_relevance_excludes_all_when_threshold_too_high(
    db_session, mock_embed_text, make_atom
):
    await make_atom(content="Some content here.", access_mask=0xFF, dense_vec=make_vector(10))
    from unittest.mock import patch
    with patch("backend.serving.l3_search.embed_text") as m:
        m.return_value = make_vector(100)
        results = await search_atoms(db_session, ["query"], role_mask=0xFF, min_relevance=0.999)
    assert results == []


async def test_search_atoms_result_has_required_fields(db_session, mock_embed_text, make_atom):
    await make_atom(access_mask=0xFF)
    results = await search_atoms(db_session, ["query"], role_mask=0xFF)
    assert len(results) >= 1
    for field in ["atom_id", "content", "kind", "domain", "access_mask", "relevance_score", "links", "canonical"]:
        assert field in results[0], f"Missing field: {field}"


async def test_search_atoms_top_k_limits_results(db_session, mock_embed_text, make_atom):
    for i in range(5):
        await make_atom(content=f"Unique fact number {i} about revenue growth.", access_mask=0xFF)
    results = await search_atoms(db_session, ["revenue"], role_mask=0xFF, top_k=2)
    assert len(results) <= 2


async def test_search_atoms_no_atoms_returns_empty(db_session, mock_embed_text):
    results = await search_atoms(db_session, ["query"], role_mask=0xFF)
    assert results == []


async def test_search_atoms_relevance_score_between_zero_and_one(db_session, mock_embed_text, make_atom):
    await make_atom(access_mask=0xFF, dense_vec=make_vector(0))
    results = await search_atoms(db_session, ["query"], role_mask=0xFF)
    for r in results:
        assert 0.0 <= r["relevance_score"] <= 1.0


# ── Multiple hypotheses ───────────────────────────────────────────────────────


async def test_search_atoms_accepts_multiple_hypotheses(db_session, mock_embed_text, make_atom):
    atom = await make_atom(content="Revenue grew 20% in Q2.", access_mask=0xFF)
    results = await search_atoms(
        db_session, ["Revenue grew in Q2.", "Sales exceeded targets.", "Q2 metrics improved."], role_mask=0xFF
    )
    assert str(atom.id) in [r["atom_id"] for r in results]


async def test_rrf_deduplicates_atoms_across_hypotheses(db_session, mock_embed_text, make_atom):
    # Single atom should appear exactly once even with multiple hypotheses
    await make_atom(content="Revenue grew 20% in Q2.", access_mask=0xFF)
    results = await search_atoms(
        db_session, ["Revenue grew.", "Sales increased in Q2.", "Q2 performance improved."], role_mask=0xFF
    )
    atom_ids = [r["atom_id"] for r in results]
    assert len(atom_ids) == len(set(atom_ids)), "Duplicate atom_ids in results"


# ── is_superseded filter ──────────────────────────────────────────────────────


async def test_excludes_superseded_atoms(db_session, mock_embed_text, make_atom):
    await make_atom(content="Superseded metric value.", access_mask=0xFF, is_superseded=True)
    results = await search_atoms(db_session, ["metric value"], role_mask=0xFF)
    assert results == []


async def test_includes_non_superseded_atoms(db_session, mock_embed_text, make_atom):
    atom = await make_atom(content="Current metric value.", access_mask=0xFF, is_superseded=False)
    results = await search_atoms(db_session, ["metric value"], role_mask=0xFF)
    assert any(r["atom_id"] == str(atom.id) for r in results)


# ── canonical field in results ────────────────────────────────────────────────


async def test_result_includes_canonical_field(db_session, mock_embed_text, make_atom):
    await make_atom(access_mask=0xFF)
    results = await search_atoms(db_session, ["query"], role_mask=0xFF)
    assert len(results) >= 1
    assert "canonical" in results[0]


async def test_result_canonical_populated_when_set(db_session, mock_embed_text, make_atom):
    canon = {"subject": "revenue", "predicate": "growth", "object": "", "value": 20.0, "unit": "%", "period": "Q2 2025"}
    atom = await make_atom(content="Revenue grew 20%.", access_mask=0xFF, canonical=canon)
    results = await search_atoms(db_session, ["revenue"], role_mask=0xFF)
    matching = [r for r in results if r["atom_id"] == str(atom.id)]
    assert len(matching) == 1
    assert matching[0]["canonical"]["subject"] == "revenue"


# ── canonical period pre-filter ───────────────────────────────────────────────


async def test_period_filter_excludes_non_matching_period(db_session, mock_embed_text, make_atom):
    # Q3 atom should be excluded when searching with period="Q2 2024"
    await make_atom(
        content="SOC 2 certification is Q3 priority.",
        access_mask=0xFF,
        canonical_period="Q3",
    )
    q2_atom = await make_atom(
        content="Revenue grew 20% in Q2.",
        access_mask=0xFF,
        canonical_period="Q2 2024",
    )
    results = await search_atoms(
        db_session, ["Q2 revenue"], role_mask=0xFF,
        query_canonical={"period": "Q2 2024"},
    )
    atom_ids = [r["atom_id"] for r in results]
    assert str(q2_atom.id) in atom_ids


async def test_period_filter_keeps_atoms_without_period(db_session, mock_embed_text, make_atom):
    # Non-metric atoms (no canonical_period) should survive any period filter
    atom = await make_atom(
        content="General company fact with no period.",
        access_mask=0xFF,
        canonical_period=None,
    )
    results = await search_atoms(
        db_session, ["company fact"], role_mask=0xFF,
        query_canonical={"period": "Q2 2024"},
    )
    assert any(r["atom_id"] == str(atom.id) for r in results)


# ── re-ranking: confidence boost ─────────────────────────────────────────────


async def test_confidence_boost_ranks_high_confidence_first(db_session, mock_embed_text, make_atom):
    high = await make_atom(
        content="High confidence metric result.",
        kind="metric",
        access_mask=0xFF,
        dense_vec=make_vector(0),
        confidence=3.0,
    )
    low = await make_atom(
        content="Low confidence metric result.",
        kind="metric",
        access_mask=0xFF,
        dense_vec=make_vector(0),
        confidence=1.0,
    )
    results = await search_atoms(db_session, ["query"], role_mask=0xFF)
    ids = [r["atom_id"] for r in results]
    assert ids.index(str(high.id)) < ids.index(str(low.id))


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
