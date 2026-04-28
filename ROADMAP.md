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

| # | Item | Phase | Status | Why Now |
|---|------|-------|--------|---------|
| 1 | **Atom versioning + `atom_versions` table** | 1 | ✅ Done | Closes biggest gap vs. HydraDB; foundational for temporal query, state diff, and change tracking |
| 2 | **`supersedes` + `contradicts` + `confirms` link types** | 1 | ✅ Done | Stage 8 consolidator classifies near-duplicates via LLM; provenance preserved in `atom_versions` |
| 3 | **Multi-hypothesis search (HyDE, k=3) + RRF fusion** | 1 | ✅ Done | Eliminates single-hypothesis failure mode; atoms appearing across multiple search lists surface higher |
| 4 | **Canonical pre-filters (`canonical_subject`, `canonical_period`)** | 1 | ✅ Done | Period/subject extracted at ingest as indexed SQL columns; bidirectional ILIKE match at query time |
| 5 | **Period + subject normalisation** | 1 | ✅ Done | Consistent format at write and query time; "q2-2024" / "second quarter" → "Q2 2024" |
| 6 | **Optional LLM re-ranker (`deep_rerank=True`)** | 1 | ✅ Done | Second LLM pass scores candidates 1–10; falls back to heuristic order on any error |
| 7 | **Temporal query API (`?as_of=`, `valid_from/until`)** | 2 | 📋 Planned | Turns Lattice into a temporal knowledge layer; schema done (`valid_from/until` on atoms + versions table); API endpoint not yet built |
| 8 | **Graph-traversal serving mode** | 2 | 📋 Planned | Uses existing `atom.links[]` data with no schema change; directly answers "flat embeddings" criticism |
| 9 | **State-diff events on re-ingest** | 2 | 📋 Planned | Structured state-change events streamed out of consolidator; lays groundwork for event bus in Phase 3 |
| 10 | **Agent session memory** | 2 | 📋 Planned | Closes HydraDB's "persistent agent memory" pitch; differentiates Lattice for agent-first customers |
| 11 | **Async compiler workers** | 2 | 📋 Planned | Unblocks production ingest throughput; needed before first enterprise pilot |
| 12 | **Sliding window ingestion** | 2 | 📋 Planned | Better boundary-spanning relationship extraction; low-risk compiler-only change |
| 13 | **LongMemEval-S benchmark** | 2 | 📋 Planned | Gives a competitive accuracy number to cite against HydraDB's 90.79% claim |
| 14 | **L2 frame cache** | 2 | 📋 Planned | Performance optimization for hot paths; can defer until latency becomes a complaint |
| 15 | **Context Diff API** | 2 | 📋 Planned | Shares groundwork with atom versioning (now done); ready to build |
| — | _**Search Intelligence — Phase 2**_ | — | — | — |
| 22 | **BM25 + dense hybrid search** | 2 | ✅ Done | Pure-dense vectors miss exact term/ID/name matches; pgvector + tsvector fused via RRF (fusion layer already exists); no new dependency |
| 23 | **Kind-aware freshness decay** | 2 | 📋 Planned | `metric` atoms decay in weeks; `procedure` atoms in years; single formula change in `l3_search.py`; immediate relevance gain on metric queries |
| 24 | **Contradiction adjudication at query time** | 2 | 📋 Planned | Routes `contradicts` pairs to LLM re-ranker with targeted prompt; turns existing link data into active search feature; no competitor does this |
| 25 | **Graph-centrality atom boosting** | 2 | 📋 Planned | Pre-compute hub scores from in-degree across diverse link types; fold into heuristic re-scorer; uses existing link data, no traversal |
| 26 | **Minimum coverage set** | 2 | 📋 Planned | Evict near-semantic-duplicate results (cosine > 0.9 between results); saves token budget with no precision loss |
| 27 | **Temporal velocity scoring** | 2 | 📋 Planned | Detect hot-topic churn from `atom_versions`; surface warning at query time; pure read signal, no schema change |
| 28 | **Kind-aware query intent + intent-adaptive routing** | 2 | ✅ Done | Classify query by atom kind (metric/event/decision/procedure/fact); generate kind-flavored HyDE hypotheses; auto-configure deep_rerank, top_k, min_relevance per kind |
| 29 | **Knowledge gap detection** | 2 | 📋 Planned | Score KB coverage as `high/partial/gap` after search; agents know when operating on thin evidence; differentiator, no competitor surfaces this |
| 30 | **Uncertainty-aware token budgeting** | 2 | 📋 Planned | Allocate token budget inversely to confidence; contested atoms get more tokens where reasoning matters most |
| 31 | **Query decomposition** | 2 | 📋 Planned | Split compound queries into independent sub-queries; run each through full L3 pipeline; stitch with provenance labels; closes HyDE failure mode on multi-part questions |
| 32 | **Novelty-biased search mode** | 2 | 📋 Planned | `discovery=True` flag; score = relevance × (1 − prior access frequency); pure `access_log` signal; no schema change |
| 33 | **Access gap surfacing** | 2 | 📋 Planned | Return cardinality + domain hint when relevant atoms are blocked by `role_mask`; turns ACL into a visible boundary, not a silent wall |
| 34 | **Cross-agent collaborative filtering** | 2 | 📋 Planned | Boost atoms co-accessed by similar-`role_mask` agents on similar queries; personalizes retrieval with no schema change |
| — | _**Search Intelligence — Phase 3**_ | — | — | — |
| 35 | **Causal chain construction** | 3 | 📋 Planned | Walk `causal` links backward for explanation, forward for consequences; returns directed reasoning chain, not flat list; answers "why" queries structurally |
| 36 | **Belief propagation through link graph** | 3 | 📋 Planned | Confidence propagates transitively via `confirms` chains (with decay); `contradicts` against high-confidence atoms penalizes skepticism; turns link graph into trust network |
| 37 | **Ghost atoms — temporal extrapolation** | 3 | 📋 Planned | Detect metric time-series at query time; synthesize projected atom for missing period; tagged `kind=projection, confidence=derived`; generated on-the-fly, never stored |
| 38 | **Counterfactual time travel search** | 3 | 📋 Planned | Extends `?as_of=` to return then-vs-now result diff: flipped confidences, new contradictions, superseded facts; active knowledge state comparison |
| 39 | **Contrastive search** | 3 | 📋 Planned | `find_similar_to(X) − find_similar_to(Y)` query mode; embed both, compute `X − Y` direction, search along it; answers "how is X different from Y?" without new infrastructure |
| 40 | **Emergent concept flagging** | 3 | 📋 Planned | When top results cluster tightly but share no explicit links, flag unnamed emergent pattern; pure topology signal, no LLM needed |
| 41 | **Semantic temperature** | 3 | 📋 Planned | `temperature` param (0.0–1.0) on query endpoint; low = tight canonical filters, high precision; high = relaxed filters, unexpected cross-domain connections surface |
| 42 | **Inverse retrieval** | 3 | 📋 Planned | Given atom ID, find natural-language queries that would surface it; enables gap analysis ("is this atom discoverable?") and auto-FAQ generation |
| 43 | **Cross-role insight bridging** | 3 | 📋 Planned | Surface to agent when elevated-role atoms exist for their query topic; domain hints only, no content leaked; builds awareness of cross-role knowledge silos |
| 16 | **Push Gateway + subscription model** | 3 | 📋 Planned | Real-time context delivery; needed for agentic workflows at scale |
| 17 | **Confluence / Slack / Jira connectors** | 3 | 📋 Planned | Expands TAM; enterprise customers need connectors before they can adopt |
| 18 | **OpenTelemetry + Prometheus** | 3 | 📋 Planned | Enterprise procurement requirement; often a blocker |
| 19 | **Multi-tenant deployment** | 4 | 📋 Planned | Required for SaaS; can serve early customers single-tenant |
| 20 | **Python + TypeScript SDKs** | 4 | 📋 Planned | Developer experience; needed for self-serve adoption |
| 21 | **SOC 2 / HIPAA readiness** | business | 📋 Planned | Required for FinServ / Healthcare verticals |

---

## Phase 1: MVP ✅ (Complete - L3-Only)

See [MVP.md](./MVP.md) for full scope.

**Core deliverables:**

- ✅ Context Atom data model (replaces chunks + entities)
- ✅ Compiler pipeline: extract → embed → link+tag (parallel) → index → cross-link → consolidate (8 stages, synchronous)
- ✅ Cross-source relationship linking — domain-aware candidate selection (DOMAIN_GROUPS) + LLM link inference, similarity-gated (cosine ≥ 0.5)
- ✅ Stage 8 Consolidator — near-duplicate detection (cosine ≥ 0.85) + LLM classification: `confirms`, `subsumes`, `supersedes`, `contradicts`; provenance preserved; replaces silent Tier 2 discard
- ✅ Atom versioning — `atom_versions` append-only ledger; `valid_from`/`valid_until` on atoms; foundation for temporal queries
- ✅ Multi-hypothesis search (HyDE, k=3 diverse declarative hypotheses) + Reciprocal Rank Fusion
- ✅ Canonical pre-filters — `canonical_subject` + `canonical_period` as indexed SQL columns; bidirectional ILIKE matching
- ✅ Period + subject normalisation — consistent format at write and query time (`normalize_period`, `normalize_subject`)
- ✅ Optional LLM re-ranker (`deep_rerank=True`) — second pass scores candidates 1–10; falls back gracefully
- ✅ L3-only serving: multi-hypothesis pgvector search with bitmask pre-filtering (~100–200ms smart, ~50ms fast path)
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

### Temporal Knowledge Layer

- ✅ **Atom versioning** — `atom_versions` append-only ledger; every state transition written with `valid_from`/`valid_until`; `reason` field (`initial` | `confirmed` | `superseded`); enables "what did the system believe at time T?"
- ✅ **Time-bounded fact modeling** — `valid_from` / `valid_until` fields on `Atom`; `is_superseded` flag; `superseded_by` FK; atoms with `is_superseded=True` excluded from live L3 search
- ✅ **`supersedes` / `contradicts` / `confirms` link types** — Stage 8 consolidator emits typed links; `contradicts` pairs are flagged for review; `confirms` boosts `confidence`
- [ ] **Temporal query API** — `?as_of=<ISO-timestamp>` on `/v1/context/query`; data already in `atom_versions`; only the API endpoint remains to be built
- [ ] **State-diff events on re-ingest** — structured state-change events emitted from consolidator to event bus; lays groundwork for Phase 3 streaming
- [ ] **Context Diff API** — `GET /v1/context/query?since=version:42` returns delta since last fetch; groundwork (versioning, valid_from) now done

### Serving Enhancements

- ✅ **Multi-hypothesis HyDE search** — k=3 diverse hypotheses, no kind classification, eliminates phrasing mismatch
- ✅ **RRF fusion** — atoms appearing across multiple hypothesis shortlists surface higher; deduplicates by atom_id
- ✅ **Canonical pre-filters** — `canonical_subject` + `canonical_period` indexed SQL columns; bidirectional ILIKE pre-filter
- ✅ **Optional LLM re-ranker** — `deep_rerank=True` flag; 1–10 score per candidate; fallback to heuristic order
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

- ✅ **LLM-powered atomization + distillation** — merged into a single LLM call per chunk (Stage 1+2 extract); parallel link+tag (Stages 4+5)
- ✅ **Contradiction detection** — Stage 8 consolidator emits `contradicts` links when atoms disagree
- [ ] **Async compiler workers** — decouple ingestion from HTTP request lifecycle, queue-based processing
- [ ] **Sliding window ingestion** — replace fixed-chunk atomization with overlapping windows (e.g. 50% overlap) to preserve relationship context at chunk boundaries; compiler-only change, no serving impact
- [ ] **Incremental recompilation** — track source content hashes, only recompile changed atoms
- [ ] **Multi-format connectors** — Markdown, DOCX, HTML, CSV ingestion

### Search Intelligence _(new — expanded retrieval capabilities)_

#### Priority A — Quick Wins (schema-free, high immediate impact)

- ✅ **BM25 + dense hybrid search** — PostgreSQL `tsvector` full-text search fused into the same RRF pipeline alongside pgvector hypothesis searches; GIN index added; subject canonical pre-filter removed (BM25 covers it as a soft signal instead of a hard gate)
- [ ] **Kind-aware freshness decay** — replace global half-life (~139 days) with per-kind decay rates inferred from `atom_versions` supersedure patterns; `metric` atoms decay in weeks, `procedure` atoms in years; single formula change in `l3_search.py`
- [ ] **Temporal velocity scoring** — detect "hot" topics from churn in `atom_versions`; surface velocity signal at query time: *"8 updates in 30 days — treat with caution"*; inversely, stable atoms get a "settled knowledge" boost; pure read signal, no schema change
- [ ] **Graph-centrality atom boosting** — pre-compute nightly hub scores (in-degree across diverse link types and domains); fold into heuristic re-scorer in `l3_search.py`; atoms that are topologically load-bearing outrank isolated newcomers at equal cosine distance
- [ ] **Minimum coverage set** — after RRF scoring, evict near-semantic-duplicate atoms from the result set (cosine > 0.9 between any two results); keep highest-confidence of each duplicate pair; reduces token waste with no precision loss

#### Priority B — Serving Layer Additions (changes to `router.py` / `l3_search.py`)

- [ ] **Contradiction adjudication at query time** — when result set contains atoms with active `contradicts` links between them, route the conflicted pair to the LLM re-ranker with a targeted prompt; return winner surfaced, loser flagged with confidence delta shown; turns existing `contradicts` data into an active query feature
- ✅ **Kind-aware query intent + intent-adaptive routing** — `process_query()` classifies query into atom kinds (metric/event/decision/procedure/fact) and generates kind-flavored HyDE hypotheses; `_apply_intent_routing()` in `router.py` reads the classified kinds and auto-configures `deep_rerank`, `top_k_factor`, `min_relevance`, and `strip_period` per-kind via `_INTENT_CONFIG`
- [ ] **Knowledge gap / negative space detection** — after search, score KB coverage as `high / partial / gap` based on result confidence distribution, supersedure proximity, and `contradicts` density; return as a coverage signal alongside atoms; agents know when operating on thin evidence
- [ ] **Uncertainty-aware token budgeting** — allocate token budget inversely to atom confidence: high-confidence settled atoms get fewer tokens, contested/low-confidence/recently-superseded atoms get more; agents receive richer context where reasoning matters most
- [ ] **Query decomposition for compound queries** — detect compound structure in incoming query (LLM classifier step before `process_query()`); split into sub-queries; run each through full L3 pipeline independently; stitch and deduplicate before token trim; each sub-result gets a provenance label; closes HyDE failure mode on multi-part questions

#### Priority C — Agent Intelligence (signals from `access_log` + agent profiles)

- [ ] **Novelty-biased search mode** — `discovery=True` flag on query endpoint; per-agent score = `relevance × (1 − prior_access_frequency)`; surfaces highly relevant atoms the agent has never retrieved; pure `access_log` signal, no schema change
- [ ] **Access gap surfacing** — after search, query whether additional relevant atoms exist that the agent's `role_mask` blocks; return cardinality + domain hints only (no content leaked); agents see what they're missing; turns access control from a silent wall into a visible boundary
- [ ] **Cross-agent collaborative filtering** — boost atoms historically co-accessed by agents with similar `role_mask` profiles on similar queries; item-based collaborative filtering on `access_log`; personalizes search results with no schema change

---

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

### Search Intelligence — Advanced _(builds on Phase 2 Search Intelligence)_

- [ ] **Causal chain construction** — walk `causal` links backward from matched atoms to surface upstream causes; walk forward for consequences; return a directed reasoning chain alongside the flat result list; query *"why did X happen"* returns a structured explanation, not just facts
- [ ] **Belief propagation through link graph** — make confidence network-propagated: `confirms` chains boost transitively with per-hop decay, `contradicts` edges against high-confidence atoms impose skepticism penalties; runs as a nightly graph pass; turns typed link edges into a living trust network
- [ ] **Ghost atoms — dynamic temporal extrapolation** — detect metric atoms forming a time series at query time (Q1/Q2/Q3 data); synthesize a projected atom for the missing period from the detected trend; returned tagged `kind=projection, confidence=derived`; generated on-the-fly, never written to the atom store
- [ ] **Counterfactual time travel search** — extend `?as_of=` to return *two* result sets (knowledge state then vs. now) with a structural diff: atoms that flipped confidence, newly emerged contradictions, superseded high-confidence facts; active knowledge comparison, not just point-in-time retrieval
- [ ] **Contrastive search** — `find_similar_to(X) − find_similar_to(Y)` query mode; embed both X and Y, compute contrastive direction `X − Y` in embedding space, search along that vector; answers *"how is our Q3 strategy different from Q2?"* with no infrastructure change
- [ ] **Emergent concept flagging** — when top results cluster tightly in embedding space but share no explicit `links[]` between them, flag as an unnamed emergent concept: *"these atoms describe a pattern not explicitly captured in the knowledge graph"*; pure topology signal, no LLM needed
- [ ] **Semantic temperature** — `temperature` parameter (0.0–1.0) on the query endpoint; low = tight canonical filters, small cosine radius, high precision; high = filters relaxed, hypotheses drift further from the literal query, unexpected cross-domain connections surface; gives callers a knob between *"give me exactly this"* and *"surprise me with what's related"*
- [ ] **Inverse retrieval** — given an atom ID, find natural-language queries that would best surface it; embed atom content, match against query log; answers *"what question does this atom answer?"*; surfaces undiscoverable atoms and enables auto-FAQ generation from the knowledge base
- [ ] **Cross-role insight bridging** — identify which elevated `role_mask` profiles historically retrieve high-confidence atoms relevant to a given query topic; surface to current agent: *"relevant knowledge exists in [domain] requiring elevated access"*; domain hints only, no content leaked; builds awareness of cross-role knowledge silos without breaching ACL

---

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
- [ ] **Query trajectory prediction** — model an agent's session queries as a path through embedding space; detect convergence (agent homing in on a topic) vs. divergence (exploration); predict next query, pre-warm results, and surface contextually adjacent atoms before they're asked for
- [ ] **Atom authority scoring** — multi-factor authority metric: in-degree across link types, source trust rank, survival count through consolidation challenges, confirmation-to-contradiction ratio; replaces flat confidence as the primary ranking signal for high-stakes retrieval
- [ ] **Semantic momentum** — detect when a concept's embedding centroid in a domain is drifting over successive ingestions; surface at query time: *"the knowledge base's understanding of 'customer acquisition' has shifted since Q2"*; flags knowledge in transition vs. settled knowledge

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

_Last updated: 2026-04-27_
