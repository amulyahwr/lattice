import type {
  LatticeStats,
  Source,
  AgentProfile,
  ContextResult,
  AuditEntry,
  ActivityEvent,
  AtomDetail,
  AtomNeighborhood,
} from "../lib/types";

const BASE_URL = "/api/v1";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

// ── Raw backend shapes (before transformation) ──

interface BackendActivityEvent {
  type: string;
  agent_name?: string;
  query?: string;
  decision?: string;
  atoms_served?: number;
  cache_tier?: string;
  latency_ms?: number;
  timestamp?: string;
}

interface BackendCompareResult {
  agent_id: string;
  agent_name: string;
  role_mask: number;
  atoms: Array<Record<string, unknown>>;
  cache_tier: string;
  latency_ms: number;
  atoms_served: number;
  atoms_filtered: number;
  total_tokens: number;
}

interface BackendAuditEntry {
  id: string;
  agent_name?: string;
  query?: string;
  decision: string;
  atoms_served: number;
  atoms_filtered: number;
  cache_tier?: string;
  latency_ms?: number;
  timestamp?: string;
}

// ── Transformers ──

function toActivityEvent(e: BackendActivityEvent, idx: number): ActivityEvent {
  const description =
    e.agent_name && e.query
      ? `${e.agent_name} queried "${e.query}"`
      : (e.query ?? e.agent_name ?? "System event");
  return {
    id: `${e.timestamp ?? idx}-${idx}`,
    type: e.decision === "denied" ? "access_denied" : "query",
    description,
    agent: e.agent_name ?? undefined,
    cache_tier: (e.cache_tier as "L2" | "L3") ?? undefined,
    latency_ms: e.latency_ms ?? undefined,
    timestamp: e.timestamp ?? new Date().toISOString(),
  };
}

function toAtom(a: Record<string, unknown>) {
  return {
    id: (a.atom_id ?? a.id ?? "") as string,
    content: (a.content ?? "") as string,
    kind: (a.kind ?? "fact") as import("../lib/types").AtomKind,
    domain: (a.domain ?? []) as string[],
    confidence: (a.confidence ?? 1.0) as number,
    freshness: (a.freshness ?? "") as string,
    source_name: a.source_name as string | undefined,
    source_type: a.source_type as string | undefined,
    links: (a.links ?? []) as { target_id: string; relation: string }[],
    version: (a.version ?? 1) as number,
    relevance_score: a.relevance_score as number | undefined,
  };
}

function toAtomDetail(a: Record<string, unknown>): AtomDetail {
  return {
    id: (a.atom_id ?? a.id ?? "") as string,
    content: (a.content ?? "") as string,
    kind: (a.kind ?? "fact") as import("../lib/types").AtomKind,
    domain: (a.domain ?? []) as string[],
    confidence: (a.confidence ?? 1.0) as number,
    freshness: (a.freshness ?? "") as string,
    source_name: a.source_name as string | undefined,
    source_type: a.source_type as string | undefined,
    links: (a.links ?? []) as { target_id: string; relation: string }[],
    version: (a.version ?? 1) as number,
    relevance_score: a.relevance_score as number | undefined,
    raw_content: a.raw_content as string | undefined,
    canonical: a.canonical as Record<string, unknown> | undefined,
    access_mask: (a.access_mask ?? 0) as number,
    compiled_at: a.compiled_at as string | undefined,
    sources: (a.sources ?? []) as import("../lib/types").AtomSourceRef[],
  };
}

function toContextResult(
  r: BackendCompareResult,
  query: string,
): ContextResult {
  return {
    query,
    agent: r.agent_name,
    agent_id: r.agent_id,
    atoms: r.atoms.map(toAtom),
    cache_tier: r.cache_tier as "L2" | "L3",
    latency_ms: r.latency_ms,
    total_tokens: r.total_tokens,
    atoms_served: r.atoms_served,
    atoms_filtered: r.atoms_filtered,
  };
}

// ── API ──

export const api = {
  // Stats
  getStats: () => request<LatticeStats>("/admin/stats"),

  getActivity: async (limit = 50): Promise<ActivityEvent[]> => {
    const res = await request<{
      events: BackendActivityEvent[];
      total: number;
    }>(`/admin/activity?limit=${limit}`);
    return res.events.map(toActivityEvent);
  },

  // Sources
  getSources: () => request<Source[]>("/sources/"),

  ingestSource: async (file: File): Promise<Source> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${BASE_URL}/sources/ingest`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(`Ingest error: ${res.status}`);
    const data = await res.json();
    return {
      id: data.id,
      name: data.name,
      source_type: data.source_type,
      domains: [],
      atom_count: data.compilation?.atoms_created ?? 0,
      compilation_stats: data.compilation
        ? { atoms_by_kind: data.compilation.kinds ?? {} }
        : undefined,
    };
  },

  // Agents
  getAgents: () => request<AgentProfile[]>("/agents/"),

  createAgent: (data: Partial<AgentProfile>) =>
    request<AgentProfile>("/agents/", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateAgent: (id: string, data: Partial<AgentProfile>) =>
    request<AgentProfile>(`/agents/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteAgent: (id: string) =>
    request<{ status: string }>(`/agents/${id}`, { method: "DELETE" }),

  // Context
  compareContext: async (
    query: string,
    agentIds: string[],
  ): Promise<ContextResult[]> => {
    const res = await request<{
      query: string;
      results: BackendCompareResult[];
    }>("/context/compare", {
      method: "POST",
      body: JSON.stringify({ query, agent_ids: agentIds }),
    });
    return res.results.map((r) => toContextResult(r, res.query));
  },

  // Atoms
  getAtoms: async (
    params: {
      search?: string;
      kind?: string;
      domain?: string;
      limit?: number;
      offset?: number;
    } = {},
  ): Promise<AtomDetail[]> => {
    const qs = new URLSearchParams();
    if (params.search) qs.set("search", params.search);
    if (params.kind) qs.set("kind", params.kind);
    if (params.domain) qs.set("domain", params.domain);
    if (params.limit) qs.set("limit", String(params.limit));
    if (params.offset) qs.set("offset", String(params.offset));
    const raw = await request<Record<string, unknown>[]>(`/atoms/?${qs}`);
    return raw.map(toAtomDetail);
  },

  getAtom: async (id: string): Promise<AtomDetail> => {
    const raw = await request<Record<string, unknown>>(`/atoms/${id}`);
    return toAtomDetail(raw);
  },

  getAtomNeighborhood: async (id: string): Promise<AtomNeighborhood> => {
    const raw = await request<{
      center: Record<string, unknown>;
      neighbors: Array<{ atom: Record<string, unknown>; relation: string }>;
    }>(`/atoms/${id}/neighborhood`);
    return {
      center: toAtomDetail(raw.center),
      neighbors: raw.neighbors.map((n) => ({
        atom: toAtomDetail(n.atom),
        relation: n.relation,
      })),
    };
  },

  getFullGraph: async (
    limit = 100,
  ): Promise<{
    nodes: Array<{
      id: string;
      content: string;
      kind: string;
      domain: string[];
      confidence: number;
    }>;
    edges: Array<{ source: string; target: string; relation: string }>;
  }> => {
    return request(`/atoms/graph?limit=${limit}`);
  },

  // Audit
  getAuditLog: async (page = 1, pageSize = 50): Promise<AuditEntry[]> => {
    const res = await request<{ entries: BackendAuditEntry[]; total: number }>(
      `/audit/log?page=${page}&page_size=${pageSize}`,
    );
    return res.entries.map((e) => ({
      id: e.id,
      timestamp: e.timestamp ?? new Date().toISOString(),
      agent_name: e.agent_name,
      query: e.query,
      decision: e.decision,
      atoms_served: e.atoms_served,
      atoms_filtered: e.atoms_filtered,
      cache_tier: e.cache_tier as "L2" | "L3" | undefined,
      latency_ms: e.latency_ms,
    }));
  },
};
