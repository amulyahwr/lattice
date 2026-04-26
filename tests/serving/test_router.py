"""Tests for query_context and compare_context — real DB, L3-only."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from backend.models.atoms import AccessLog
from backend.serving.router import compare_context, query_context
from tests.helpers import make_vector

# ── L3 fallback path ──────────────────────────────────────────────────────────


async def test_query_context_l3_returns_result_dict(
    db_session, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF, domains=["general"])
    result = await query_context(db_session, "revenue query", agent)

    assert "atoms" in result
    assert "cache_tier" in result
    assert "latency_ms" in result
    assert "atoms_served" in result
    assert "total_tokens" in result
    assert result["cache_tier"] == "L3"


async def test_query_context_l3_returns_accessible_atoms(
    db_session, mock_embed_text, make_agent, make_atom, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF, domains=["general"])
    atom = await make_atom(
        content="General knowledge fact here.", access_mask=0xFF, domain=["general"]
    )
    result = await query_context(db_session, "knowledge", agent)
    # With min_relevance=0.3 and same query/atom vector, atom should be returned
    atom_ids = [a["atom_id"] for a in result["atoms"]]
    assert str(atom.id) in atom_ids


async def test_query_context_preflight_skips_when_no_accessible_atoms(
    db_session, mock_embed_text, make_agent, clear_l2_cache
):
    # No atoms in DB → pre-flight returns immediately
    agent = await make_agent(role_mask=0b010, domains=["sales"])
    result = await query_context(db_session, "query", agent)
    assert result["atoms"] == []
    assert result["atoms_served"] == 0
    # embed_text should NOT be called (pre-flight short-circuits)
    mock_embed_text.assert_not_called()


async def test_query_context_access_control_excludes_inaccessible_atoms(
    db_session, mock_embed_text, make_agent, make_atom, clear_l2_cache
):
    # Agent has only sales bit; atom has only finance bit → excluded
    agent = await make_agent(role_mask=0b0010, domains=["sales"])
    await make_atom(
        content="Finance content only.", access_mask=0b0100, domain=["finance"]
    )
    result = await query_context(db_session, "finance", agent)
    assert result["atoms"] == []


async def test_query_context_token_budget_trims_atoms(
    db_session, mock_embed_text, make_agent, make_atom, clear_l2_cache
):
    # max_tokens=1: no atom should fit (every atom has >1 token)
    agent = await make_agent(role_mask=0xFF, domains=["general"], max_tokens=1)
    await make_atom(
        content="This is a longer sentence with multiple tokens.",
        access_mask=0xFF,
        domain=["general"],
    )
    result = await query_context(db_session, "tokens", agent)
    assert result["total_tokens"] <= 1


async def test_query_context_logs_access_event(
    db_session, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF, domains=["general"])
    await query_context(db_session, "my specific query", agent)
    await db_session.flush()

    logs = (
        (
            await db_session.execute(
                select(AccessLog).where(AccessLog.agent_id == agent.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(logs) == 1
    assert logs[0].query == "my specific query"
    assert logs[0].cache_tier == "L3"


# ── compare_context ───────────────────────────────────────────────────────────


async def test_compare_context_returns_one_result_per_agent(
    db_session, mock_embed_text, make_agent, clear_l2_cache
):
    a1 = await make_agent(name="agent-1", role_mask=0xFF)
    a2 = await make_agent(name="agent-2", role_mask=0b01)
    results = await compare_context(db_session, "test query", [a1, a2])
    assert len(results) == 2
    agent_ids = {r["agent_id"] for r in results}
    assert str(a1.id) in agent_ids
    assert str(a2.id) in agent_ids


async def test_compare_context_includes_agent_name(
    db_session, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(name="named-agent", role_mask=0xFF)
    results = await compare_context(db_session, "query", [agent])
    assert results[0]["agent_name"] == "named-agent"
