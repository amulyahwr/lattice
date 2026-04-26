# Lattice — Enterprise Context Engine Roadmap

**Vision:** Single broker for delivering the right context, at the right time, to any agent within an enterprise. Lattice doesn't own data — it connects to where data already lives and intelligently brokers it.

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

### Serving Enhancements

- [ ] **L2 frame cache (optional)** — pre-built context frames for common queries, <5ms lookups
- [ ] **L1 per-agent session cache** — in-memory atom set per active agent, sub-1ms lookups
- [ ] **L4 cold semantic search** — full corpus search for rare/new query patterns, <200ms
- [ ] **Frame lattice hierarchy** — parent/child frame relationships with join (∨) and meet (∧) operations for dynamic frame composition
- [ ] **Token budget trimming improvements** — smarter atom prioritization based on relevance, recency, confidence
- [ ] **Query result caching** — cache recent query results to avoid re-embedding same queries

### Compiler Improvements

- [ ] **Async compiler workers** — decouple ingestion from HTTP request lifecycle, queue-based processing
- [ ] **LLM-powered atomization** — use LLM for higher-quality atom extraction alongside regex patterns
- [ ] **LLM-powered distillation** — generate better token-efficient summaries vs extractive fallback
- [ ] **Contradiction detection** — when two sources disagree, flag both atoms with `contradicts` link
- [ ] **Incremental recompilation** — track source content hashes, only recompile changed atoms
- [ ] **Multi-format connectors** — Markdown, DOCX, HTML, CSV ingestion

### Access Control

- [ ] **Hierarchical bitmasks** — support very large orgs (>64 roles) with multi-level bitmask structure
- [ ] **Dynamic mask recomputation** — when org structure changes, cascade bitmask updates to affected atoms
- [ ] **Attribute-based policies** — supplement bitmasks with attribute conditions for edge cases

### Frontend

- ✅ **Atom Explorer** — search, browse, inspect individual atoms with full metadata
- ✅ **Graph Explorer** — interactive knowledge graph visualization of atom relationships (React Flow, circular nodes, relationship labels, auto-fit)
- [ ] **Real-time activity feed** — WebSocket-powered live updates on dashboard
- [ ] **Source detail page** — drill into a source, see all atoms, compilation history, recompile button

---

## Phase 3: Enterprise Features

### Push & Streaming

- [ ] **Subscription model** — agents subscribe to frames/domains, receive push updates on context changes
- [ ] **Push Gateway** — gRPC streaming + WebSocket transports for real-time context delivery
- [ ] **Delta protocol** — version-tracked atoms; on re-query, send only what changed since last fetch
- [ ] **Context Diff API** — `GET /v1/context/query?since=version:42` returns delta, not full payload

### Sparse Distributed Representations (SDR)

- [ ] **SDR generation** — random projection from dense embeddings to sparse binary vectors (2048-bit)
- [ ] **SDR matching at L1/L2** — hardware-accelerated bitwise operations for nanosecond similarity
- [ ] **SDR-based frame lookup** — use sparse vectors for frame cache key matching instead of exact domain match

### Event-Driven Architecture

- [ ] **Event bus integration** — NATS JetStream or Kafka for frame invalidation events
- [ ] **Source webhooks** — receive real-time change notifications from source systems
- [ ] **Compiler event pipeline** — atom create/update/delete events flow from compiler to mesh

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
- [ ] **Context quality scoring** — track which atoms agents actually use (feedback loops)

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
