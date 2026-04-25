/**
 * Lattice API client.
 */

const BASE = "/api/v1";

async function throwIfError(res) {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

// Sources

export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/sources/upload/pdf`, { method: "POST", body: form });
  return throwIfError(res);
}

export async function listSources() {
  const res = await fetch(`${BASE}/sources/`);
  return throwIfError(res);
}

export async function updateSource(sourceId, data) {
  const res = await fetch(`${BASE}/sources/${sourceId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return throwIfError(res);
}

export async function deleteSource(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}`, { method: "DELETE" });
  return throwIfError(res);
}

export async function getSourceRecommendations(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}/recommendations`);
  return throwIfError(res);
}

// Search

export async function search(query, apiKey, topK = 5) {
  const res = await fetch(`${BASE}/search/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Api-Key": apiKey },
    body: JSON.stringify({ query, top_k: topK }),
  });
  return throwIfError(res);
}

// Agents

export async function listAgents() {
  const res = await fetch(`${BASE}/agents/`);
  return throwIfError(res);
}

export async function createAgent(data) {
  const res = await fetch(`${BASE}/agents/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return throwIfError(res);
}

export async function updateAgent(agentId, data) {
  const res = await fetch(`${BASE}/agents/${agentId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  return throwIfError(res);
}

export async function getAgentRecommendations(agentId) {
  const res = await fetch(`${BASE}/agents/${agentId}/recommendations`);
  return throwIfError(res);
}

export async function grantAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/grant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId }),
  });
  return throwIfError(res);
}

export async function denyAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/deny`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId }),
  });
  return throwIfError(res);
}

export async function deleteAgent(agentId) {
  const res = await fetch(`${BASE}/agents/${agentId}`, { method: "DELETE" });
  return throwIfError(res);
}

export async function revokeAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/revoke/${sourceId}`, {
    method: "DELETE",
  });
  return throwIfError(res);
}
