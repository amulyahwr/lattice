# Lattice Architecture — L3-Only Simplified

**Date:** 2026-04-26  
**Status:** Implemented

## Overview

Lattice has been simplified to an **L3-only architecture**, removing the L2 frame cache layer to focus on proving the core thesis: **compiled atoms + bitmask access control**.

## Architecture Changes

### What Was Removed

1. **L2 Frame Cache** (`backend/serving/l2_cache.py`) - In-memory/Redis frame caching
2. **Frame Building** (`backend/serving/frame_builder.py`) - Pre-assembled atom bundles
3. **Frame Matching** (`backend/serving/frame_matcher.py`) - Agent-to-frame recommendation
4. **Frame Model** - Removed from `backend/models/atoms.py`
5. **Frame Routes** - Removed `/admin/frames` endpoint
6. **Cache Config** - Removed `cache_backend` from settings

### Current Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      COMPILER PIPELINE                       │
│  Ingest → Atomize → Distill → Embed → Link → Tag → Index   │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    ┌─────────────────┐
                    │   Atom Storage  │
                    │   (PostgreSQL)  │
                    │   + pgvector    │
                    └─────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      SERVING LAYER (L3)                      │
│                                                              │
│  Query → Embed → pgvector Search → Bitmask Filter →         │
│          Token Budget Trim → Return Atoms                    │
└─────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Compiler Pipeline (`backend/compiler/pipeline.py`)

**Stages:**

1. **Atomize** - LLM extracts atomic propositions from chunks
2. **Distill** - LLM rewrites concisely + extracts canonical form
3. **Embed** - Dense vectors via sentence-transformers
4. **Link** - LLM identifies relationships between atoms within the same source
5. **Tag** - Bitmask access control + domain tagging
6. **Index** - Write to DB with two-tier dedup
7. **Cross-link** - LLM finds relationships between new atoms and semantically similar atoms from previously ingested sources (domain-filtered, cosine similarity ≥ 0.5)

**Deduplication:**

- Tier 1: `content_hash` - Exact SHA-256 match on distilled text
- Tier 2: `canonical_hash` - Structural match on normalized canonical JSON

### 2. Data Model (`backend/models/atoms.py`)

**Atom** - Core knowledge unit

- `content` - Distilled, token-efficient text
- `kind` - fact | decision | metric | relationship | event | procedure
- `dense_vec` - Embedding vector (384-dim)
- `access_mask` - 64-bit bitmask for access control
- `domain[]` - Domain tags
- `links[]` - Typed edges to other atoms

**AgentProfile** - Agent identity

- `role_mask` - 64-bit bitmask for access control
- `max_tokens` - Token budget per query
- `domains[]` - Focus domains

**Source** - Data source metadata
**AtomSource** - Many-to-many join (atoms can come from multiple sources)
**AccessLog** - Audit trail

### 3. Serving Layer (`backend/serving/`)

**router.py** - L3-only query routing

- Embed query
- pgvector cosine similarity search
- Bitmask pre-filter: `atom.access_mask & agent.role_mask != 0`
- Domain filter: agent domains + "general"
- Token budget trimming
- Access logging

**l3_search.py** - pgvector search

- Semantic similarity via cosine distance
- Bitmask access filter in SQL
- Domain overlap filter
- Returns atoms with metadata

### 4. Cross-Source Linking (`backend/compiler/linker.py`)

Cross-source linking runs as Stage 7 of the pipeline immediately after new atoms are indexed. It connects knowledge across source boundaries without requiring re-ingestion.

**Domain expansion** (`expand_domains`):  
Each atom's domains are expanded one hop via `DOMAIN_GROUPS` before the candidate search. A `sales` atom searches `{sales, finance, product}` — never `engineering` or `hr`.

```python
DOMAIN_GROUPS = [
    {"sales", "finance"},
    {"sales", "product"},
    {"engineering", "product"},
    {"legal", "hr"},
    {"legal", "finance"},
]
```

**Candidate selection** (`fetch_cross_link_candidates` in `pipeline.py`):  
- Per new atom: pgvector cosine similarity search filtered by expanded domains
- Threshold: similarity ≥ 0.5 (cosine distance ≤ 0.5)
- Top-K: 5 candidates per new atom, deduplicated across all new atoms

**Link direction**: One-directional only — new atoms get links to existing atoms. Existing atoms are not modified during a new ingest run (bidirectional writes add no serving value since L3 retrieval is similarity-based, not graph-traversal).

**Admin re-link**: `POST /admin/relink` re-runs cross-source linking across all existing sources, appending new links without overwriting existing ones.

### 5. API Routes

**`/v1/sources/ingest`** - Ingest documents, run compiler (Stages 1–7)
**`/v1/context/query`** - Query context (L3 search)
**`/v1/agents`** - Agent management
**`/v1/atoms/graph`** - Full knowledge graph (all atoms + relationships)
**`/v1/atoms/{id}/neighborhood`** - Single atom neighborhood (1-hop)
**`/admin/stats`** - System stats (atoms, agents, sources, queries)
**`/admin/activity`** - Recent query activity
**`/admin/relink`** - Re-run cross-source linking across all atoms
**`/audit/log`** - Paginated access log
**`/audit/stats`** - Access control statistics

## Key Features Preserved

✅ **Atom-based knowledge representation**  
✅ **Bitmask access control** (nanosecond filtering)  
✅ **Agent-aware context** (same query, different results per agent)  
✅ **Compiler pipeline** (expensive work at ingest time)  
✅ **Two-tier deduplication** (content + canonical)  
✅ **Audit logging** (every access tracked)  
✅ **Domain-based filtering**  
✅ **Token budget management**  
✅ **Cross-source relationship linking** (domain-aware, similarity-gated)

## Performance Characteristics

- **L3 Search Latency:** ~50-100ms (pgvector + bitmask filter)
- **Access Control:** Sub-millisecond (bitwise AND operation)
- **Deduplication:** Prevents redundant atoms across sources
- **Token Trimming:** Respects agent budget constraints

## Future Enhancements (Post-MVP)

1. **L2 Frame Cache** - Pre-assembled atom bundles for hot paths
2. **L1 Session Cache** - Per-agent query result caching
3. **Sparse Binary Vectors** - SDR for ultra-fast filtering
4. **Async Compiler Workers** - Parallel pipeline stages
5. **Redis Backend** - Distributed caching layer

## Migration Notes

The simplified architecture removes complexity while preserving all core functionality:

- Queries go directly to L3 (pgvector)
- No frame pre-assembly overhead
- Simpler codebase, easier to debug
- Can add L2 optimization later without breaking changes

## Testing

Run tests:

```bash
pytest tests/compiler/  # Compiler pipeline tests
pytest tests/serving/   # L3 search tests
pytest tests/api/       # API integration tests
```

## Deployment

1. PostgreSQL with pgvector extension
2. LM Studio for LLM stages (atomize, distill, link)
3. Sentence-transformers for embeddings
4. FastAPI backend on port 8001
5. React frontend on port 5173

---

**Bottom Line:** L3-only architecture proves the core thesis (atoms + bitmask access) with minimal complexity. L2 caching can be added later as a performance optimization.
