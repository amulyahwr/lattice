export type AtomKind = 'fact' | 'metric' | 'decision' | 'relationship' | 'event' | 'procedure'

export interface Atom {
  id: string
  content: string
  kind: AtomKind
  domain: string[]
  confidence: number
  freshness: string
  source_id: string
  source_name?: string
  links: { target_id: string; relation: string }[]
  version: number
}

export interface Frame {
  id: string
  name: string
  domain: string
  atom_count: number
  token_count: number
  access_count: number
  last_accessed: string
}

export interface AgentProfile {
  id: string
  name: string
  api_key: string
  purpose: string
  domains: string[]
  role_mask: number
  max_tokens: number
  query_count?: number
  avg_latency?: number
  cache_hit_rate?: number
}

export interface ContextResult {
  query: string
  agent: string
  atoms: Atom[]
  frame_id?: string
  cache_tier: 'L2' | 'L3'
  latency_ms: number
  total_tokens: number
  atoms_served: number
  atoms_filtered: number
}

export interface Source {
  id: string
  name: string
  source_type: string
  classification: string
  domains: string[]
  atom_count: number
  frame_count: number
  compiled_at: string
  compilation_stats?: {
    atomize_ms: number
    distill_ms: number
    embed_ms: number
    link_ms: number
    tag_ms: number
    index_ms: number
    atoms_by_kind: Record<string, number>
  }
}

export interface LatticeStats {
  total_atoms: number
  total_frames: number
  total_agents: number
  cache_hit_rate: number
  atoms_by_kind: Record<string, number>
}

export interface AuditEntry {
  id: string
  timestamp: string
  agent_id: string
  agent_name: string
  query: string
  atoms_served: number
  atoms_filtered: number
  cache_tier: 'L2' | 'L3'
  latency_ms: number
}

export interface ActivityEvent {
  id: string
  type: 'query' | 'compile' | 'access_denied'
  description: string
  agent?: string
  cache_tier?: 'L2' | 'L3'
  latency_ms?: number
  timestamp: string
}

export const ROLES = ['public', 'sales', 'finance', 'engineering', 'hr', 'legal', 'product', 'executive'] as const
export type Role = (typeof ROLES)[number]
