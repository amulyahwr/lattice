# Lattice — Architecture Document

> Enterprise Context Engine: Right context. Right time. Right agent.

**Version:** 0.1.0-draft
**Date:** 2026-04-25
**Author:** Amulya Gupta + Optimus Prime

---

## Table of Contents

1. [Overview](#1-overview)
2. [Design Principles](#2-design-principles)
3. [System Architecture](#3-system-architecture)
4. [Data Model](#4-data-model)
5. [Ingestion Pipeline — The Context Compiler](#5-ingestion-pipeline--the-context-compiler)
6. [The Lattice Structure — Context Frames](#6-the-lattice-structure--context-frames)
7. [Serving Layer — Context Mesh](#7-serving-layer--context-mesh)
8. [Agent Interface Protocol](#8-agent-interface-protocol)
9. [Access Control & Governance](#9-access-control--governance)
10. [Observability & Audit](#10-observability--audit)
11. [Deployment Topology](#11-deployment-topology)
12. [Performance Targets](#12-performance-targets)
13. [Open Questions](#13-open-questions)

---

## 1. Overview

Lattice is an enterprise context broker. It sits between an organization's knowledge sources and its AI agents, providing intelligent, low-latency, access-controlled context delivery.

Lattice does **not** own data. It connects to where data already lives — Confluence, Slack, databases, APIs, document stores, CRMs — and compiles it into optimized representations that agents can consume at high throughput.

### What Lattice Is Not

- Not a vector database (though it uses embeddings internally)
- Not a RAG pipeline (though it subsumes that function)
- Not a knowledge graph product (though it maintains graph relationships)
- Not an agent framework (it's agent-agnostic)

### The Core Insight

Traditional context retrieval does expensive semantic work **at query time**. Lattice inverts this: expensive work happens **at ingestion**, and serving is reduced to cache lookups and bitmask operations.

Think CDN, not database.

### Data Residency — Broker, Not Data Lake

Lattice is a **context broker and cache layer**, not a second data lake. The source of truth stays where it already lives.

**What Lattice stores:**
- **Atoms** — distilled, token-efficient summaries (the "index cards," not photocopies)
- **Embeddings** — vector representations for semantic matching
- **Metadata** — access masks, domain tags, atom links, source lineage, timestamps
- **SourceRef pointers** — deep links back to the original document in the source system

**What Lattice does NOT store (enterprise mode):**
- Full original documents
- Raw source content
- Copies of databases or message archives

The original data stays in Confluence, SharePoint, Slack, S3, databases — wherever the enterprise already manages it. Lattice only holds the compiled intelligence layer on top.

**Why this matters:**

| Concern | How Lattice Addresses It |
|---------|-------------------------|
| **Security** | No second copy of sensitive data to protect. Atoms are distilled summaries, not full documents. |
| **Compliance (GDPR/CCPA)** | Data doesn't move regions. Source stays in its original residency. Lattice can run in-region with only metadata. |
| **Data ownership** | Enterprise retains full ownership. Lattice is a read-only consumer with a compiled cache. |
| **Freshness** | Lattice re-compiles from the live source on change events. No stale copies drifting out of sync. |
| **Right to deletion** | Delete at source → Lattice tombstones affected atoms within SLA. No orphaned copies. |

**Deployment spectrum:**

```
MVP (simple):       Source → Lattice stores atoms + raw text locally
                     Good for demos and small deployments.

Enterprise (broker): Source stays in customer systems
                     Lattice stores ONLY atoms + embeddings + metadata + SourceRefs
                     Raw content fetched on-demand via connector if needed.

Air-gapped:          Everything on-prem, Lattice + sources in same network
                     No data leaves the perimeter.
```

The connector model (Section 5) enables this: connectors know how to read from sources and how to resolve a SourceRef back to the original content when an agent or auditor needs full provenance.

```
┌─────────────────────────────────────────────────────────┐
│                     ENTERPRISE                          │
│                                                         │
│  Confluence  Slack  Jira  Salesforce  DBs  APIs  Mail   │
│      │         │      │       │        │     │     │    │
└──────┼─────────┼──────┼───────┼────────┼─────┼─────┼────┘
       └─────────┴──────┴───────┴────────┴─────┴─────┘
                            │
                    ┌───────▼────────┐
                    │   CONNECTORS   │  ← Source adapters
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │    COMPILER    │  ← Atomize, distill, embed, link
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │    LATTICE     │  ← Frame assembly, lattice structure
                    │     CORE       │
                    └───────┬────────┘
                            │
                    ┌───────▼────────┐
                    │  CONTEXT MESH  │  ← Tiered cache, push/pull serving
                    └───────┬────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
        ┌─────▼─────┐ ┌────▼────┐ ┌──────▼──────┐
        │  Agent A   │ │ Agent B │ │   Agent N   │
        │  (Sales)   │ │ (Eng)   │ │   (Custom)  │
        └───────────┘ └─────────┘ └─────────────┘
```

---

## 2. Design Principles

### P1: Compile Once, Serve Many
The ingestion pipeline does heavy lifting — NLP, summarization, relationship extraction, embedding. The serving path does lookups and filtering. This separation is what enables low latency at scale.

### P2: Atoms, Not Documents
The fundamental unit is a **Context Atom** — the smallest meaningful piece of context. Not a document. Not a chunk. A discrete fact, decision, relationship, or metric with full metadata. Atoms compose into frames. Frames compose into lattices.

### P3: Push Over Pull
Agents shouldn't poll for context changes. When context updates, Lattice pushes deltas to subscribed agents. Event-driven, not request-driven, for known context domains.

### P4: Access Control Is Not Aftermarket
Every atom carries access tags from the moment it's created. Filtering is a bitmask AND, not a post-query policy check. Security is in the data structure, not bolted on top.

### P5: Agent-Agnostic Protocol
Lattice exposes a standard protocol (gRPC + REST + streaming). No vendor lock-in. Works with OpenAI, Anthropic, open-source, or custom agent frameworks.

### P6: Token Efficiency
Agents pay per token. Lattice delivers pre-distilled, compressed context — not raw documents. Every atom includes a token-efficient summary alongside source references.

---

## 3. System Architecture

### Component Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        LATTICE ENGINE                            │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ CONNECTORS  │  │   COMPILER   │  │     LATTICE CORE       │  │
│  │             │  │              │  │                        │  │
│  │ - Confluence│  │ - Atomizer   │  │ - Atom Store           │  │
│  │ - Slack     │  │ - Distiller  │  │ - Frame Builder        │  │
│  │ - Jira      │  │ - Embedder   │  │ - Lattice Index        │  │
│  │ - Database  │  │ - Linker     │  │ - Subscription Manager │  │
│  │ - API       │  │ - Tagger     │  │ - Profile Registry     │  │
│  │ - Email     │  │              │  │                        │  │
│  │ - Custom    │  │              │  │                        │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────┬────────────┘  │
│         │                │                      │               │
│         └───────►────────┘                      │               │
│                  │                              │               │
│           ┌──────▼──────────────────────────────▼────────┐      │
│           │              EVENT BUS (Internal)             │      │
│           │     Atom events, frame invalidations,        │      │
│           │     subscription updates, source changes     │      │
│           └──────────────────────┬───────────────────────┘      │
│                                  │                              │
│  ┌───────────────────────────────▼───────────────────────────┐  │
│  │                     CONTEXT MESH                          │  │
│  │                                                           │  │
│  │  ┌─────┐  ┌─────┐  ┌──────────────┐  ┌───────────────┐   │  │
│  │  │ L1  │  │ L2  │  │     L3       │  │      L4       │   │  │
│  │  │Cache│  │Cache│  │  Dist Index  │  │  Cold Search  │   │  │
│  │  └─────┘  └─────┘  └──────────────┘  └───────────────┘   │  │
│  │                                                           │  │
│  │  ┌────────────────┐  ┌─────────────┐  ┌──────────────┐   │  │
│  │  │ Query Router   │  │ Delta Engine│  │ Push Gateway  │   │  │
│  │  └────────────────┘  └─────────────┘  └──────────────┘   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    CONTROL PLANE                          │  │
│  │                                                           │  │
│  │  ┌──────────┐  ┌──────────────┐  ┌────────────────────┐  │  │
│  │  │ Policies │  │ Audit Logger │  │ Metrics / Traces   │  │  │
│  │  └──────────┘  └──────────────┘  └────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  AGENT INTERFACE   │
                    │  gRPC / REST /     │
                    │  Streaming / SDK   │
                    └───────────────────┘
```

---

## 4. Data Model

### 4.1 Context Atom

The fundamental unit. Every piece of context in Lattice is an atom.

```
Atom {
  id:           uuid
  content:      string          // Pre-distilled, token-efficient text
  raw_ref:      SourceRef       // Pointer to original source (never stored inline)
  
  // Embeddings (dual representation)
  dense_vec:    float[768]      // Dense embedding for L3/L4 semantic search
  sparse_vec:   bit[2048]       // Sparse binary vector for L1/L2 fast matching
  
  // Metadata
  kind:         enum            // fact | decision | metric | relationship | event | procedure
  domain:       string[]        // ["sales", "emea", "q2-2026"]
  freshness:    timestamp       // When the underlying source was last verified
  confidence:   float           // Compiler's confidence in distillation accuracy
  ttl:          duration        // How long before this atom must be re-verified
  
  // Access Control
  access_mask:  bit[256]        // Bitmask — roles/groups that can see this atom
  classification: enum          // public | internal | confidential | restricted
  
  // Graph
  links: [
    { target: atom_id, relation: enum }  // causal | temporal | hierarchical | topical | contradicts
  ]
  
  // Lineage
  source:       SourceRef       // Which connector produced this
  compiled_at:  timestamp       // When the compiler last processed this
  version:      int             // Incremented on recompilation
}
```

### 4.2 Source Reference

```
SourceRef {
  connector:    string          // "confluence", "slack", "jira", etc.
  external_id:  string          // ID in the source system
  url:          string          // Deep link back to source
  snapshot_hash: string         // Hash of source content at compile time
}
```

### 4.3 Context Frame

A pre-assembled bundle of atoms likely needed together.

```
Frame {
  id:           uuid
  name:         string          // Human-readable label
  atoms:        atom_id[]       // Ordered list of atom references
  
  // Lattice position
  parent_frames: frame_id[]    // More general frames above this one
  child_frames:  frame_id[]    // More specific frames below this one
  
  // Pre-computed serving data
  token_count:  int             // Total tokens if all atoms are serialized
  compressed:   bytes           // Pre-serialized, compressed payload
  access_mask:  bit[256]        // Union of all atom access masks (for fast pre-filter)
  
  // Lifecycle
  last_accessed: timestamp
  access_count:  int
  warm:          boolean        // Currently in L2 cache
}
```

### 4.4 Agent Profile

```
AgentProfile {
  id:           uuid
  name:         string          // "sales-assistant", "eng-oncall-bot"
  
  // Identity & Access
  role_mask:    bit[256]        // What this agent can see
  org_unit:     string          // Department / team
  
  // Context preferences
  domains:      string[]        // Topics this agent cares about
  max_tokens:   int             // Token budget per context fetch
  freshness_req: duration       // How fresh context must be (e.g., "5m" for real-time, "24h" for reports)
  
  // Working set
  subscribed_frames: frame_id[] // Frames this agent is subscribed to (push updates)
  l1_atoms:     atom_id[]       // Currently hot in L1 for this agent
  
  // Stats
  avg_latency:  float           // Running average of context serve latency
  cache_hit_rate: float         // L1+L2 hit rate
}
```

### 4.5 Entity-Relationship Overview

```
                    ┌──────────────┐
                    │   Source     │
                    │   System    │
                    └──────┬───────┘
                           │ produces
                           ▼
┌──────────┐      ┌───────────────┐      ┌──────────────┐
│  Agent   │◄────►│  Context Atom │◄────►│ Context Atom │
│ Profile  │ uses └───────┬───────┘ links└──────────────┘
└──────┬───┘              │
       │           groups into
       │                  │
       │           ┌──────▼──────┐
       └──────────►│   Context   │
        subscribes │    Frame    │
                   └──────┬──────┘
                          │ ordered in
                          ▼
                   ┌─────────────┐
                   │   Lattice   │
                   │  Hierarchy  │
                   └─────────────┘
```

---

## 5. Ingestion Pipeline — The Context Compiler

The compiler transforms raw enterprise data into optimized atoms. This is where the heavy compute happens — **offline, asynchronous, never on the serving path.**

### 5.1 Pipeline Stages

```
Source Data
    │
    ▼
┌─────────────────┐
│  1. EXTRACTION   │  Connectors pull raw content + metadata
│     (Connector)  │  Change detection: only process deltas
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. ATOMIZATION  │  Break content into atomic units
│                  │  One fact/decision/metric per atom
│                  │  Deduplication against existing atoms
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. DISTILLATION │  Summarize each atom into token-efficient form
│     (LLM)       │  Strip boilerplate, keep signal
│                  │  Generate both human-readable + structured forms
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. EMBEDDING    │  Generate dual representations:
│                  │  - Dense vector (768-dim) for semantic search
│                  │  - Sparse binary vector (2048-bit) for fast matching
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. LINKING      │  Identify relationships between atoms
│     (LLM + ML)  │  Causal, temporal, hierarchical, topical
│                  │  Contradiction detection
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  6. TAGGING      │  Apply access masks from source permissions
│                  │  Domain classification
│                  │  Freshness + TTL assignment
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  7. INDEXING     │  Write to Atom Store
│                  │  Update affected frames
│                  │  Emit events to Event Bus
└─────────────────┘
```

### 5.2 Connector Model

Each connector implements a standard interface:

```
Connector {
  // Initial sync
  full_scan() → RawDocument[]
  
  // Incremental sync (preferred)
  changes_since(cursor) → ChangeSet
  
  // Webhook receiver (best)
  on_webhook(event) → RawDocument[]
  
  // Permission mapping
  get_permissions(document_id) → AccessPolicy
}
```

**Priority connectors (v1):**
- Document stores: Confluence, Notion, Google Docs, SharePoint
- Communication: Slack, Teams, Email
- Project management: Jira, Linear, Asana
- Data: PostgreSQL, MySQL, REST APIs
- Code: GitHub (READMEs, docs, PR context)

### 5.3 Incremental Compilation

Full recompilation is expensive. Lattice tracks source content hashes and only recompiles when sources change:

```
on source_change(doc):
  old_hash = atom_store.get_hash(doc.source_ref)
  new_hash = hash(doc.content)
  
  if old_hash == new_hash:
    return  // No change
  
  old_atoms = atom_store.get_by_source(doc.source_ref)
  new_atoms = compiler.compile(doc)
  
  diff = compute_diff(old_atoms, new_atoms)
  
  for atom in diff.added:    atom_store.insert(atom)
  for atom in diff.removed:  atom_store.tombstone(atom)
  for atom in diff.modified: atom_store.update(atom)
  
  // Cascade: invalidate affected frames
  affected_frames = frame_builder.get_affected(diff)
  for frame in affected_frames:
    frame_builder.recompute(frame)
    event_bus.emit(FrameUpdated { frame, diff })
```

---

## 6. The Lattice Structure — Context Frames

### 6.1 Frame Assembly

Frames are pre-computed bundles. They're built by analyzing:

1. **Co-access patterns** — Atoms frequently requested together get grouped
2. **Graph proximity** — Linked atoms form natural frames
3. **Domain clustering** — Atoms in the same domain/subdomain
4. **Temporal locality** — Recent atoms about the same topic

```
Frame Assembly Algorithm:
  
  1. Cluster atoms by domain + graph proximity
  2. For each cluster:
     a. Create a frame with constituent atoms
     b. Order atoms by relevance score (most important first)
     c. Pre-serialize and compress the frame payload
     d. Compute aggregate access mask (union of atom masks)
  3. Build lattice edges:
     a. Frame A is parent of Frame B if A's atoms ⊃ B's atoms
     b. Or if A represents a broader domain containing B's domain
  4. Identify hot frames from agent access patterns
  5. Pre-warm hot frames into L2 cache
```

### 6.2 Lattice Hierarchy

The lattice is a partially ordered set where:
- **Join (∨)**: Combine two frames → union of their atoms (generalization)
- **Meet (∧)**: Intersect two frames → shared atoms (specialization)

```
                    ┌─────────────────────┐
                    │   Enterprise Root   │
                    │  (all public atoms) │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
     ┌────────▼──────┐ ┌──────▼───────┐ ┌──────▼──────┐
     │    Sales      │ │ Engineering  │ │     HR      │
     │   Domain      │ │   Domain     │ │   Domain    │
     └───┬──────┬────┘ └──────┬───────┘ └──┬──────┬───┘
         │      │             │            │      │
    ┌────▼─┐ ┌─▼────┐  ┌─────▼────┐  ┌───▼──┐ ┌─▼─────┐
    │ EMEA │ │  NA  │  │ Platform │  │Hiring│ │ Comp  │
    └──┬───┘ └──┬───┘  └────┬─────┘  └──┬───┘ └───────┘
       │        │           │            │
  ┌────▼────┐   │     ┌─────▼─────┐  ┌──▼──────────┐
  │ Q2 EMEA │   │     │  Infra    │  │ Eng Hiring  │
  │ Pipeline│   │     │  Oncall   │  │  Pipeline   │
  └─────────┘   │     └───────────┘  └─────────────┘
                │
          ┌─────▼──────┐
          │ NA Enterprise│
          │ Accounts     │
          └──────────────┘
```

### 6.3 Dynamic Frame Operations

When an agent query doesn't match a pre-computed frame exactly, Lattice performs lattice operations:

```
query: "Q2 sales pipeline for enterprise accounts in EMEA"

1. Find nearest frames:
   - "Q2 EMEA Pipeline" (match: domain=sales, region=emea, period=q2)
   - "NA Enterprise Accounts" (match: segment=enterprise)

2. Lattice meet operation:
   result = meet("Q2 EMEA Pipeline", "NA Enterprise Accounts")
   → Atoms that exist in BOTH frames (enterprise + EMEA + Q2)

3. If meet is too narrow, join parent frames:
   result = join("EMEA", "Enterprise Accounts") filtered by Q2

4. Cache the result as a new dynamic frame if access count > threshold
```

---

## 7. Serving Layer — Context Mesh

### 7.1 Cache Tiers

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  L1: Agent Session Cache              Latency: < 1ms   │
│  ┌─────────────────────────────────┐                    │
│  │ Per-agent in-memory atom set    │  Hit rate: ~40%    │
│  │ Recent queries + active frames  │  Size: ~1000 atoms │
│  │ SDR (sparse vectors) for match  │  per agent         │
│  └─────────────────────────────────┘                    │
│                    │ miss                                │
│                    ▼                                     │
│  L2: Shared Frame Cache              Latency: < 5ms    │
│  ┌─────────────────────────────────┐                    │
│  │ Pre-warmed frames (compressed)  │  Hit rate: ~50%    │
│  │ Shared across agents with same  │  Size: ~100K frames│
│  │ domain. Bitmask access filter.  │                    │
│  └─────────────────────────────────┘                    │
│                    │ miss                                │
│                    ▼                                     │
│  L3: Distributed Lattice Index       Latency: < 50ms   │
│  ┌─────────────────────────────────┐                    │
│  │ Full lattice traversal          │  Hit rate: ~9%     │
│  │ Dense vector ANN search         │                    │
│  │ Frame assembly on the fly       │                    │
│  └─────────────────────────────────┘                    │
│                    │ miss                                │
│                    ▼                                     │
│  L4: Cold Semantic Search            Latency: < 200ms  │
│  ┌─────────────────────────────────┐                    │
│  │ Full corpus embedding search    │  Hit rate: ~1%     │
│  │ May trigger recompilation       │                    │
│  │ Results cached as new frames    │                    │
│  └─────────────────────────────────┘                    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Query Router

Every context query goes through the router, which decides the cheapest path:

```
route(query, agent_profile):
  
  // Step 1: Check L1 — agent's session cache
  l1_result = l1.match(query.sparse_vec, agent.l1_atoms)
  if l1_result.score > THRESHOLD_L1:
    return l1_result.atoms  // < 1ms
  
  // Step 2: Check L2 — find matching pre-warmed frame
  candidate_frames = l2.find_frames(query, agent.role_mask)
  if candidate_frames:
    best_frame = rank_frames(candidate_frames, query)
    atoms = best_frame.atoms.filter(agent.role_mask)
    l1.promote(atoms, agent)  // Warm L1 for next time
    return atoms  // < 5ms
  
  // Step 3: L3 — lattice traversal
  lattice_result = l3.traverse(query, agent.role_mask)
  if lattice_result:
    frame = frame_builder.assemble(lattice_result)
    l2.cache(frame)  // Warm L2
    l1.promote(frame.atoms, agent)
    return frame.atoms  // < 50ms
  
  // Step 4: L4 — cold search
  search_result = l4.semantic_search(query.dense_vec, agent.role_mask)
  atoms = compiler.quick_distill(search_result)  // Lighter distillation
  frame = frame_builder.assemble(atoms)
  l2.cache(frame)
  return atoms  // < 200ms
```

### 7.3 Delta Engine

When an agent requests context it recently asked for, Lattice sends only what changed:

```
Agent → Lattice:  GET /context?topic=q2-pipeline&since=version:42
Lattice → Agent:  {
  "base_version": 42,
  "current_version": 44,
  "delta": {
    "added": [ atom_55, atom_56 ],
    "removed": [ atom_31 ],
    "modified": [ { "id": atom_22, "content": "..." } ]
  },
  "token_cost": 340  // Only 340 tokens for the delta vs 4200 for full frame
}
```

### 7.4 Push Gateway

Agents subscribe to frames or domains. When context changes, Lattice pushes:

```
// Agent subscribes at connection time
Agent → Lattice:  SUBSCRIBE frames=["q2-emea-pipeline", "eng-oncall"]

// When frame updates (from compiler pipeline)
Lattice → Agent:  PUSH {
  "frame": "q2-emea-pipeline",
  "event": "atom_updated",
  "delta": { ... },
  "priority": "normal"  // or "urgent" for high-impact changes
}
```

**Transport options:**
- **gRPC streaming** — lowest latency, best for long-lived agent processes
- **WebSocket** — browser-based agents / dashboards
- **Webhook** — serverless / ephemeral agents
- **Message queue** — high-volume enterprise integrations (Kafka, SQS)

---

## 8. Agent Interface Protocol

### 8.1 Core API

```
// Pull: Get context for a query
POST /v1/context/query
{
  "query": "What's the current Q2 pipeline for EMEA enterprise?",
  "agent_profile_id": "sales-assistant-01",
  "max_tokens": 2000,
  "freshness": "1h",          // Optional: how fresh
  "since_version": 42,        // Optional: delta mode
  "format": "distilled"       // distilled | raw | structured
}

Response:
{
  "atoms": [ ... ],
  "frame_id": "fr_abc123",
  "version": 44,
  "total_tokens": 1850,
  "latency_ms": 3,
  "cache_tier": "L2",
  "access_filtered": 2        // 2 atoms hidden due to access control
}
```

```
// Push: Subscribe to context updates
POST /v1/context/subscribe
{
  "agent_profile_id": "sales-assistant-01",
  "frames": ["q2-emea-pipeline"],
  "domains": ["sales.emea"],
  "transport": "grpc-stream"
}
```

```
// Register: Create/update agent profile
PUT /v1/agents/{agent_id}/profile
{
  "name": "sales-assistant-01",
  "role": "sales-rep",
  "domains": ["sales", "crm"],
  "max_tokens": 4000,
  "freshness_req": "15m"
}
```

```
// Feedback: Tell Lattice what was useful
POST /v1/context/feedback
{
  "query_id": "qr_xyz",
  "useful_atoms": ["atom_1", "atom_3"],
  "irrelevant_atoms": ["atom_7"],
  "missing_context": "Needed competitor pricing info"
}
```

### 8.2 SDK (Thin Client)

```python
from lattice import LatticeClient

client = LatticeClient(
    endpoint="lattice.internal:9090",
    agent_profile="sales-assistant-01"
)

# Pull context
ctx = client.query(
    "Q2 EMEA pipeline status",
    max_tokens=2000
)

for atom in ctx.atoms:
    print(f"[{atom.kind}] {atom.content}")
    # [metric] EMEA Q2 pipeline: $4.2M (up 12% from Q1)
    # [fact] Top 3 deals: Acme ($800K), Globex ($650K), Initech ($500K)
    # [decision] EMEA team expanding enterprise focus per Apr board meeting

# Subscribe to updates
async for update in client.subscribe(domains=["sales.emea"]):
    print(f"Context changed: {update.delta}")
```

---

## 9. Access Control & Governance

### 9.1 Bitmask Access Model

Every atom and every agent carries a bitmask. Access check is a single AND operation:

```
can_access(agent, atom):
  return (agent.role_mask & atom.access_mask) != 0
```

This runs in **nanoseconds**, not milliseconds. No policy engine evaluation on the hot path.

### 9.2 Bitmask Assignment

```
Bit allocation (256 bits):
  Bits   0-31:   Organization roles (admin, manager, employee, contractor, ...)
  Bits  32-63:   Departments (sales, engineering, hr, finance, legal, ...)
  Bits  64-95:   Teams (within departments)
  Bits  96-127:  Projects / initiatives
  Bits 128-159:  Classification levels
  Bits 160-255:  Custom / reserved
```

Masks are computed at compile time from source system permissions:
- Confluence space permissions → department + team bits
- Jira project roles → project bits
- Slack channel membership → team bits
- HR system → classification level bits

### 9.3 Governance Layer

```
AccessPolicy {
  // Compile-time policies (baked into masks)
  role_mappings:    map[source_permission → bitmask]
  classification_rules: [
    { pattern: "salary|compensation", level: "restricted" },
    { pattern: "revenue|pipeline", level: "confidential" },
  ]
  
  // Runtime policies (checked on sensitive operations)
  data_residency:   map[domain → allowed_regions]
  retention:        map[classification → max_age]
  audit_level:      map[classification → audit_detail]
}
```

### 9.4 Audit Trail

Every context delivery is logged:

```
AuditEntry {
  timestamp:    datetime
  agent_id:     string
  query:        string (hashed for confidential queries)
  atoms_served: atom_id[]
  atoms_filtered: int        // How many were hidden by access control
  cache_tier:   enum
  latency_ms:   float
  feedback:     optional     // If agent provided relevance feedback
}
```

---

## 10. Observability & Audit

### 10.1 Metrics

**Serving metrics:**
- `lattice_query_latency_ms` (histogram, by cache tier)
- `lattice_cache_hit_rate` (gauge, by tier L1-L4)
- `lattice_atoms_served_total` (counter, by domain)
- `lattice_tokens_served_total` (counter, by agent)
- `lattice_access_filtered_total` (counter — atoms hidden by ACL)

**Compiler metrics:**
- `lattice_compile_duration_ms` (histogram, by stage)
- `lattice_atoms_total` (gauge — total atoms in store)
- `lattice_frames_total` (gauge — total frames)
- `lattice_source_staleness_seconds` (gauge, by connector)
- `lattice_recompile_queue_depth` (gauge)

**Agent metrics:**
- `lattice_agent_query_rate` (counter, by agent)
- `lattice_agent_feedback_score` (gauge — relevance feedback)
- `lattice_subscription_count` (gauge, by agent)

### 10.2 Distributed Tracing

Every query gets a trace spanning:
```
[Query Router] → [L1 Check] → [L2 Check] → [Frame Assembly] → [Access Filter] → [Serialize] → [Respond]
```

### 10.3 Compliance Dashboard

For regulated enterprises:
- Who accessed what context and when
- Data residency compliance
- Retention policy enforcement
- Classification accuracy audits

---

## 11. Deployment Topology

### 11.1 Single-Tenant (SMB)

```
┌──────────────────────────┐
│    Single Lattice Node   │
│                          │
│  Compiler + Core + Mesh  │
│  Embedded atom store     │
│  In-memory L1/L2 cache   │
│                          │
│  Agents connect via gRPC │
└──────────────────────────┘
```

### 11.2 Multi-Tenant (Enterprise)

```
┌─────────────────────────────────────────────────────┐
│                   LATTICE CLUSTER                    │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐                 │
│  │  Compiler    │  │  Compiler    │  (Scale with    │
│  │  Workers     │  │  Workers     │   source count) │
│  └──────┬───────┘  └──────┬───────┘                 │
│         └──────────┬───────┘                        │
│                    ▼                                │
│  ┌─────────────────────────────┐                    │
│  │  Atom Store (distributed)  │  Sharded by domain  │
│  │  (ScyllaDB / TiKV / etc.)  │                    │
│  └─────────────┬───────────────┘                    │
│                │                                    │
│  ┌─────────────▼───────────────┐                    │
│  │  Mesh Nodes (stateless)    │  Scale with agent   │
│  │  ┌─────┐ ┌─────┐ ┌─────┐  │  count             │
│  │  │Mesh │ │Mesh │ │Mesh │  │                     │
│  │  │ #1  │ │ #2  │ │ #N  │  │  Each has local     │
│  │  └─────┘ └─────┘ └─────┘  │  L1/L2 cache        │
│  └────────────────────────────┘                     │
│                                                     │
│  ┌──────────────────────────┐                       │
│  │  Event Bus (Kafka/NATS)  │                       │
│  └──────────────────────────┘                       │
└─────────────────────────────────────────────────────┘
```

### 11.3 Scaling Characteristics

| Component | Scales With | Strategy |
|-----------|-------------|----------|
| Connectors | Number of data sources | Horizontal: one worker per source |
| Compiler | Volume of source changes | Horizontal: workers pull from queue |
| Atom Store | Total knowledge volume | Sharded by domain |
| Mesh Nodes | Number of concurrent agents | Stateless horizontal scaling |
| L2 Cache | Number of active domains | Distributed cache (Redis Cluster) |
| Event Bus | Subscription volume | Partitioned by domain |

---

## 12. Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| L1 query latency (p99) | < 1ms | In-process memory lookup |
| L2 query latency (p99) | < 5ms | Shared cache + access filter |
| L3 query latency (p99) | < 50ms | Lattice traversal |
| L4 query latency (p99) | < 200ms | Full semantic search |
| Overall cache hit rate (L1+L2) | > 90% | After warm-up period |
| Compile throughput | > 1000 atoms/sec | Per compiler worker |
| Push notification latency | < 100ms | From source change to agent delivery |
| Concurrent agent connections | > 10,000 | Per mesh node |
| Atom store capacity | > 100M atoms | Per cluster |
| Access check latency | < 1μs | Bitmask AND operation |

---

## 13. Open Questions

These need resolution before v1:

### Representation
- [ ] **Sparse vector dimensionality**: 2048-bit vs 4096-bit? Tradeoff between expressiveness and memory.
- [ ] **Atom granularity**: How small is too small? Need empirical testing with real enterprise data.
- [ ] **Frame size limits**: What's the optimal atom count per frame? Probably varies by domain.

### Compilation
- [ ] **LLM choice for distillation**: Local model (cost-efficient, data stays on-prem) vs cloud API (better quality)?
- [ ] **Contradiction handling**: When two sources disagree, how does the compiler resolve it? Flag both? Pick one?
- [ ] **Multi-language support**: Enterprise data in multiple languages — compile to English atoms or keep native?

### Serving
- [ ] **Cold start**: New agent with no history — how to bootstrap an L1 cache? Use role-based defaults?
- [ ] **Token budget allocation**: When a frame exceeds the agent's token budget, which atoms get cut?
- [ ] **Staleness vs latency**: If the freshest data requires L4 search, do we serve stale L2 data while L4 runs in background?

### Governance
- [ ] **Bitmask overflow**: 256 bits handles most enterprises, but what about very large orgs? Hierarchical bitmasks?
- [ ] **Cross-tenant context**: In a multi-tenant deployment, can context ever be shared across tenants? (Probably not, but need a policy.)
- [ ] **Right to deletion**: GDPR/CCPA — when source data is deleted, how fast must atoms be purged?

### Business
- [ ] **Pricing model**: Per atom? Per query? Per agent seat? Per source connector?
- [ ] **Open-source vs proprietary**: Core open-source with enterprise features? Full proprietary?
- [ ] **First target vertical**: Which industry benefits most? (FinServ, Healthcare, Tech — each has different compliance needs)

---

## Appendix A: Technology Candidates

| Component | Candidates | Notes |
|-----------|-----------|-------|
| Atom Store | ScyllaDB, TiKV, FoundationDB | Need low-latency point reads + range scans |
| Dense Vector Index | Milvus, Qdrant, pgvector | L3/L4 ANN search |
| Sparse Vector Ops | Custom (SIMD), or Roaring Bitmaps | L1/L2 fast matching |
| L2 Cache | Redis Cluster, Dragonfly, Memcached | Pre-warmed frame storage |
| Event Bus | NATS JetStream, Kafka, Redpanda | Frame invalidation + push delivery |
| Compiler Orchestration | Temporal, Prefect | Multi-stage pipeline coordination |
| API Gateway | Envoy, Kong | Rate limiting, auth, routing |
| Observability | OpenTelemetry, Prometheus, Grafana | Metrics + traces + dashboards |

---

## Appendix B: Sparse Distributed Representation (SDR) Deep Dive

SDRs are inspired by how the neocortex encodes information. Each atom is represented as a sparse binary vector — roughly 2% of bits are active (e.g., 40 out of 2048).

**Properties that matter for Lattice:**

1. **Similarity = overlap**: Two atoms are semantically similar if their active bits overlap. This is a popcount on AND — single CPU instruction.

2. **Union = combination**: OR two SDRs to represent "both of these topics." The result is slightly denser but still matchable.

3. **Noise tolerance**: Even with some bit errors, matching still works. This gives robustness to approximation.

4. **Fixed memory**: Every atom is exactly 256 bytes (2048 bits). Predictable, cache-friendly.

5. **Hardware acceleration**: Bitwise operations are SIMD-friendly. AVX-512 can compare thousands of SDRs per microsecond.

**Generating SDRs from dense embeddings:**

```
dense_to_sdr(dense_vec[768]) → sdr[2048]:
  1. Project dense vector through learned random projection matrix (768 → 2048)
  2. Apply winner-take-all: keep top-k (k ≈ 40) highest values, set to 1
  3. All others set to 0
  4. Result: 2048-bit vector with exactly 40 active bits
```

This is a one-time computation per atom (done at compile time), and the projection matrix is fixed per Lattice instance.

---

*This is a living document. Update as design evolves.*
