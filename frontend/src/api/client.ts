const BASE_URL = '/api/v1'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export const api = {
  // Stats
  getStats: () => request<import('../lib/types').LatticeStats>('/admin/stats'),
  
  // Sources
  getSources: () => request<import('../lib/types').Source[]>('/sources'),
  ingestSource: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return fetch(`${BASE_URL}/sources/ingest`, { method: 'POST', body: form })
  },
  
  // Agents
  getAgents: () => request<import('../lib/types').AgentProfile[]>('/agents'),
  createAgent: (data: Partial<import('../lib/types').AgentProfile>) =>
    request<import('../lib/types').AgentProfile>('/agents', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  
  // Context
  queryContext: (query: string, agentId: string) =>
    request<import('../lib/types').ContextResult>('/context/query', {
      method: 'POST',
      body: JSON.stringify({ query, agent_profile_id: agentId }),
    }),
  
  // Audit
  getAuditLog: () => request<import('../lib/types').AuditEntry[]>('/audit/log'),
}
