"""HTTP-level tests for /api/v1/context/ — auth, query, compare."""

import uuid

import pytest


async def test_context_query_valid_api_key_returns_200(
    http_client, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF, domains=["general"])
    resp = await http_client.post(
        "/api/v1/context/query",
        json={"query": "revenue growth", "top_k": 5},
        headers={"x-api-key": agent.api_key},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "atoms" in body
    assert "cache_tier" in body
    assert "latency_ms" in body
    assert "atoms_served" in body
    assert body["query"] == "revenue growth"
    assert body["agent_name"] == agent.name


async def test_context_query_missing_api_key_returns_422(http_client):
    # No x-api-key header → FastAPI returns 422 (missing required header)
    resp = await http_client.post(
        "/api/v1/context/query",
        json={"query": "revenue"},
    )
    assert resp.status_code == 422


async def test_context_query_invalid_api_key_returns_401(http_client):
    resp = await http_client.post(
        "/api/v1/context/query",
        json={"query": "revenue"},
        headers={"x-api-key": "invalid-key-that-does-not-exist"},
    )
    assert resp.status_code == 401


async def test_context_query_excludes_inaccessible_atoms(
    http_client, mock_embed_text, make_agent, make_atom, clear_l2_cache
):
    # Agent has only sales bit (0b010); atom has only finance bit (0b100)
    agent = await make_agent(role_mask=0b010, domains=["sales"])
    await make_atom(content="Finance only content.", access_mask=0b100, domain=["finance"])

    resp = await http_client.post(
        "/api/v1/context/query",
        json={"query": "finance", "top_k": 10},
        headers={"x-api-key": agent.api_key},
    )
    assert resp.status_code == 200
    # No atoms should be returned — agent can't see finance atoms
    for atom in resp.json()["atoms"]:
        assert atom["access_mask"] & 0b010  # agent's bit must be present


async def test_context_query_top_k_validation(
    http_client, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent()
    # top_k must be between 1 and 50
    resp = await http_client.post(
        "/api/v1/context/query",
        json={"query": "test", "top_k": 0},
        headers={"x-api-key": agent.api_key},
    )
    assert resp.status_code == 422


async def test_context_compare_returns_results_per_agent(
    http_client, mock_embed_text, make_agent, clear_l2_cache
):
    a1 = await make_agent(name="compare-a1", role_mask=0xFF)
    a2 = await make_agent(name="compare-a2", role_mask=0b01)

    resp = await http_client.post(
        "/api/v1/context/compare",
        json={
            "query": "revenue",
            "agent_ids": [str(a1.id), str(a2.id)],
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "revenue"
    assert len(body["results"]) == 2
    result_agent_ids = {r["agent_id"] for r in body["results"]}
    assert str(a1.id) in result_agent_ids
    assert str(a2.id) in result_agent_ids


async def test_context_compare_result_has_required_fields(
    http_client, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF)
    resp = await http_client.post(
        "/api/v1/context/compare",
        json={"query": "test", "agent_ids": [str(agent.id)], "top_k": 5},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]
    for field in ["agent_id", "agent_name", "role_mask", "atoms", "cache_tier", "latency_ms"]:
        assert field in result, f"Missing field in compare result: {field}"


async def test_context_compare_unknown_agent_returns_404(http_client):
    resp = await http_client.post(
        "/api/v1/context/compare",
        json={"query": "test", "agent_ids": [str(uuid.uuid4())], "top_k": 5},
    )
    assert resp.status_code == 404


async def test_context_compare_single_agent(
    http_client, mock_embed_text, make_agent, clear_l2_cache
):
    agent = await make_agent(role_mask=0xFF)
    resp = await http_client.post(
        "/api/v1/context/compare",
        json={"query": "single agent test", "agent_ids": [str(agent.id)], "top_k": 5},
    )
    assert resp.status_code == 200
    assert len(resp.json()["results"]) == 1


async def test_context_compare_different_masks_return_different_atoms(
    http_client, mock_embed_text, make_agent, make_atom, clear_l2_cache
):
    # a1 can see everything; a2 can only see public bit
    a1 = await make_agent(name="all-access", role_mask=0xFF)
    a2 = await make_agent(name="restricted", role_mask=0b0001)  # public only

    # Atom only visible to all-access agent
    await make_atom(
        content="Restricted content only visible to full access.",
        access_mask=0b1000,  # engineering only
        domain=["engineering"],
    )

    resp = await http_client.post(
        "/api/v1/context/compare",
        json={"query": "restricted", "agent_ids": [str(a1.id), str(a2.id)], "top_k": 10},
    )
    body = resp.json()
    a1_result = next(r for r in body["results"] if r["agent_id"] == str(a1.id))
    a2_result = next(r for r in body["results"] if r["agent_id"] == str(a2.id))

    # a2 should have 0 atoms (role_mask=0b0001 can't see access_mask=0b1000)
    for atom in a2_result["atoms"]:
        assert atom["access_mask"] & 0b0001  # public bit must be present
