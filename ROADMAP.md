# Lattice Roadmap

> Not just search. A context engine that compounds intelligence.

---

## Vision

Lattice is a knowledge graph that learns from every interaction. Agents connect to it, query it, and it gets smarter over time. The more data flows through it, the more connections it discovers, the better context it delivers.

**The graph is the product. Everything else is built on top of it.**

---

## Phase 1: Graph Core ← NOW

Build the foundation that everything else depends on.

### Entity-Relationship Extraction
- Extract entities (people, orgs, dates, concepts, metrics) from ingested content
- Extract relationships between entities (reported_by, occurred_on, references, part_of)
- Run extraction during ingestion pipeline (after chunking, before/alongside embedding)
- Start with rule-based + lightweight NLP extraction, add LLM extraction as optional layer

### Graph Storage
- Entities table: id, name, type, properties (JSONB), embedding, source_id
- Relationships table: id, from_entity_id, to_entity_id, type, properties, source_id
- Keep it in Postgres (no Neo4j dependency yet) — use recursive CTEs for traversal
- Index for fast entity lookup and relationship traversal

### Hybrid Retrieval
- Query hits both vector search AND graph traversal
- Vector search → relevant chunks (existing)
- Graph traversal → connected entities and relationships (new)
- Merge and rank → richer context than either alone
- Agent asks "What do we know about Project Atlas?" → gets chunks + every person, date, metric, and document connected to it

### Graph-Aware Source DNA
- Source summary becomes a subgraph, not just a text blob
- Entities extracted from a source are linked to the source node
- Domain tags derived from entity types, not keyword matching

---

## Phase 2: Memory That Compounds

Make the graph learn from usage.

### Interaction Tracking
- Log every query, every result returned, every agent that asked
- Queries become nodes in the graph — linked to agents, sources, and entities they touched
- Frequency of access strengthens relationship weights

### Context Evolution
- New information updates existing entities (not just appends)
- Conflicting facts flagged and resolved (latest source wins, or human decides)
- Entity properties evolve: "Q3 revenue = $12M" gets updated when Q4 report arrives
- Stale knowledge decays — relevance scoring factors in recency

### Agent Memory
- Each agent builds a memory subgraph over time — what it's queried, what it's used, what worked
- Repeated queries about "revenue" → agent develops affinity for financial context
- Agent purpose embedding updates based on actual usage patterns, not just the initial description

### Feedback Loops
- Agents can mark context as useful/not useful
- Positive feedback strengthens graph connections
- Negative feedback weakens them or flags for review
- The graph literally gets smarter with every interaction

---

## Phase 3: Multi-Modal & Multi-Source

Prove the "any data, any modality" promise.

### More Connectors
- Postgres/SQL — structured data, auto-summarize tables and schemas
- Gmail/Google Drive — emails, docs, slides
- Notion/Confluence — knowledge base pages
- Web/URL scraper — paste a URL, ingest
- Snowflake — enterprise data warehouse

### Multi-Modal Ingestion
- Audio → transcribe → extract entities → graph
- Images → describe → extract entities → graph
- Video → keyframes + transcription → extract entities → graph
- Every modality feeds the same graph

### Cross-Source Relationships
- Entity resolution across sources (is "Sarah Chen" in the PDF the same as "S. Chen" in the email?)
- Automatic relationship discovery — find connections humans missed
- The graph becomes the unified knowledge layer that ties everything together

---

## Phase 4: Intelligence Layer

The graph becomes proactive.

### Proactive Context
- Agent starts a session → Lattice pre-loads relevant context based on the agent's history and the graph neighborhood
- "Right context at the right time" — not because someone configured it, but because the graph knows

### Knowledge Discovery
- Surface unexpected connections: "This contract references a vendor who was also mentioned in 3 support tickets"
- Anomaly detection: "This agent is accessing sources outside its usual pattern"
- Gap detection: "There's no data about Q2 in any source — this might be missing"

### Graph Visualization (Map v2)
- Visualize the actual knowledge graph — entities, relationships, clusters
- Zoom from high-level (source ↔ agent lineage) to low-level (entity ↔ entity relationships)
- Time dimension — watch the graph grow and evolve

### Policy Engine
- Declarative access rules on graph nodes and edges
- "No agent can traverse a relationship that crosses a restricted classification boundary"
- Graph-aware security — not just source-level, but entity-level access control

---

## What's Built (MVP)

The foundation is in place:

- ✅ Connector framework with PDF connector
- ✅ Vector search with pgvector
- ✅ Source DNA (summary, classification, domains, embedding)
- ✅ Agent identity profiles (purpose, clearance, domains, embedding)
- ✅ Semantic recommendation engine
- ✅ Human-in-the-loop access control
- ✅ Audit logging
- ✅ Visual lineage map (D3)
- ✅ Demo-ready UI

**Next: Phase 1 — build the graph.**
