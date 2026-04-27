# Lattice Architecture

**Date:** 2026-04-27
**Status:** Implemented

## Overview

Lattice is an **L3-only architecture** — compiled context atoms served through multi-hypothesis pgvector search with bitmask access control. The core thesis: **compile knowledge once at ingest, serve fast at query time.**

---

## Current Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         COMPILER PIPELINE                            │
│  Ingest → Atomize+Distill → Embed → Link+Tag (parallel) →          │
│           Index → Cross-link → Consolidate                          │
└─────────────────────────────────────────────────────────────────────┘
                                ↓
                      ┌─────────────────┐
                      │   Atom Storage  │
                      │   (PostgreSQL)  │
                      │   + pgvector    │
                      └─────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────────┐
│                        SERVING LAYER (L3)                            │
│                                                                      │
│  Query → process_query (k=3 hypotheses + canonical)                 │
│        → canonical pre-filter (subject + period, SQL-level)         │
│        → pgvector search × k (one per hypothesis)                   │
│        → RRF fusion (Reciprocal Rank Fusion)                        │
│        → confidence × freshness re-scoring                          │
│        → [optional LLM re-rank]                                     │
│        → token budget trim → return atoms                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Compiler Pipeline (`backend/compiler/pipeline.py`)

**Stages:**

Stages 1+2 are merged into a single LLM call per chunk. Stages 4+5 run in parallel.

1+2. **Extract** — One LLM call per chunk: atomize raw text into atomic propositions + distill to concise canonical form
3. **Embed** — Dense vectors via sentence-transformers (384-dim)
4. **Link** — LLM identifies within-source relationships between atoms (parallel with Tag)
5. **Tag** — Bitmask access control + domain tagging (parallel with Link)
6. **Index** — Write to DB with Tier 1 exact dedup (content_hash). Writes `canonical_subject` and `canonical_period` as normalized indexed columns alongside the full `canonical` JSONB blob.
7. **Cross-link** — LLM finds relationships between new atoms and semantically similar atoms from previously ingested sources (domain-filtered, cosine similarity ≥ 0.5)
8. **Consolidate** — Near-duplicate detection via pgvector (cosine ≥ 0.85) + LLM relationship classification; preserves provenance in `atom_versions`

**Deduplication:**

- **Tier 1 — content_hash**: Exact SHA-256 match on distilled text; blocks true re-ingestion (one batch SELECT)
- **Stage 8 — Consolidation**: Finds near-duplicate existing atoms (cosine distance ≤ 0.15); LLM classifies each pair and takes action:
  - `confirms` — same fact, different wording → boost existing atom confidence; emit `confirms` link; write version record
  - `subsumes` — new atom is a superset → archive existing (mark `is_superseded`); emit `subsumes` link
  - `supersedes` — fact has evolved → archive existing; emit `supersedes` link; record transition in `atom_versions`
  - `contradicts` — atoms disagree → both survive; emit `contradicts` link on both; flagged for review
  - `distinct` — similar topic, genuinely different → no action

Near-duplicates are preserved with typed links rather than silently discarded. Provenance is maintained in the `atom_versions` ledger.

---

### 2. Data Model (`backend/models/atoms.py`)

**Atom** — Core knowledge unit

- `content` — Distilled, token-efficient text
- `kind` — fact | decision | metric | event | procedure
- `dense_vec` — Embedding vector (384-dim)
- `access_mask` — 64-bit bitmask for access control
- `domain[]` — Domain tags
- `canonical` — Full structured form JSONB: `{subject, predicate, object, value, unit, period}`
- `canonical_subject` — Extracted, normalised subject (indexed column; `"Revenue Growth"` → `"revenue growth"`)
- `canonical_period` — Extracted, normalised period (indexed column; `"Q2-2024"` → `"Q2 2024"`)
- `links[]` — Typed edges: `confirms`, `subsumes`, `supersedes`, `contradicts`, cross-source relations
- `valid_from` / `valid_until` — Time-bounded fact validity window
- `is_superseded` — True when a newer atom replaces this one; excluded from L3 search
- `superseded_by` — FK to the superseding atom
- `confidence` — Boosted (+0.5) each time another atom confirms the same fact

`canonical_subject` and `canonical_period` are denormalised from the JSONB blob and indexed separately for efficient SQL pre-filtering. The JSONB blob is preserved as-is for display and full-field access.

**AtomVersion** — Append-only version ledger

- Written on atom creation (`reason="initial"`) and on every consolidation transition
- `valid_from` / `valid_until` — The time window this version was the current state
- `reason` — `initial` | `confirmed` | `superseded`
- `triggered_by_atom_id` — Which atom caused the state transition

**AgentProfile** — Agent identity

- `role_mask` — 64-bit bitmask for access control
- `max_tokens` — Token budget per query
- `domains[]` — Focus domains

**Source** — Data source metadata
**AtomSource** — Many-to-many join (atoms can come from multiple sources)
**AccessLog** — Audit trail

---

### 3. Query Processor (`backend/compiler/query_processor.py`)

Converts a raw query into embedding-ready inputs before search. Two responsibilities:

**HyDE (Hypothetical Document Embeddings):**
Generates `k=3` diverse declarative statements ("hypotheses") written as if a matching atom already exists in the KB. Each hypothesis covers a different angle of the query (activity/event, metric/quantity, trend/decision). Eliminates the question-vs-statement embedding mismatch that degrades single-embedding search.

Rules enforced:
- No hallucinated entity names, dollar amounts, or specific values not in the query
- Generic language so each hypothesis can match any relevant atom
- Fallback to `[raw_query]` on any LLM failure — never raises

**Canonical extraction:**
Extracts `subject` and `period` from the query in a standard normalised form:
- `normalize_subject("Revenue Growth")` → `"revenue growth"` (lowercase + strip)
- `normalize_period("q2-2024")` → `"Q2 2024"`, `"second quarter"` → `"Q2"`

These are used as SQL pre-filters in `_search_one` before cosine search runs.

**Output:** `ProcessedQuery(hypotheses: list[str], canonical: dict | None)`

---

### 4. Serving Layer (`backend/serving/`)

**`router.py`** — Query routing

- `smart_search=True` (default) — calls `process_query()` to get k hypotheses + canonical
- `smart_search=False` — skips LLM call, embeds raw query directly (fast path)
- `deep_rerank=False` (default) — uses confidence × freshness heuristic scoring
- `deep_rerank=True` — adds a second LLM pass to re-rank the shortlist by semantic relevance (+1–3s)
- `compare_context()` calls `process_query()` once and reuses hypotheses across all agents

**`l3_search.py`** — Multi-hypothesis search with RRF

Search flow per query:

```
for each hypothesis in hypotheses:
    1. SQL pre-filter: canonical_period (bidirectional ILIKE) + canonical_subject (bidirectional ILIKE)
       → atoms with no canonical fields (events, decisions) always pass through
    2. pgvector cosine distance → top_k rows

RRF fusion:
    atom_score += 1 / (60 + rank)  for each list it appears in
    dedup by atom_id, keep row with best (lowest) cosine distance

Heuristic re-scoring:
    final_score = best_cosine × confidence_weight × freshness_weight
    confidence_weight = 1 + log(min(confidence, 3.0)) / 4  [1.0x→1.27x]
    freshness_weight  = exp(-0.005 × age_days)             [half-life ~139 days]

[Optional LLM re-rank]:
    send top candidates + raw query to LLM; receive 1–10 scores per candidate
    re-sort by LLM score; fall back to heuristic order on any error
```

`is_superseded=True` atoms are excluded at the SQL level (not post-filtered).

**Canonical pre-filter design:**

Both `canonical_period` and `canonical_subject` use bidirectional ILIKE:
- `stored ILIKE '%q2%'` → stored `"Q2 2024"` matches query `"Q2"`
- `'q2 2024' ILIKE '%' || stored || '%'` → stored `"Q2"` matches query `"Q2 2024"`
- `OR canonical_period IS NULL` → atoms without canonical fields always survive

This means a metric atom with the wrong period (`"Q3"`) is excluded before cosine search, but a non-metric event atom (no `canonical_period`) always passes through.

---

### 5. Consolidator (`backend/compiler/consolidator.py`)

Stage 8 of the pipeline. Runs after new atoms are indexed and cross-linked.

**Candidate selection**: For each new atom, pgvector search finds existing atoms within cosine distance ≤ 0.15 (similarity ≥ 0.85). Up to 5 candidates per new atom. Superseded atoms and the current ingest batch are excluded.

**LLM classification**: All pairs are batched into a single LLM call. The LLM classifies each pair using the relation vocabulary above.

**Actions**:
- `confirms` — `existing.confidence += 0.5`; write version record; add `confirms` link on new atom
- `subsumes` / `supersedes` — `existing.is_superseded = True`; set `existing.superseded_by`; close `existing.valid_until`; write `AtomVersion` record; add typed link on new atom
- `contradicts` — add `contradicts` link on both atoms (both retained for human review)
- `distinct` — no action; atoms coexist independently

---

### 6. Cross-Source Linking (`backend/compiler/linker.py`)

Cross-source linking runs as Stage 7 of the pipeline immediately after new atoms are indexed.

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

**Candidate selection**: Per new atom — pgvector cosine similarity search filtered by expanded domains, threshold ≥ 0.5, top-K=5, deduplicated across all new atoms.

**Admin re-link**: `POST /admin/relink` re-runs cross-source linking across all existing sources, appending new links without overwriting existing ones.

---

### 7. API Routes

```
POST   /v1/sources/ingest           Ingest a document (runs 8-stage compiler)
GET    /v1/sources/                 List sources
GET    /v1/sources/{id}/atoms       List atoms for a source
DELETE /v1/sources/{id}             Delete source

POST   /v1/context/query            Query context (multi-hypothesis L3 search)
POST   /v1/context/compare          Compare context across multiple agents

POST   /v1/agents                   Register agent
GET    /v1/agents                   List agents
PATCH  /v1/agents/{id}              Update agent profile
DELETE /v1/agents/{id}              Delete agent

GET    /v1/atoms/graph              Full knowledge graph
GET    /v1/atoms/{id}/neighborhood  Single atom neighborhood (1-hop)

GET    /admin/stats                 System stats
GET    /admin/activity              Recent query activity
POST   /admin/relink                Re-run cross-source linking

GET    /audit/log                   Paginated access log
GET    /audit/stats                 Access control statistics
```

---

## Performance Characteristics

| Operation | Latency | Notes |
|---|---|---|
| Bitmask access check | Sub-millisecond | Bitwise AND, no DB join |
| pgvector search (per hypothesis) | ~15–30ms | Indexed cosine distance |
| L3 query (smart_search=True) | ~100–200ms | 1 LLM call + k×pgvector |
| L3 query (smart_search=False) | ~50ms | Embed only + 1×pgvector |
| L3 query (deep_rerank=True) | ~1–3s additional | Optional second LLM pass |
| Ingest compile time | ~5–15s/doc | 3 LLM calls + embed + index |

---

## Key Features

✅ **Atom-based knowledge representation**
✅ **Bitmask access control** (sub-millisecond filtering)
✅ **Agent-aware context** (same query, different results per agent)
✅ **Compiler pipeline** (expensive work at ingest time)
✅ **Tier 1 deduplication** (exact content_hash re-ingest guard)
✅ **Stage 8 consolidation** (near-duplicate detection + LLM relationship classification)
✅ **Atom versioning** (append-only `atom_versions` ledger)
✅ **Supersedes / contradicts / confirms links** (provenance-preserving knowledge evolution)
✅ **is_superseded filter** (stale atoms never appear in search results)
✅ **Multi-hypothesis HyDE search** (k=3 diverse hypotheses, no kind classification)
✅ **RRF fusion** (atoms appearing across multiple hypothesis shortlists are surfaced)
✅ **Canonical pre-filter** (period + subject as indexed SQL pre-filters; bidirectional ILIKE)
✅ **Period + subject normalisation** (consistent format at write and query time)
✅ **Optional LLM re-ranker** (deep_rerank flag; falls back gracefully)
✅ **Audit logging** (every access tracked)
✅ **Cross-source relationship linking** (domain-aware, similarity-gated)
✅ **Token budget management**

---

## Future Enhancements

1. **Temporal query API** — `?as_of=<ISO-timestamp>` on `/v1/context/query`; data already in `atom_versions`
2. **Graph-traversal serving** — `?hops=1` parameter; seed via pgvector, expand via `atom.links[]`
3. **Async compiler workers** — decouple ingest from HTTP request lifecycle
4. **L2 Frame Cache** — pre-assembled atom bundles for hot query paths
5. **Agent session memory** — recency-weighted retrieval per agent across sessions
6. **Canonical value/unit columns** — add indexed `canonical_value` (Float) and `canonical_unit` (String) for numeric range filtering on metric atoms

---

## Project Structure

```
lattice/
├── backend/
│   ├── compiler/
│   │   ├── pipeline.py          # 8-stage compiler orchestrator
│   │   ├── atomizer.py          # Text → Atoms (LLM)
│   │   ├── distiller.py         # Raw → Distilled content (LLM)
│   │   ├── linker.py            # Atom-to-atom linking (LLM)
│   │   ├── tagger.py            # Access mask + domain tagging (LLM)
│   │   ├── consolidator.py      # Near-duplicate detection + classification (LLM)
│   │   ├── query_processor.py   # HyDE hypotheses + canonical extraction (LLM)
│   │   └── llm_client.py        # LM Studio API client
│   ├── serving/
│   │   ├── router.py            # Query routing + token trim + access log
│   │   └── l3_search.py         # Multi-hypothesis pgvector search + RRF
│   ├── models/
│   │   ├── atoms.py             # Atom, AgentProfile, Source, AccessLog
│   │   └── database.py          # DB setup
│   ├── api/                     # FastAPI routes
│   ├── connectors/              # PDF, text/markdown connectors
│   └── engine/
│       └── embeddings.py        # Sentence-transformers
└── tests/
    ├── api/                     # API integration tests
    ├── compiler/                # Compiler unit tests (incl. query_processor)
    └── serving/                 # L3 search + router tests
```

---

## Deployment

1. PostgreSQL with pgvector extension
2. LM Studio for all LLM stages (atomize, distill, link, tag, consolidate, query_processor, re-ranker)
3. Sentence-transformers for embeddings
4. FastAPI backend on port 8001
5. React frontend on port 5173

---

**Bottom Line:** Compile once, serve fast. The search layer generates multiple diverse hypotheses, pre-filters by canonical structure, fuses ranked lists via RRF, and re-scores by confidence and freshness — all before an optional LLM re-rank pass. The result is a search system that improves result quality without sacrificing the simplicity of the L3-only architecture.
