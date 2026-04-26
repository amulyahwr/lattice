export type AtomKind =
  | "fact"
  | "metric"
  | "decision"
  | "relationship"
  | "event"
  | "procedure";

export interface Atom {
  id: string; // mapped from backend's atom_id
  content: string;
  kind: AtomKind;
  domain: string[];
  confidence: number;
  freshness: string;
  source_name?: string;
  source_type?: string;
  links: { target_id: string; relation: string }[];
  version: number;
  relevance_score?: number;
}

export interface AgentProfile {
  id: string;
  name: string;
  api_key: string;
  purpose: string;
  domains: string[];
  role_mask: number;
  max_tokens: number;
  freshness_req?: string;
  created_at?: string;
  query_count?: number;
  avg_latency?: number;
  cache_hit_rate?: number;
}

export interface ContextResult {
  query: string;
  agent: string; // agent name
  agent_id: string;
  atoms: Atom[];
  cache_tier: "L2" | "L3";
  latency_ms: number;
  total_tokens: number;
  atoms_served: number;
  atoms_filtered: number;
}

export interface Source {
  id: string;
  name: string;
  source_type: string;
  domains: string[];
  atom_count: number;
  created_at?: string;
  compilation_stats?: {
    atomize_ms?: number;
    distill_ms?: number;
    embed_ms?: number;
    link_ms?: number;
    tag_ms?: number;
    index_ms?: number;
    atoms_by_kind: Record<string, number>;
  };
}

export interface LatticeStats {
  total_atoms: number;
  total_agents: number;
  total_sources?: number;
  atoms_by_kind: Record<string, number>;
  total_queries?: number;
}

export interface AuditEntry {
  id: string;
  timestamp: string;
  agent_id?: string;
  agent_name?: string;
  query?: string;
  decision: string;
  atoms_served: number;
  atoms_filtered: number;
  cache_tier?: "L2" | "L3";
  latency_ms?: number;
}

export interface ActivityEvent {
  id: string;
  type: "query" | "compile" | "access_denied";
  description: string;
  agent?: string;
  cache_tier?: "L2" | "L3";
  latency_ms?: number;
  timestamp: string;
}

export interface AtomSourceRef {
  source_id: string;
  source_name: string;
  source_type: string;
  is_primary: boolean;
}

export interface AtomDetail extends Atom {
  raw_content?: string;
  canonical?: Record<string, unknown>;
  access_mask: number;
  compiled_at?: string;
  sources: AtomSourceRef[];
}

export interface AtomNeighborhood {
  center: AtomDetail;
  neighbors: Array<{ atom: AtomDetail; relation: string }>;
}

export const ROLES = [
  "sales",
  "finance",
  "engineering",
  "hr",
  "legal",
  "product",
] as const;
export type Role = (typeof ROLES)[number];
