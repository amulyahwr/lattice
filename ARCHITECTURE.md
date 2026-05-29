# Architecture

lattice-mcp is a local-first MCP server that gives AI coding assistants persistent, structured memory. Raw text is decomposed into typed, timestamped **atoms** and stored as markdown files. A graph index connects atoms through provenance, subject, and supersession edges so retrieval can navigate context instead of scanning a flat folder.

---

## Pipeline

```
lattice_ingest(source, metadata)
        │
        ▼
   Segmentation          lattice/parsers/ — infer_source_type() detects chat/markdown/code;
                         parse() returns list[Segment] with role, context, span fields.
                         chat.py: window by turn count, role field set when window is
                         single-role. markdown.py: split on headings, heading in context.
        │
        ▼
   LLM Extraction        source-type-aware prompt (chat/markdown/code addenda);
                         one atom per fact: subject, kind, content, valid_from/until;
                         chat: User turns → facts/events/preferences;
                         Assistant turns → kind=recommendation only when a specific
                         proper noun (brand/venue/person/title) is named for this user;
                         relative dates resolved to ISO dates using observed_at as reference
        │
        ▼
   Dedup + Supersession  skip exact hash matches; fuzzy subject match via rapidfuzz
                         token_sort_ratio (threshold=80, env-tunable via
                         LATTICE_SUBJECT_FUZZY_THRESHOLD); LLM decides if candidate supersedes
        │
        ▼
   LatticeDB.write()     atomic write to LATTICE_DIR/<atom_id>.md
        │
        ▼
   LatticeGraph.add()    incremental update → graph/nodes.jsonl + edges.jsonl + manifest.json


lattice_select(query, as_of)
        │
        ├── retrieval_mode=select (default) ──────────────────────────────────
        │        │
        │        ▼
        │   BM25 search           top-20 non-superseded atoms scored on subject+content
        │        │
        │        ▼
        │   Graph BFS expansion   bounded BFS (depth=4, max=60) through committed
        │                         graph snapshot — traverses segment, source, subject,
        │                         supersedes, same_hash edges
        │        │
        │        ▼
        │   Collapse + filter     drop superseded; deduplicate by normalized hash;
        │                         apply as_of temporal filter;
        │                         recommendation cap: max 5 kind=recommendation
        │                         (tunable via LATTICE_RECOMMENDATION_CAP);
        │                         kind fallback: if primary_kind absent, scan all
        │
        └── retrieval_mode=llm_filter ───────────────────────────────────────
                 │
                 ▼
            select()         BM25 + session probe + graph BFS → candidate atoms
                 │
                 ▼
            Coarse LLM filter   subject + kind + observed_at only (~600 tokens);
                                _AtomSelectionCoarse: n_selected ge=8 le=25,
                                atom_ids min_length=8 max_length=25 (grammar-enforced);
                                up to 2 retries; fallback to candidates[:20]
                 │
                 ▼
            Fine LLM filter     full content (~1800 tokens);
                                _AtomSelectionFine: n_selected ge=5 le=15,
                                atom_ids min_length=5 max_length=15 (grammar-enforced);
                                up to 2 retries; fallback to coarse shortlist if <5 valid
                 │
                 ▼
            FilterResult(atoms, debug)   debug: n_candidates, n_coarse, n_fine,
                                         coarse_fallback, fine_fallback
        │
        ▼
   Return atom dicts     with full provenance fields (SelectionResult wrapper for agent mode)


lattice_answer(query, atom_ids?, as_of)
        │
        ├── atom_ids provided → read atoms directly from LatticeDB
        │
        └── no atom_ids → run lattice_select first
                │
                ▼
           Synthesis agent  tool-calling agent loop (raw OpenAI-compat API, up to 5 rounds);
                            date_diff(date1, date2) tool for exact date arithmetic;
                            sum_numbers(numbers[]) tool for exact numeric aggregation;
                            query_date passed as agent's "today" reference
```

---

## Module Map

| Module | Role |
|--------|------|
| `server.py` | MCP stdio entrypoint. Owns one shared `LatticeDB` instance per process. Routes `lattice_ingest`, `lattice_select`, `lattice_answer` tool calls. |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared low-level helpers: `_normalized_subject()`, `_write_json_atomic()`. |
| `lattice/parsers/` | Source-aware segmentation. `infer_source_type()` detects chat/markdown/code. `parse()` returns `list[Segment]` (frozen dataclass with `text`, `role`, `source_type`, `context`, `start`, `end`). `chat.py` handles windowed turn parsing with role tagging. `markdown.py` splits on headings. |
| `lattice/ingest.py` | Segments source via `parsers/` → LLM extracts atoms per segment → dedup + supersession check → write to DB. |
| `lattice/selection.py` | `select()` — BM25 top-k seeds → graph BFS (depth=4, max=60) → collapse superseded/duplicates → recommendation cap → kind fallback. Returns raw candidate atoms. `select_llm_filter()` — calls `select()` then applies two-stage LLM filter: coarse (subject+kind, `_AtomSelectionCoarse` ge=8 le=25) → fine (full content, `_AtomSelectionFine` ge=5 le=15); Pydantic constraints grammar-enforced by ollama; falls back to previous stage on LLM failure; returns `FilterResult(atoms, debug)`. Model from `SELECTION_MODEL`, context window from `SELECTION_NUM_CTX`. Falls back to `evidence_pack()` if graph is empty. |
| `lattice/query.py` | `parse_query()` — detect query shape (`temporal`/`preference`/`recommendation`/`factual`) and `primary_kind` from question text. Returns `QueryIntent`. Used by both `select()` and `select_agent()`. |
| `lattice/synthesis.py` | Tool-calling agent using raw OpenAI-compat SDK. Model read from `SYNTHESIS_MODEL` env var (falls back to `LLM_MODEL`, default `qwen3.5:4b`). Exposes `date_diff` (date arithmetic) and `sum_numbers` (numeric aggregation) tools. Returns `SynthesisResult(answer, raw_response, tool_calls)`. Supports `ollama` and `openai` providers. **Gap:** `anthropic` provider not yet supported — raises `NotImplementedError`. |
| `lattice/llm.py` | Thin litellm wrapper. Single `complete(messages) → str` interface. Used by ingest, selection, and supersession — not synthesis. Reads `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` from env. Supports `anthropic`, `openai`, `ollama`. `LLM_API_KEY` required for non-ollama providers. |

---

## Atom Data Model

Every atom is a `.md` file with YAML frontmatter:

```
atom_id              UUID (stable, used in supersession links and lattice_answer calls)
kind                 free-form: fact | event | decision | preference | belief | …
source               free-form: user | document | chat | code | …
subject              canonical noun phrase — normalized for subject index and graph edges
content              self-contained statement of the fact
valid_from/until     optional date bounds; as_of queries exclude atoms outside window
is_superseded        true when a newer atom has replaced this one
supersedes           atom_id of the older version this atom replaced
superseded_by        atom_id of the newer version that replaced this atom
ingested_at          when the atom was written
observed_at          when the fact was observed in the source
source_id            groups all atoms from one ingest call / document
session_id           groups atoms from one conversation turn window
segment_id           chunk within a segmented source (s0, s1, …)
source_type          markdown | chat | code | plain
source_span          {start, end} byte offsets into original source
content_hash         SHA256 of exact content (exact dedup)
normalized_content_hash  SHA256 of lowercased word-tokenized content (fuzzy dedup)
metadata             passthrough dict from lattice_ingest caller
```

---

## Graph Index

After every atom write, `LatticeGraph` upserts nodes and edges into a `networkx.MultiDiGraph` and writes committed sidecars to `LATTICE_DIR/graph/`.

**Node types:**

| ID pattern | Represents |
|-----------|-----------|
| `atom:<atom_id>` | One per atom (including superseded) |
| `source:<source_id>` | One per unique source document / ingest batch |
| `segment:<container_id>:<segment_id>` | One per chunk; container = source_id or session_id |
| `subject:<normalized>` | One per unique normalized subject string |

**Edge types:**

| Type | Direction | Meaning |
|------|-----------|---------|
| `atom_has_subject` | atom → subject | Always present |
| `same_subject_as` | atom ↔ atom | Bidirectional; same normalized subject |
| `source_contains_segment` | source → segment | When atom has source_id + segment_id |
| `segment_contains_atom` | segment → atom | When atom has segment_id |
| `supersedes` | new atom → old atom | Written by `db.supersede()` |
| `same_hash` | atom → atom | Same `normalized_content_hash` |

**Sidecar files:**

```
LATTICE_DIR/
  graph/
    nodes.jsonl       one JSON line per node {id, type, …attrs}
    edges.jsonl       one JSON line per edge {src, dst, type, key}
    manifest.json     {version, atom_count, edge_count, built_at}
```

`preload()` loads sidecars when `manifest.atom_count` matches disk atom count; otherwise rebuilds from scratch. All writes are atomic (tempfile + rename).

---

## Key Design Invariants

- **Local-only.** No hosted service, no daemon, no external DB. Everything in `LATTICE_DIR`.
- **Human-readable atoms.** `.md` files can be hand-edited, deleted, or committed to git without breaking the server.
- **Committed snapshots.** Selection reads stable graph/BM25 snapshots; it never waits for active ingest.
- **Superseded atoms stay on disk** with `is_superseded=true` and bidirectional links. History is preserved, not deleted.
- **Expensive enrichment is optional.** Embeddings, semantic relation enrichment, and hub labeling are roadmap items that must remain off by default for Ollama users.
- **LLM calls are mockable at the module level.** Ingest/selection/supersession patch `lattice.ingest.complete` / `lattice.selection.complete`. Synthesis patches `lattice.synthesis.OpenAI` (raw OpenAI client) — not `lattice.llm.complete`.

---

## Roadmap Direction

Current state (p24-llmfilter, 76% / 79.9% task-avg LongMemEval): structured `parsers/` layer → LLM extraction with proper-noun assistant-turn rule → fuzzy supersession via rapidfuzz → BM25 seeds → session-diversity probe (pointed/expansion paths) → graph BFS expansion → recommendation cap → collapse superseded/duplicates → two-stage LLM filter (`select_llm_filter()`, `SELECTION_MODEL`, `SELECTION_NUM_CTX`) → synthesis agent (`SYNTHESIS_MODEL`) with date_diff + sum_numbers tools.

Next: multi-session aggregation — fine filter cuts atoms needed for counting totals; fix candidate is skipping fine stage for detected "how many / total" queries. Dense seed augmentation (P16) to address BM25 vocabulary mismatch. Full roadmap in `lattice/eval/PRIORITIES.md`.
