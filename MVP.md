# Lattice MVP — Scope & Code Mapping

**Date:** 2026-04-26 (Updated for L3-only architecture + cross-source linking + knowledge graph visualization)
**Goal:** Prove the core thesis — compiled context atoms served through pgvector search with bitmask access control, cross-source relationship linking, and full knowledge graph visualization.

---

## 1. What the MVP Must Prove

| Thesis                        | How We Prove It                                                                                              |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Atoms > Chunks                | Ingested content is atomized + distilled, not just chunked. Agents get concise, typed context units.         |
| Compile once, serve fast      | Expensive work (extraction, distillation, embedding, tagging) runs at ingest. Queries hit pre-indexed atoms. |
| Bitmask access = fast         | Access check is `role_mask & access_mask`, not a DB join per query. Measurable sub-ms filtering.             |
| pgvector search is sufficient | L3 (pgvector) with bitmask pre-filtering delivers 40-60ms latency — fast enough for production.              |
| Agent-aware context           | Different agents get different context for the same query based on profile, role, and token budget.          |
| Cross-source knowledge links  | New atoms are linked to semantically similar atoms from other sources via domain-aware candidate selection + LLM inference. Knowledge graph spans source boundaries. |

---

## 2. MVP Scope — What's In

### 2.1 Data Model

**Context Atom** (replaces Chunk + Entity)

- `id`, `content` (distilled text), `raw_content` (original text)
- `kind`: fact | decision | metric | relationship | event | procedure
- `dense_vec`: float[384] (sentence-transformers embedding)
- `domain[]`, `freshness`, `confidence`
- `access_mask`: bit field (64-bit integer for MVP — covers most orgs)
- `links[]`: typed edges to other atoms (stored as JSONB array of `{target_id, relation}`)
- `source_id`, `compiled_at`, `version`

**Agent Profile** (evolves from Agent)

- Keep: `id`, `name`, `api_key`, `purpose`, `domains`
- Add: `role_mask` (64-bit), `max_tokens`, `freshness_req`
- Drop for MVP: `purpose_embedding`, `clearance` string (replaced by bitmask), `auto_grant_threshold`

**Source** (slimmed down)

- Keep: `id`, `name`, `source_type`, `domains`
- Drop: `summary_embedding` (lives on atoms now), `summary` (becomes atoms), `classification`

**Access Log** (evolves)

- Keep: `id`, `agent_id`, `query`, `decision`, `timestamp`
- Add: `atoms_served` (count), `atoms_filtered` (count), `cache_tier` (always "L3"), `latency_ms`
- Drop: `source_id` as primary key (access is per-atom now), `relevance_score`

### 2.2 Compiler Pipeline

Synchronous for MVP (async workers come later), but structured as distinct stages:

```
Ingest → Atomize → Distill → Embed → Link → Tag → Index → Cross-link
```

- **Atomize**: Break content into atomic facts (LLM-assisted, fall back to sentence splitting)
- **Distill**: Generate concise token-efficient text per atom (LLM or extractive for MVP)
- **Embed**: Dense vector via sentence-transformers (existing)
- **Link**: Identify within-source relationships between atoms (LLM)
- **Tag**: Assign `access_mask` from source permissions, assign `domain[]`, set `kind`
- **Index**: Write atoms to DB with pgvector index; two-tier deduplication (content_hash → canonical_hash)
- **Cross-link**: Find relationships between new atoms and semantically similar atoms from other sources. Domain-aware candidate selection via `expand_domains()` (one-hop expansion through DOMAIN_GROUPS) + pgvector similarity search (threshold ≥ 0.5, top-K=5 per new atom) + LLM link inference.

`compile_source()` returns:
```python
{
    "atoms_created": int,
    "cross_links_added": int,
    "kinds": dict[str, int],   # e.g. {"fact": 3, "metric": 1}
    "domains": list[str],
}
```

### 2.3 Serving (L3-Only)

**Query Router** with single tier for MVP:

- **L3 (pgvector)**: Cosine similarity search with bitmask pre-filtering. ~40-60ms.

**Query flow:**

```
query + agent_profile
    → embed query
    → apply role_mask pre-filter (SQL WHERE)
    → pgvector cosine similarity search
    → filter atoms by access_mask (post-filter)
    → trim to agent's max_tokens budget
    → return atoms + metadata (cache_tier="L3", latency, version)
```

**Why L3-only for MVP:**

- Simpler architecture — no frame cache complexity
- pgvector is fast enough (40-60ms) for production use
- Bitmask pre-filtering keeps search space small
- Can add L2 frame cache later as optimization without breaking changes

### 2.4 API Surface

```
POST   /api/v1/sources/ingest           Ingest a document (runs 7-stage compiler)
GET    /api/v1/sources/                 List sources
GET    /api/v1/sources/{id}/atoms       List atoms for a source
DELETE /api/v1/sources/{id}             Delete source

POST   /api/v1/context/query            Query context (L3 pgvector search)

POST   /api/v1/agents                   Register agent with profile
GET    /api/v1/agents                   List agents
PATCH  /api/v1/agents/{id}              Update profile

GET    /api/v1/atoms/graph              Full knowledge graph (all atoms + relationships)
GET    /api/v1/atoms/{id}/neighborhood  Single atom neighborhood (1-hop)

GET    /admin/stats                     Atom/agent/source/query counts
GET    /admin/activity                  Recent query activity
POST   /admin/relink                    Re-run cross-source linking across all atoms

GET    /audit/log                       Paginated access log
GET    /audit/stats                     Access control statistics
```

### 2.5 Connectors (MVP)

- **PDF** (existing)
- **Plain text / Markdown** (trivial to add)
- That's it for MVP. Confluence, Slack, etc. come later.

---

## 3. MVP Scope — What's Out

| Feature                                    | Why Out                                              | When               |
| ------------------------------------------ | ---------------------------------------------------- | ------------------ |
| L2 frame cache                             | Optimization — L3 proves the thesis                  | Phase 2 (optional) |
| L1 per-agent session cache                 | Optimization — L3 is fast enough                     | Phase 2            |
| L4 cold semantic search                    | Edge case — L3 covers this                           | Phase 2            |
| Sparse binary vectors (SDR)                | Advanced optimization — dense vectors sufficient     | Phase 3            |
| Push/streaming subscriptions               | Pull-based queries prove value first                 | Phase 3            |
| Delta protocol (version diffs)             | Optimization — full atoms are fine initially         | Phase 3            |
| Event bus (Kafka/NATS)                     | Overkill for MVP; compiler writes directly           | Phase 3            |
| gRPC interface                             | REST is fine for MVP; gRPC for production throughput | Phase 3            |
| Multi-tenant deployment                    | Single-tenant first                                  | Phase 4            |
| Webhook connectors (real-time source sync) | Polling/manual ingest for MVP                        | Phase 2            |
| Compiler async workers                     | Synchronous pipeline for MVP; parallelize later      | Phase 2            |

---

## 4. Existing Code → MVP Mapping

### ✅ KEEP — Direct Reuse

| File                           | Role in MVP            | Changes                                    |
| ------------------------------ | ---------------------- | ------------------------------------------ |
| `backend/config.py`            | Config                 | Removed `cache_backend` (no L2 cache)      |
| `backend/models/database.py`   | DB setup               | None — works as-is                         |
| `backend/main.py`              | FastAPI app            | Swap route imports to new routes           |
| `backend/connectors/base.py`   | Connector interface    | None for MVP                               |
| `backend/connectors/pdf.py`    | PDF ingestion          | None — feeds into compiler's atomize stage |
| `backend/connectors/text.py`   | Text ingestion         | Added for markdown/txt                     |
| `backend/engine/embeddings.py` | Compiler → Embed stage | None — works as-is                         |
| `pyproject.toml`               | Project deps           | Add `tiktoken` (token counting)            |

**8 files kept as-is or near as-is.**

### 🔄 KEEP + REFACTOR — Significant Evolution

| File                            | What It Becomes                 | Key Changes                                                                                                                                                                                                                                                                                     |
| ------------------------------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend/models/schemas.py`     | `backend/models/atoms.py`       | `Chunk` → `Atom` (add `kind`, `access_mask`, `domain`, `freshness`, `links`, `version`). `Agent` → `AgentProfile` (add `role_mask`, `max_tokens`; drop `clearance` string). `Source` stays slimmer. `AgentPermission` table removed. `AccessLog` gets new fields. **No Frame model** (L3-only). |
| `backend/engine/access.py`      | `backend/compiler/tagger.py`    | `check_clearance()` → `compute_access_mask()` (builds bitmask at compile time). Runtime access becomes one-liner: `mask & mask`.                                                                                                                                                                |
| `backend/engine/search.py`      | `backend/serving/l3_search.py`  | Same pgvector search but: (1) queries atoms not chunks, (2) bitmask pre-filter before vector search, (3) returns atoms not chunk dicts.                                                                                                                                                         |
| `backend/engine/extraction.py`  | `backend/compiler/atomizer.py`  | Regex patterns stay as the fast path. Add LLM-based atomization as the quality path. Output changes from `ExtractedEntity` → `Atom` objects with `kind` tags.                                                                                                                                   |
| `backend/engine/graph.py`       | `backend/compiler/linker.py`    | `ingest_to_graph()` → `link_atoms()`. Instead of writing Entity/Relationship rows, it sets `links[]` on atoms.                                                                                                                                                                                  |
| `backend/engine/summarize.py`   | `backend/compiler/distiller.py` | `extractive_summary()` stays as fast path. Add `llm_distill()` for higher quality atom content.                                                                                                                                                                                                 |
| `backend/api/routes_sources.py` | `backend/api/routes_ingest.py`  | Upload flow becomes: receive file → run compiler pipeline → return atom stats.                                                                                                                                                                                                                  |
| `backend/api/routes_agents.py`  | `backend/api/routes_agents.py`  | Keep most routes. Drop grant/deny/revoke endpoints (bitmask replaces them). Add `role_mask` to create/update.                                                                                                                                                                                   |
| `backend/api/routes_search.py`  | `backend/api/routes_context.py` | New `/v1/context/query` endpoint. Goes through Query Router → L3. Returns atoms + metadata.                                                                                                                                                                                                     |
| `backend/api/routes_graph.py`   | `backend/api/routes_admin.py`   | Graph stats → atom stats. Entity search → atom search. Neighborhood → atom links traversal.                                                                                                                                                                                                     |
| `backend/api/deps.py`           | `backend/api/deps.py`           | Keep agent auth dep. Remove cache dependency (no L2).                                                                                                                                                                                                                                           |

**11 files refactored.**

### ❌ REMOVE — Dead in New Architecture

| File                                                  | Why                                                                                                                                 |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `backend/models/graph.py`                             | `Entity` and `Relationship` tables are gone. Entities become atoms with `kind=entity`. Relationships become atom `links[]` (JSONB). |
| `backend/models/schemas.py` → `AgentPermission` class | Bitmask replaces per-source-per-agent permission rows.                                                                              |
| `backend/serving/l2_cache.py`                         | No L2 frame cache in MVP                                                                                                            |
| `backend/serving/frame_builder.py`                    | No frames in MVP                                                                                                                    |
| `backend/serving/frame_matcher.py`                    | No frames in MVP                                                                                                                    |
| `tests/unit/test_l2_cache.py`                         | No L2 cache                                                                                                                         |
| `tests/unit/test_frame_builder.py`                    | No frames                                                                                                                           |

**7 files / models removed.**

---

## 5. New Files Created

| File                             | Purpose                                                      |
| -------------------------------- | ------------------------------------------------------------ |
| `backend/compiler/__init__.py`   | Compiler package                                             |
| `backend/compiler/pipeline.py`   | Orchestrates: atomize → distill → embed → link → tag → index |
| `backend/compiler/atomizer.py`   | Breaks raw text into atoms                                   |
| `backend/compiler/distiller.py`  | Generates concise atom content                               |
| `backend/compiler/linker.py`     | Creates atom-to-atom links                                   |
| `backend/compiler/tagger.py`     | Assigns access_mask, domains, kind                           |
| `backend/compiler/llm_client.py` | LLM API client for compiler stages                           |
| `backend/serving/__init__.py`    | Serving package                                              |
| `backend/serving/router.py`      | Query Router: L3 search → access filter → token trim         |
| `backend/serving/l3_search.py`   | pgvector atom search                                         |
| `backend/models/atoms.py`        | Atom, AgentProfile, Source, AccessLog models                 |
| `backend/connectors/text.py`     | Text/markdown connector                                      |

**12 new files.**

---

## 6. Current Project Structure

```
lattice/
├── backend/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app
│   ├── config.py                    # Settings (no cache_backend)
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py              # DB setup
│   │   └── atoms.py                 # Atom, AgentProfile, Source, AccessLog (no Frame)
│   │
│   ├── compiler/
│   │   ├── __init__.py
│   │   ├── pipeline.py              # Compiler orchestrator
│   │   ├── atomizer.py              # Text → Atoms
│   │   ├── distiller.py             # Raw → Distilled
│   │   ├── linker.py                # Atom linking
│   │   ├── tagger.py                # Access mask + domain tagging
│   │   └── llm_client.py            # LLM API client
│   │
│   ├── serving/
│   │   ├── __init__.py
│   │   ├── router.py                # Query Router (L3-only)
│   │   └── l3_search.py             # pgvector search
│   │
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── base.py                  # Connector interface
│   │   ├── pdf.py                   # PDF connector
│   │   └── text.py                  # Text/markdown connector
│   │
│   ├── engine/
│   │   └── embeddings.py            # Embedding generation
│   │
│   └── api/
│       ├── __init__.py
│       ├── deps.py                  # Dependencies (no cache dep)
│       ├── routes_ingest.py         # Source ingestion
│       ├── routes_context.py        # Context query
│       ├── routes_agents.py         # Agent management
│       ├── routes_atoms.py          # Atom CRUD
│       └── routes_admin.py          # Stats + audit
│
├── frontend/                        # React + TypeScript UI
│   ├── src/
│   │   ├── pages/                   # Dashboard, Agents, Sources, etc.
│   │   ├── components/              # Reusable UI components
│   │   ├── hooks/                   # React hooks for API calls
│   │   └── lib/                     # Types, utils, constants
│   └── package.json
│
├── tests/
│   ├── api/                         # API integration tests
│   ├── compiler/                    # Compiler unit tests
│   ├── serving/                     # Serving unit tests
│   └── unit/                        # Other unit tests
│
├── pyproject.toml
├── ARCHITECTURE.md                  # Detailed architecture docs
├── ARCHITECTURE_SIMPLIFIED.md       # L3-only architecture guide
├── MVP.md                           # This file
├── PITCH.md                         # Project pitch
├── ROADMAP.md                       # Development roadmap
└── LICENSE
```

---

## 7. Summary

| Category            | Count | Notes                                                                                                                         |
| ------------------- | ----- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Keep as-is**      | 8     | config, database, main, connectors, embeddings, pyproject.toml                                                                |
| **Refactor**        | 11    | schemas→atoms, access→tagger, search→l3_search, extraction→atomizer, graph→linker, summarize→distiller, all route files, deps |
| **Remove**          | 7     | models/graph.py, AgentPermission, L2 cache files, frame files                                                                 |
| **Create new**      | 12    | compiler package (6), serving package (2), models/atoms.py, connectors/text.py, routes updates                                |
| **Total MVP files** | ~30   | Lean, focused architecture                                                                                                    |

**Bottom line:** ~60% of existing logic survives in evolved form. The core investment (FastAPI, async Postgres, pgvector, embeddings, PDF connector, entity extraction, summarization) all carries forward. What's new is the _architecture around it_ — the compiler pipeline structure, L3-only serving, and the bitmask access model.

**Key simplification:** Removed L2 frame cache complexity. pgvector with bitmask pre-filtering is fast enough (40-60ms) for production use. Can add L2 back later as an optimization without breaking changes.
