/**
 * Lattice API client.
 */

const BASE = "/api/v1";

export async function uploadPDF(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/sources/upload/pdf`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listSources() {
  const res = await fetch(`${BASE}/sources/`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function deleteSource(sourceId) {
  const res = await fetch(`${BASE}/sources/${sourceId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function search(query, apiKey, topK = 5) {
  const res = await fetch(`${BASE}/search/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Api-Key": apiKey },
    body: JSON.stringify({ query, top_k: topK }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function listAgents() {
  const res = await fetch(`${BASE}/agents/`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function createAgent(name) {
  const res = await fetch(`${BASE}/agents/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function grantAccess(agentId, sourceId) {
  const res = await fetch(`${BASE}/agents/${agentId}/grant`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: sourceId }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
