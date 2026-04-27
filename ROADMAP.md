# Lattice — Enterprise Context Engine Roadmap

**Vision:** Single broker for delivering the right context, at the right time, to any agent within an enterprise. Lattice doesn't own data — it connects to where data already lives and intelligently brokers it.

---

## Mental Model

**Agents are transmitters.** Each agent simultaneously broadcasts two signals:
- *Identity signal* — `role_mask` + `domains`: "here is who I am and what I'm allowed to see"
- *Intent signal* — query embedding: "here is what I want"

**Atoms are receivers.** Each atom simultaneously broadcasts two signals:
- *Identity signal* — `access_mask` + `domain[]` + `kind`: "here is who I am and who can see me"
- *Content signal* — `dense_vec` + `content`: "here is what I have"

**Lattice is the structure in between.** Its job is to arrange all atoms into an optimized lattice so that any agent can quickly find what it's looking for. Matching runs two orthogonal filters in sequence:
1. `role_mask & access_mask != 0` — hard identity gate, nanoseconds, eliminates invisible atoms
2. `cosine(query_vec, dense_vec)` — soft content rank, ~50ms, finds the most relevant atoms

The `links[]` between atoms are the lattice topology — not just metadata. The compiler doesn't just extract facts; it arranges atoms into a structure where related signals cluster together. Cross-source linking, domain groups, and typed edges (`supersedes`, `contradicts`) make the lattice navigable, not just searchable.

Graph-traversal serving (`?hops=1`, Phase 2) is the natural extension: seed via signal match, then walk the lattice to pull in connected context that embeddings alone wouldn't surface.

Agent session memory (Phase 2) makes the transmitter dynamic — an agent's identity and intent signals grow richer the more it queries. The lattice doesn't change; the transmitter gets better at tuning its frequency.

---

## Priority List

Ordered by impact-to-effort ratio and competitive urgency. Items above the line are must-haves before the next funding / customer milestone.

| # | Item | Phase | Why Now |
|---|------|-------|---------|
| 1 | **Atom versioning + `atom_versions` table** | 2 | Closes biggest gap vs. HydraDB; foundational for temporal query, state diff, and change tracking |
| 2 | **Temporal query API (`?as_of=`, `valid_from/until`)** | 2 | Turns Lattice into a temporal knowledge layer, not just a snapshot store; enables "what was true on date X" |
| 3 | **Graph-traversal serving mode** | 2 | Uses existing `atom.links[]` data with no schema change; directly answers "flat embeddings" criticism |
| 4 | **`supersedes` link type + state-diff on re-ingest** | 2 | Upgrade planned `contradicts` detection to full state evolution; required for temporal versioning story |
| 5 | **Contradiction detection** | 2 | Already planned; accelerate — needed alongside supersedes |
| 6 | **Agent session memory** | 2 | Closes HydraDB's "persistent agent memory" pitch; differentiates Lattice for agent-first customers |
| 7 | **Async compiler workers** | 2 | Unblocks production ingest throughput; needed before first enterprise pilot |
| 8 | **Sliding window ingestion** | 2 | Better boundary-spanning relationship extraction; low-risk compiler-only change |
| 9 | **LongMemEval-S benchmark** | 2 | Gives a competitive accuracy number to cite against HydraDB's 90.79% claim |
| 10 | **L2 frame cache** | 2 | Performance optimization for hot paths; can defer until latency becomes a complaint |
| 11 | **Context Diff API** | 2 | Moved up from Phase 3 — shares groundwork with atom versioning |
| 12 | **Push Gateway + subscription model** | 3 | Real-time context delivery; needed for agentic workflows at scale |
| 13 | **Confluence / Slack / Jira connectors** | 3 | Expands TAM; enterprise customers need connectors before they can adopt |
| 14 | **OpenTelemetry + Prometheus** | 3 | Enterprise procurement requirement; often a blocker |
| 15 | **Multi-tenant deployment** | 4 | Required for SaaS; can serve early customers single-tenant |
| 16 | **Python + TypeScript SDKs** | 4 | Developer experience; needed for self-serve adoption |
| 17 | **SOC 2 / HIPAA readiness** | business | Required for FinServ / Healthcare verticals |

---

## Phase 1: MVP ✅ (Complete - L3-Only)

See [MVP.md](./MVP.md) for full scope.

**Core deliverables:**

- ✅ Context Atom data model (replaces chunks + entities)
- ✅ Compiler pipeline: atomize → distill → embed → link → tag → index → cross-link (7 stages, synchronous)
- ✅ Cross-source relationship linking — domain-aware candidate selection (DOMAIN_GROUPS) + LLM link inference, similarity-gated (cosine ≥ 0.5)
- ✅ L3-only serving: pgvector search with bitmask pre-filtering (~40-60ms)
- ✅ Bitmask access control (64-bit)
- ✅ Agent profiles with role masks and token budgets
- ✅ PDF + plain text connectors
- ✅ REST API for ingest, query, agents, admin (incl. `POST /admin/relink`)
- ✅ Demo frontend: Dashboard, Sources, Agents, Playground, Audit
- ✅ Atom Explorer — search, browse, and inspect individual atoms with full metadata
- ✅ Graph Explorer — interactive knowledge graph visualization (React Flow, circular nodes, relationship labels)

**Architecture decision:** Started with L3-only (pgvector) instead of L2+L3. Simpler, fast enough for production. L2 frame cache can be added later as optimization.

---

## Phase 2: Production Hardening

### Temporal Knowledge Layer _(new — closes gap vs. HydraDB)_

- [ ] **Atom versioning** — `atom_versions` table tracks every change to an atom's content with timestamps; superseded versions are retained with a `superseded_by` link rather than overwritten; enables full audit history of what the system believed at any point in time
- [ ] **Time-bounded fact modeling** — add `valid_from` / `valid_until` fields to atoms to represent facts with explicit lifetimes (e.g. "CEO was Alice from 2020–2023"); query engine filters by validity window
- [ ] **Temporal query API** — `?as_of=<ISO-timestamp>` parameter on `/v1/context/query` returns atoms valid at that point in time; complements the existing version-delta `Context Diff API`
- [ ] **`supersedes` link type** — new typed edge; when re-ingest produces an atom that replaces an existing one, the compiler emits a `supersedes` link and timestamps the transition rather than silently deduping
- [ ] **State-diff on re-ingest** — when the same fact changes across ingestion runs, detect the delta, emit a structured state-change event, and record the transition in atom history; lays groundwork for event bus in Phase 3
- [ ] **Context Diff API** — `GET /v1/context/query?since=version:42` returns delta since last fetch, not full payload; moved up from Phase 3 because groundwork is shared with atom versioning

### Serving Enhancements

- [ ] **Graph-traversal serving mode** — optional `?hops=1` parameter on `/v1/context/query` seeds via pgvector similarity then expands via `atom.links[]`; hybrid retrieval uses existing data with no schema change; directly answers "flat embeddings" criticism
- [ ] **L2 frame cache (optional)** — pre-built context frames for common queries, <5ms lookups
- [ ] **L1 per-agent session cache** — in-memory atom set per active agent, sub-1ms lookups
- [ ] **L4 cold semantic search** — full corpus search for rare/new query patterns, <200ms
- [ ] **Frame lattice hierarchy** — parent/child frame relationships with join (∨) and meet (∧) operations for dynamic frame composition
- [ ] **Token budget trimming improvements** — smarter atom prioritization based on relevance, recency, confidence
- [ ] **Query result caching** — cache recent query results to avoid re-embedding same queries

### Agent Session Memory _(new — closes gap vs. HydraDB)_

- [ ] **Agent interaction history** — track which atoms each agent has accessed, which queries it has issued, and which domains it has focused on across sessions
- [ ] **Recency-weighted retrieval** — boost atoms the agent has recently engaged with during L3 scoring; same query returns progressively better results as agent builds history
- [ ] **Agent preference inference** — infer agent domain affinities from access patterns; auto-suggest domain refinements for agent profiles
- [ ] **Session context continuity** — when the same agent queries repeatedly within a time window, maintain a lightweight session state that biases retrieval toward the current task

### Compiler Improvements

- [ ] **Async compiler workers** — decouple ingestion from HTTP request lifecycle, queue-based processing
- [ ] **Sliding window ingestion** — replace fixed-chunk atomization with overlapping windows (e.g. 50% overlap) to preserve relationship context at chunk boundaries; compiler-only change, no serving impact
- [ ] **LLM-powered atomization** — use LLM for higher-quality atom extraction alongside regex patterns
- [ ] **LLM-powered distillation** — generate better token-efficient summaries vs extractive fallback
- [ ] **Contradiction detection** — when two sources disagree, flag both atoms with `contradicts` link
- [ ] **Incremental recompilation** — track source content hashes, only recompile changed atoms
- [ ] **Multi-format connectors** — Markdown, DOCX, HTML, CSV ingestion

### Evaluation & Benchmarks _(new — competitive positioning)_

- [ ] **LongMemEval-S benchmark run** — evaluate Lattice against the same benchmark HydraDB cites (90.79%); surfaces compiler quality gaps and produces a competitive accuracy number
- [ ] **Internal eval harness** — test query suite with expected atom sets; regression tracking across compiler iterations
- [ ] **Context quality scoring** — track which atoms agents actually use; close the feedback loop into compiler quality

### Access Control

- [ ] **Hierarchical bitmasks** — support very large orgs (>64 roles) with multi-level bitmask structure
- [ ] **Dynamic mask recomputation** — when org structure changes, cascade bitmask updates to affected atoms
- [ ] **Attribute-based policies** — supplement bitmasks with attribute conditions for edge cases

### Frontend

- ✅ **Atom Explorer** — search, browse, inspect individual atoms with full metadata
- ✅ **Graph Explorer** — interactive knowledge graph visualization of atom relationships (React Flow, circular nodes, relationship labels, auto-fit)
- [ ] **Atom version timeline** — visualize the history of an atom: what it said at each version, what triggered changes
- [ ] **Real-time activity feed** — WebSocket-powered live updates on dashboard
- [ ] **Source detail page** — drill into a source, see all atoms, compilation history, recompile button

---

## Phase 3: Enterprise Features

### Push & Streaming

- [ ] **Subscription model** — agents subscribe to frames/domains, receive push updates on context changes
- [ ] **Push Gateway** — gRPC streaming + WebSocket transports for real-time context delivery
- [ ] **Delta protocol** — version-tracked atoms; on re-query, send only what changed since last fetch
- [ ] **Compiler event pipeline** — atom create/update/delete/supersede events flow from compiler to mesh

### Sparse Distributed Representations (SDR)

- [ ] **SDR generation** — random projection from dense embeddings to sparse binary vectors (2048-bit)
- [ ] **SDR matching at L1/L2** — hardware-accelerated bitwise operations for nanosecond similarity
- [ ] **SDR-based frame lookup** — use sparse vectors for frame cache key matching instead of exact domain match

### Event-Driven Architecture

- [ ] **Event bus integration** — NATS JetStream or Kafka for frame invalidation and state-change events
- [ ] **Source webhooks** — receive real-time change notifications from source systems

### Advanced Connectors

- [ ] **Confluence connector** — space/page sync with permission mapping
- [ ] **Slack connector** — channel message ingestion with access inheritance
- [ ] **Jira connector** — issue/project context with role mapping
- [ ] **Database connector** — SQL query results as atoms with schema-aware extraction
- [ ] **REST API connector** — generic API polling with configurable extraction
- [ ] **Email connector** — inbox ingestion with sender/recipient access scoping
- [ ] **Google Workspace connector** — Docs, Sheets, Drive with sharing permission mapping
- [ ] **GitHub connector** — repos, PRs, issues, wiki pages as enterprise knowledge

### Observability

- [ ] **OpenTelemetry integration** — distributed tracing across compiler + serving
- [ ] **Prometheus metrics** — standard metric export for enterprise monitoring stacks
- [ ] **Compliance reporting** — scheduled PDF/CSV reports of access patterns, data residency

### Frontend

- [ ] **Admin console** — role/bitmask management, org structure editor, connector config
- [ ] **Compliance dashboard** — access pattern visualization, data residency map, audit export
- [ ] **Agent analytics** — per-agent usage trends, most-queried topics, latency percentiles
- [ ] **Demo mode** — one-click seed data + guided walkthrough for sales demos

---

## Phase 4: Scale & Multi-Tenancy

### Infrastructure

- [ ] **Multi-tenant deployment** — isolated atom stores per tenant, shared mesh infrastructure
- [ ] **Distributed atom store** — migrate from single Postgres to sharded store (ScyllaDB / TiKV / FoundationDB)
- [ ] **Distributed L2 cache** — Redis Cluster or Dragonfly for shared frame cache across mesh nodes
- [ ] **Mesh node auto-scaling** — stateless serving nodes scale with agent connection count
- [ ] **Compiler worker pool** — auto-scale compiler workers based on ingestion queue depth

### Protocol & SDK

- [ ] **gRPC interface** — high-throughput binary protocol for production agent integrations
- [ ] **Python SDK** — `from lattice import LatticeClient` with query, subscribe, feedback
- [ ] **TypeScript SDK** — npm package for JS/TS agent frameworks
- [ ] **OpenAI-compatible endpoint** — drop-in replacement for retrieval-augmented workflows
- [ ] **LangChain / LlamaIndex integration** — Lattice as a retrieval backend for popular frameworks

### Governance

- [ ] **Data residency controls** — per-domain region pinning for compliance (GDPR, CCPA)
- [ ] **Retention policies** — automated atom expiry based on classification level and age
- [ ] **Right to deletion** — GDPR delete propagation: source deletion cascades to atoms within SLA
- [ ] **Cross-tenant isolation audit** — verify no atom leaks between tenants

### Performance Targets (at scale)

| Metric                    | Target                   |
| ------------------------- | ------------------------ |
| L1 query (p99)            | < 1ms                    |
| L2 query (p99)            | < 5ms                    |
| L3 query (p99)            | < 50ms                   |
| L4 query (p99)            | < 200ms                  |
| Cache hit rate (L1+L2)    | > 90%                    |
| Compile throughput        | > 1000 atoms/sec/worker  |
| Push notification latency | < 100ms                  |
| Concurrent agents         | > 10,000 per mesh node   |
| Atom store capacity       | > 100M atoms per cluster |

---

## Phase 5: Intelligence Layer

- [ ] **Context quality feedback loops** — agents report which atoms were useful; compiler learns to produce better atoms
- [ ] **Predictive pre-warming** — ML model predicts which frames agents will need next, pre-warms L2
- [ ] **Automatic frame discovery** — analyze co-access patterns to auto-generate new frames
- [ ] **Cross-domain insight detection** — find non-obvious connections between atoms in different domains
- [ ] **Context summarization chains** — when an agent needs a broad overview, auto-compose summary from multiple frames
- [ ] **Agent collaboration context** — when multiple agents work on the same task, share a context session

---

## Business (Parallel Track)

- [ ] **Pricing model decision** — per atom / per query / per agent seat / per connector
- [ ] **Open-source strategy** — core open-source with enterprise features? Full proprietary?
- [ ] **First target vertical** — FinServ, Healthcare, Tech — each has different compliance needs
- [ ] **SOC 2 / HIPAA readiness** — audit controls, encryption, access logging for regulated industries
- [ ] **Self-hosted vs cloud** — support both; enterprise wants on-prem, SMB wants cloud

---

## Status

| Phase                 | Status      | Target |
| --------------------- | ----------- | ------ |
| Phase 1: MVP          | ✅ Complete | —      |
| Phase 2: Production   | 📋 Planned  | —      |
| Phase 3: Enterprise   | 📋 Planned  | —      |
| Phase 4: Scale        | 📋 Planned  | —      |
| Phase 5: Intelligence | 💡 Vision   | —      |

---

_Last updated: 2026-04-26_
