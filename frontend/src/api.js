const BASE = "/api/v1";

async function throwIfError(res) {
  if (!res.ok) {
    const text = await res.text();
    let message;
    try { message = JSON.parse(text)?.detail; } catch { /* ignore */ }
    throw new Error(message || text || `HTTP ${res.status}`);
  }
}

export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/sources/upload/pdf`, { method: "POST", body: form });
  await throwIfError(res);
  return res.json();
}

export async function listSources() {
  const res = await fetch(`${BASE}/sources/`);
  await throwIfError(res);
  return res.json();
}

export async function deleteSource(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}`, { method: "DELETE" });
  await throwIfError(res);
  return res.json();
}

export async function search(query, apiKey, topK = 5) {
  const res = await fetch(`${BASE}/search/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Api-Key": apiKey },
    body: JSON.stringify({ query, top_k: topK }),
  });
  await throwIfError(res);
  return res.json();
}

export async function listAgents() {
  const res = await fetch(`${BASE}/agents/`);
  await throwIfError(res);
  return res.json();
}

export async function createAgent(name) {
  const res = await fetch(`${BASE}/agents/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  await throwIfError(res);
  return res.json();
}

export async function revokeAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/revoke/${sourceId}`, { method: "DELETE" });
  await throwIfError(res);
  return res.json();
}

export async function grantAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/grant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId }),
  });
  await throwIfError(res);
  return res.json();
}
