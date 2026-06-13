# Recall Pipeline

When you ask Lattice a question, it runs three stages: **select** → **synthesize**. Selection is entirely LLM-free. Synthesis is one streaming LLM call.

## Overview

```
your question
     │
     ▼
┌─────────────────────────────────────────────────────┐
│  SELECTION  (zero LLM calls)                        │
│                                                     │
│  1. BM25 text search → top-k seed atoms             │
│  2. Dense semantic search (optional) → vocab hits   │
│  3. Zero-score seed filter                          │
│  4. Source diversity probe                          │
│  5. Graph BFS expansion                             │
│  6. Filter superseded atoms                         │
│  7. Re-rank by decay + quality_score                │
└─────────────────────────────────────────────────────┘
     │
     │  atom pack (ranked list of atom dicts with provenance)
     ▼
┌─────────────────────────────────────────────────────┐
│  SYNTHESIS  (1 LLM call)                            │
│                                                     │
│  Streaming prose answer with [1][2][3] citations    │
│  Date arithmetic via tool call                      │
│  Answer + atom pack → web UI                        │
└─────────────────────────────────────────────────────┘
```

## Selection in detail

### 1. BM25 seeds

BM25 scores every atom in the store against your query. The top-k (default 10) atoms become the initial seed set.

BM25 strips possessive apostrophes before tokenizing: `"John's"` → `"John"`, so queries like "John's preference" still find atoms about John.

### 2. Dense semantic search (optional)

If `LATTICE_DENSE_SEEDS` is set (requires `uv sync --group semantic`), dense embeddings via `BAAI/bge-small-en-v1.5` add candidates that BM25 misses:

- **Vocabulary mismatch**: "gym" ↔ "workout", "car" ↔ "vehicle"
- **Spelling tolerance**: `"pstgres"` embeds close to `"postgres"` — typos find their targets
- Top-20 cosine hits merged with BM25 seeds, re-sorted by time decay after merge (except for temporal queries)

### 3. Zero-score seed filter

Seeds that scored exactly 0 against the BM25 query are dropped. Only applies when `LATTICE_SEED_MIN_SCORE` is set.

### 4. Source diversity probe

Ensures the seed set doesn't consist entirely of atoms from one source document. Replaces over-represented sources with the next best atoms from other sources.

### 5. Graph BFS expansion

From each seed atom, BFS traverses edges to collect related atoms:

- `same_subject_as` → other atoms on the same topic
- `supersedes` chain → temporal queries get the full history
- `segment_contains_atom` → sibling atoms from the same document section
- `episode_contains_atom` → atoms from the same capture session

The resulting expanded set typically includes 2–5× the original seed count.

### 6. Filter superseded atoms

Any atom with `is_superseded=true` is removed from the pack before synthesis. The synthesis LLM never sees stale facts, even if graph BFS traversed into them.

### 7. Re-rank by decay + quality_score

Atoms are sorted by `quality_score × time_decay`. `time_decay` is a simple exponential: newer atoms rank higher. This produces the final evidence pack.

## Synthesis

One streaming LLM call:

```
System: You are a personal memory assistant. Answer using only the provided atoms.
        Cite each fact with [n] where n is the atom's position in the list.

User: [atom 1]
      [atom 2]
      ...
      Question: what coffee do I like?
```

The model streams tokens to the web UI via SSE. `[1]`, `[2]` citations in the output are linked to atom source chips below the answer.

Synthesis uses `SYNTHESIS_MODEL` (falls back to `LLM_MODEL`).

## Multi-turn conversation

For follow-up queries, `conversation.py` detects anaphoric references:

```
User: what coffee do I like?
Lattice: You prefer Ethiopian dark roast.
User: why did I switch to that?   ← anaphoric follow-up
```

`is_followup("why did I switch to that?")` returns `True` (pronoun + short query, no proper noun).

`reformulate(query, history, cfg)` makes one LLM call to rewrite it as:
> "Why did I switch to Ethiopian dark roast coffee?"

The reformulated query goes into the selection pipeline. The original query is preserved for display.

## Intent detection: recall vs capture

Before entering the recall pipeline, the web UI and Telegram bot call `classify_intent(question)`:

- Fast path: ends with `?` → `"recall"`
- LLM path: one call → `"capture"` or `"recall"`
- Fallback: `"recall"`

If `"capture"`, the text goes through `reformulate_capture()` (pronoun resolution into a self-contained assertion) → `ingest()` instead.

## Tracing (optional)

Set `LATTICE_TRACE=true` to write a per-query trace to `LATTICE_DIR/traces.jsonl`:

```json
{
  "ts": "2025-11-14T09:15:00Z",
  "query_hash": "sha256:...",
  "bm25_seed_count": 8,
  "dense_seed_count": 4,
  "bfs_expanded_count": 23,
  "final_atom_count": 15,
  "synthesis_latency_ms": 1420,
  "model": "gemma4"
}
```

Query text is hashed, not stored. Atom IDs are stored but not content.
