"""HTTP-level tests for /api/v1/agents/ — real DB (rolled back), no LLM."""

import pytest


async def test_create_agent_returns_200_with_api_key(http_client):
    resp = await http_client.post(
        "/api/v1/agents/",
        json={"name": "finance-bot", "role_mask": 4, "domains": ["finance"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "finance-bot"
    assert body["role_mask"] == 4
    assert body["domains"] == ["finance"]
    assert body["api_key"].startswith("lat_")
    assert "id" in body


async def test_create_agent_default_values(http_client):
    resp = await http_client.post("/api/v1/agents/", json={"name": "minimal-agent"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role_mask"] == 0
    assert body["max_tokens"] == 4000
    assert body["freshness_req"] == "24h"


async def test_list_agents_returns_created_agent(http_client):
    await http_client.post("/api/v1/agents/", json={"name": "listed-agent"})
    resp = await http_client.get("/api/v1/agents/")
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "listed-agent" in names


async def test_list_agents_returns_all_agents(http_client):
    await http_client.post("/api/v1/agents/", json={"name": "alpha-agent"})
    await http_client.post("/api/v1/agents/", json={"name": "beta-agent"})
    resp = await http_client.get("/api/v1/agents/")
    assert resp.status_code == 200
    names = [a["name"] for a in resp.json()]
    assert "alpha-agent" in names
    assert "beta-agent" in names


async def test_list_agents_empty_when_none_created(http_client):
    resp = await http_client.get("/api/v1/agents/")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_patch_agent_updates_role_mask(http_client, make_agent):
    agent = await make_agent(name="patchable-agent", role_mask=0b0001)
    resp = await http_client.patch(
        f"/api/v1/agents/{agent.id}",
        json={"role_mask": 0xFF},
    )
    assert resp.status_code == 200
    assert resp.json()["role_mask"] == 0xFF


async def test_patch_agent_updates_domains(http_client, make_agent):
    agent = await make_agent(name="domain-patcher", domains=["sales"])
    resp = await http_client.patch(
        f"/api/v1/agents/{agent.id}",
        json={"domains": ["engineering", "hr"]},
    )
    assert resp.status_code == 200
    assert set(resp.json()["domains"]) == {"engineering", "hr"}


async def test_patch_agent_not_found_returns_404(http_client):
    import uuid
    resp = await http_client.patch(
        f"/api/v1/agents/{uuid.uuid4()}",
        json={"role_mask": 1},
    )
    assert resp.status_code == 404


async def test_delete_agent_removes_it(http_client, make_agent):
    agent = await make_agent(name="deletable-agent")
    resp = await http_client.delete(f"/api/v1/agents/{agent.id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    list_resp = await http_client.get("/api/v1/agents/")
    names = [a["name"] for a in list_resp.json()]
    assert "deletable-agent" not in names


async def test_delete_agent_not_found_returns_404(http_client):
    import uuid
    resp = await http_client.delete(f"/api/v1/agents/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_agent_stats_zero_for_new_agent(http_client, make_agent):
    agent = await make_agent(name="stats-agent")
    resp = await http_client.get(f"/api/v1/agents/{agent.id}/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_queries"] == 0
    assert body["avg_latency_ms"] == 0.0
    assert body["cache_hit_rate"] == 0.0
    assert body["agent_name"] == "stats-agent"


async def test_get_agent_stats_not_found_returns_404(http_client):
    import uuid
    resp = await http_client.get(f"/api/v1/agents/{uuid.uuid4()}/stats")
    assert resp.status_code == 404
