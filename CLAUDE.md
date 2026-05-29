# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # install deps
uv run pytest                  # all tests
uv run pytest tests/test_db.py # single file
uv run pytest -k test_supersession_links_atoms  # single test
uv run lattice             # run MCP server (requires env vars)
```

Required env vars for running the server: `LLM_PROVIDER`, `LLM_MODEL`, `LATTICE_DIR`. `LLM_API_KEY` is required for all providers except `ollama` — `complete()` raises `EnvironmentError` eagerly if missing.

## Architecture

The current pipeline is: **ingest → select → synthesize**, each backed by an LLM call via `lattice/llm.py`. The product direction is local-first lattice: source-aware ingest, provenance, deterministic graph sidecars, graph-seeded selection, and optional enrichment that never blocks local querying.

```
server.py          MCP stdio entrypoint. Owns one shared LatticeDB instance.
lattice/
  llm.py           Thin litellm wrapper. Reads LLM_PROVIDER/LLM_MODEL/LLM_API_KEY from env.
  models.py        Atom pydantic model + markdown serialization (python-frontmatter).
  db.py            File-based store: one .md file per atom in LATTICE_DIR. BM25 search.
                   subjects.json is a subject→atom_id index for O(1) supersession lookups.
                   Holds a LatticeGraph instance; updated on every write/supersede/preload.
  graph.py         Heterogeneous graph index (networkx MultiDiGraph). Writes committed
                   sidecars to LATTICE_DIR/graph/{nodes.jsonl,edges.jsonl,manifest.json}.
                   Node types: atom:<id>, source:<id>, segment:<cid>:<sid>, subject:<norm>.
                   Edge types: source_contains_segment, segment_contains_atom,
                   atom_has_subject, same_subject_as, same_hash, supersedes.
  parsers/         Source-aware pre-ingest segmentation. `infer_source_type()` detects chat/
                   markdown/code. `parse()` returns list[Segment] with role, context, span.
                   chat.py preserves turn windowing + role field. markdown.py splits on headings.
  ingest.py        Segments source via parsers/, then LLM extracts atoms per segment,
                   then checks supersession per atom.
  selection.py     BM25 pre-filter (top_k=20) → LLM re-ranks → recommendation cap (max 5
                   kind=recommendation slots, tunable via LATTICE_RECOMMENDATION_CAP) → atom dicts.
  synthesis.py     LLM generates prose answer from atom dicts. Uses SYNTHESIS_MODEL env var
                   (falls back to LLM_MODEL). Ollama path uses OpenAI-compat client with
                   num_ctx=4096 and tool calls for date_diff + sum_numbers.
```

### Product roadmap guardrails

- Keep architecture local-first: no hosted service, no required daemon, no external DB.
- Keep atoms human-readable and git-trackable.
- Treat LongMemEval as an eval yardstick only; do not add benchmark-shaped hacks to product paths.
- Prefer provenance fields and graph edges over mutating atom content for retrieval.
- Query paths should use committed snapshots and should not wait for active ingest/enrichment.
- Expensive relation enrichment, embeddings, and hub labeling must remain optional, especially for Ollama users.

### Key data flow details

**Supersession** (in `ingest.py`): when a new atom has the same subject as an existing one, an LLM call decides if it supersedes. Fast path uses `subjects.json`; slow path scans files (handles hand-edited atoms). Superseded atoms stay on disk with `is_superseded=true` and bidirectional links (`superseded_by` / `supersedes`).

**LLM calls**: all go through `lattice.llm.complete(messages)`. Tests mock this at `lattice.ingest.complete`, `lattice.selection.complete`, `lattice.synthesis.complete` — patch the module-level name, not `lattice.llm.complete`.

**Atom storage**: every atom is a `.md` file with YAML frontmatter. `LatticeDB` has an in-memory cache (`_atom_cache`). Cache is per-instance; `server.py` reuses one instance per process.

**BM25**: built fresh on each `db.search()` call from all non-superseded atoms. No persistent BM25 index.

**Graph sidecars**: `LatticeGraph` writes `LATTICE_DIR/graph/` on every atom write. `db.preload()` loads from sidecars if manifest atom_count matches; otherwise rebuilds. Access via `db.graph`. Selection uses BFS over graph edges to expand evidence packs from BM25 seeds.

This is current MVP behavior, not the target product shape. Roadmap priorities in `lattice/eval/PRIORITIES.md` track next steps.

### Test conventions

All tests mock LLM via `unittest.mock.patch`. Ingest responses mock two calls per atom: first the extraction JSON, then the supersession reply (`"null"` or an atom_id string). Use `tmp_path` fixture for isolated `LatticeDB` instances.
