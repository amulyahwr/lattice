# Lattice MVP — Scope & Code Mapping

**Date:** 2026-04-25
**Goal:** Prove the core thesis — compiled context atoms served through a tiered cache with bitmask access control, measurably faster than naive RAG.

---

## 1. What the MVP Must Prove

| Thesis | How We Prove It |
|--------|-----------------|
| Atoms > Chunks | Ingested content is atomized + distilled, not just chunked. Agents get concise, typed context units. |
| Compile once, serve fast | Expensive work (extraction, distillation, embedding, tagging) runs at ingest. Queries hit pre-indexed atoms. |
| Bitmask access = fast | Access check is `role_mask & access_mask`, not a DB join per query. Measurable sub-ms filtering. |
| Tiered serving beats flat search | L2 (frame cache) + L3 (pgvector) with a router. Show L2 hits are 10x+ faster than L3. |
| Agent-aware context | Different agents get different context for the same query based on profile, role, and token budget. |

---

## 2. MVP Scope — What's In

### 2.1 Data Model

**Context Atom** (replaces Chunk + Entity)
- `id`, `content` (distilled text), `raw_ref` (source pointer)
- `kind`: fact | decision | metric | relationship | event | procedure
- `dense_vec`: float[384] (existing embedding dim, upgrade later)
- `domain[]`, `freshness`, `confidence`
- `access_mask`: bit field (64-bit integer for MVP — covers most orgs)
- `links[]`: typed edges to other atoms (stored as JSONB array of `{target_id, relation}`)
- `source_id`, `compiled_at`, `version`

**Context Frame** (new)
- `id`, `name`, `domain`
- `atom_ids[]`: ordered list of atom references
- `token_count`: pre-computed total tokens
- `access_mask`: union of all atom masks (fast pre-filter)
- `last_accessed`, `access_count`

**Agent Profile** (evolves from Agent)
- Keep: `id`, `name`, `api_key`, `purpose`, `domains`
- Add: `role_mask` (64-bit), `max_tokens`, `freshness_req`
- Drop for MVP: `purpose_embedding`, `clearance` string (replaced by bitmask), `auto_grant_threshold`

**Source** (slimmed down)
- Keep: `id`, `name`, `source_type`, `classification`, `domains`
- Drop: `summary_embedding` (lives on atoms now), `summary` (becomes atoms)

**Access Log** (evolves)
- Keep: `id`, `agent_id`, `query`, `decision`, `timestamp`
- Add: `atoms_served` (count), `atoms_filtered` (count), `cache_tier`, `latency_ms`
- Drop: `source_id` as primary key (access is per-atom now), `relevance_score`

### 2.2 Compiler Pipeline

Synchronous for MVP (async workers come later), but structured as distinct stages:

```
Ingest → Atomize → Distill → Embed → Link → Tag → Index
```

- **Atomize**: Break content into atomic facts (LLM-assisted, fall back to sentence splitting)
- **Distill**: Generate concise token-efficient text per atom (LLM or extractive for MVP)
- **Embed**: Dense vector via sentence-transformers (existing)
- **Link**: Identify relationships between atoms (regex extraction + LLM for MVP)
- **Tag**: Assign `access_mask` from source permissions, assign `domain[]`, set `kind`
- **Index**: Write atoms to DB, build/update affected frames

### 2.3 Serving

**Query Router** with two tiers for MVP:
- **L2 (Frame Cache)**: In-memory dict/Redis. Pre-warmed frames keyed by domain + profile match. ~5ms.
- **L3 (pgvector)**: Existing cosine similarity search. ~50ms.

No L1 (per-agent session cache) or L4 (cold search) for MVP. Add later.

**Query flow:**
```
query + agent_profile
    → apply role_mask filter
    → check L2 frame cache (domain match)
    → if miss, fall through to L3 pgvector search
    → filter atoms by access_mask
    → trim to agent's max_tokens budget
    → return atoms + metadata (cache_tier, latency, version)
```

### 2.4 API Surface

```
POST   /v1/sources/ingest          Ingest a document (runs compiler)
GET    /v1/sources                  List sources

POST   /v1/context/query            Query context (goes through router)

POST   /v1/agents                   Register agent with profile
GET    /v1/agents                   List agents
PATCH  /v1/agents/{id}              Update profile

GET    /v1/admin/stats              Graph + atom + frame stats
GET    /v1/admin/frames             List frames
```

### 2.5 Connectors (MVP)

- **PDF** (existing)
- **Plain text / Markdown** (trivial to add)
- That's it for MVP. Confluence, Slack, etc. come later.

---

## 3. MVP Scope — What's Out

| Feature | Why Out | When |
|---------|---------|------|
| L1 per-agent session cache | Optimization — L2+L3 proves the thesis | Phase 2 |
| L4 cold semantic search | Edge case — L3 covers this adequately for MVP | Phase 2 |
| Sparse binary vectors (SDR) | Advanced optimization — dense vectors are sufficient for MVP | Phase 3 |
| Push/streaming subscriptions | Pull-based queries prove value first | Phase 3 |
| Delta protocol (version diffs) | Optimization — full frames are fine initially | Phase 3 |
| Frame lattice hierarchy (join/meet) | Flat frames prove the concept; hierarchy adds complexity | Phase 2 |
| Event bus (Kafka/NATS) | Overkill for MVP; compiler writes directly | Phase 3 |
| gRPC interface | REST is fine for MVP; gRPC for production throughput | Phase 3 |
| Multi-tenant deployment | Single-tenant first | Phase 4 |
| Webhook connectors (real-time source sync) | Polling/manual ingest for MVP | Phase 2 |
| Compiler async workers | Synchronous pipeline for MVP; parallelize later | Phase 2 |

---

## 4. Existing Code → MVP Mapping

### ✅ KEEP — Direct Reuse

| File | Role in MVP | Changes |
|------|-------------|---------|
| `backend/config.py` | Config | Add `cache_backend`, `compiler_llm_model`, `atom_access_bits` fields |
| `backend/models/database.py` | DB setup | None — works as-is |
| `backend/main.py` | FastAPI app | Swap route imports to new routes |
| `backend/connectors/base.py` | Connector interface | None for MVP (add `changes_since` later) |
| `backend/connectors/pdf.py` | PDF ingestion | None — feeds into compiler's atomize stage |
| `backend/engine/embeddings.py` | Compiler → Embed stage | None — works as-is |
| `pyproject.toml` | Project deps | Add `redis`, `tiktoken` (token counting) |

**7 files kept as-is or near as-is.**

### 🔄 KEEP + REFACTOR — Significant Evolution

| File | What It Becomes | Key Changes |
|------|-----------------|-------------|
| `backend/models/schemas.py` | `backend/models/atoms.py` | `Chunk` → `Atom` (add `kind`, `access_mask`, `domain`, `freshness`, `links`, `version`). `Agent` → `AgentProfile` (add `role_mask`, `max_tokens`; drop `clearance` string). `Source` stays slimmer. `AgentPermission` table removed. `AccessLog` gets new fields. Add `Frame` model. |
| `backend/engine/access.py` | `backend/compiler/tagger.py` | `check_clearance()` → `compute_access_mask()` (builds bitmask at compile time). Runtime access becomes one-liner: `mask & mask`. The `resolve_access()` function becomes a compile-time step, not a query-time step. `log_access()` stays but moves to serving layer. |
| `backend/engine/search.py` | `backend/serving/l3_search.py` | Same pgvector search but: (1) queries atoms not chunks, (2) bitmask pre-filter before vector search, (3) returns atoms not chunk dicts. |
| `backend/engine/extraction.py` | `backend/compiler/atomizer.py` | Regex patterns stay as the fast path. Add LLM-based atomization as the quality path. Output changes from `ExtractedEntity` → `Atom` objects with `kind` tags. |
| `backend/engine/graph.py` | `backend/compiler/linker.py` | `ingest_to_graph()` → `link_atoms()`. Instead of writing Entity/Relationship rows, it sets `links[]` on atoms. Entity dedup logic stays. |
| `backend/engine/summarize.py` | `backend/compiler/distiller.py` | `extractive_summary()` stays as fast path. Add `llm_distill()` for higher quality atom content. `suggest_domains()` moves to tagger. |
| `backend/engine/recommendations.py` | `backend/serving/frame_matcher.py` | Matching logic (semantic + domain overlap) → frame recommendation for agents. Same math, different target (frames not sources). |
| `backend/api/routes_sources.py` | `backend/api/routes_ingest.py` | Upload flow becomes: receive file → run compiler pipeline → return atom/frame stats. Sequential stages instead of monolithic function. |
| `backend/api/routes_agents.py` | `backend/api/routes_agents.py` | Keep most routes. Drop grant/deny/revoke endpoints (bitmask replaces them). Add `role_mask` to create/update. |
| `backend/api/routes_search.py` | `backend/api/routes_context.py` | New `/v1/context/query` endpoint. Goes through Query Router → L2 → L3. Returns atoms + metadata. |
| `backend/api/routes_graph.py` | `backend/api/routes_admin.py` | Graph stats → atom/frame stats. Entity search → atom search. Neighborhood → atom links traversal. |
| `backend/api/deps.py` | `backend/api/deps.py` | Keep agent auth dep. Add cache dependency injection. |

**12 files refactored.**

### ❌ REMOVE — Dead in New Architecture

| File | Why |
|------|-----|
| `backend/models/graph.py` | `Entity` and `Relationship` tables are gone. Entities become atoms with `kind=entity`. Relationships become atom `links[]` (JSONB). No separate graph tables. |
| `backend/models/schemas.py` → `AgentPermission` class | Bitmask replaces per-source-per-agent permission rows. One `role_mask` on the agent, one `access_mask` on the atom. No join table. |

**2 files / models removed.**

---

## 5. New Files to Create (Don't Exist Yet)

| File | Purpose |
|------|---------|
| `backend/compiler/__init__.py` | Compiler package |
| `backend/compiler/pipeline.py` | Orchestrates: atomize → distill → embed → link → tag → index |
| `backend/compiler/atomizer.py` | Breaks raw text into atoms (evolved from extraction.py) |
| `backend/compiler/distiller.py` | Generates concise atom content (evolved from summarize.py) |
| `backend/compiler/linker.py` | Creates atom-to-atom links (evolved from graph.py) |
| `backend/compiler/tagger.py` | Assigns access_mask, domains, kind (evolved from access.py) |
| `backend/serving/__init__.py` | Serving package |
| `backend/serving/router.py` | Query Router: L2 check → L3 fallback → access filter → token trim |
| `backend/serving/l2_cache.py` | Frame cache (in-memory dict for MVP, Redis-backed later) |
| `backend/serving/l3_search.py` | pgvector atom search (evolved from search.py) |
| `backend/serving/frame_builder.py` | Builds frames from atoms by domain clustering |
| `backend/serving/frame_matcher.py` | Matches agents to relevant frames (evolved from recommendations.py) |
| `backend/models/atoms.py` | Atom, Frame, AgentProfile, Source, AccessLog models |

**13 new files.**

---

## 6. New Project Structure

```
lattice/
├── backend/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app (KEEP)
│   ├── config.py                    # Settings (KEEP + extend)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py              # DB setup (KEEP)
│   │   └── atoms.py                 # Atom, Frame, AgentProfile, Source, AccessLog (NEW)
│   │
│   ├── compiler/
│   │   ├── __init__.py              # NEW
│   │   ├── pipeline.py              # Compiler orchestrator (NEW)
│   │   ├── atomizer.py              # Text → Atoms (EVOLVED from extraction.py)
│   │   ├── distiller.py             # Raw → Distilled (EVOLVED from summarize.py)
│   │   ├── linker.py                # Atom linking (EVOLVED from graph.py engine)
│   │   └── tagger.py                # Access mask + domain tagging (EVOLVED from access.py)
│   │
│   ├── serving/
│   │   ├── __init__.py              # NEW
│   │   ├── router.py                # Query Router L2→L3 (NEW)
│   │   ├── l2_cache.py              # Frame cache (NEW)
│   │   ├── l3_search.py             # pgvector search (EVOLVED from search.py)
│   │   ├── frame_builder.py         # Frame assembly (NEW)
│   │   └── frame_matcher.py         # Agent↔Frame matching (EVOLVED from recommendations.py)
│   │
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py                  # Connector interface (KEEP)
│   │   └── pdf.py                   # PDF connector (KEEP)
│   │
│   ├── engine/
│   │   └── embeddings.py            # Embedding generation (KEEP)
│   │
│   └── api/
│       ├── __init__.py
│       ├── deps.py                  # Dependencies (KEEP + extend)
│       ├── routes_ingest.py         # Source ingestion (EVOLVED from routes_sources.py)
│       ├── routes_context.py        # Context query (EVOLVED from routes_search.py)
│       ├── routes_agents.py         # Agent management (KEEP + refactor)
│       └── routes_admin.py          # Stats + frames (EVOLVED from routes_graph.py)
│
├── pyproject.toml                   # (KEEP + extend)
├── ARCHITECTURE.md
├── MVP.md
├── ROADMAP.md
└── LICENSE
```

---

## 7. Summary

| Category | Count | Files |
|----------|-------|-------|
| **Keep as-is** | 7 | config, database, main, connectors/base, connectors/pdf, engine/embeddings, pyproject.toml |
| **Refactor** | 12 | schemas→atoms, access→tagger, search→l3_search, extraction→atomizer, graph→linker, summarize→distiller, recommendations→frame_matcher, all 4 route files, deps |
| **Remove** | 2 | models/graph.py, AgentPermission model |
| **Create new** | 13 | compiler package (5), serving package (6), models/atoms.py, routes restructure |
| **Total MVP files** | ~25 | Lean enough to ship fast |

**Bottom line:** ~60% of existing logic survives in evolved form. The core investment (FastAPI, async Postgres, pgvector, embeddings, PDF connector, entity extraction, summarization) all carries forward. What's new is the *architecture around it* — the compiler pipeline structure, the frame/cache layer, and the bitmask access model.
