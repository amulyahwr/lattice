# Architecture

lattice is a local-first personal memory OS. Raw text is decomposed into typed, timestamped **atoms** and stored as markdown files. A persistent daemon owns all writes, watches an inbox folder for ambient ingest, and serves a local web UI for recall. A graph index connects atoms through provenance, subject, and supersession edges so retrieval can navigate context instead of scanning a flat folder.

MCP integration exposes the atom store to AI coding assistants as a read-mostly interface; the daemon remains the sole writer.

---

## Write path

All writes go through the daemon. MCP `lattice_ingest` and external callers do not write atoms directly.

```
inbox/*.txt|*.md          MCP lattice_ingest (daemon running)
        │                         │
        └──────────┬──────────────┘
                   ▼
           lattice-daemon        ← sole writer; owns LatticeDB instance
                   │
                   ▼
           ingest pipeline (below)
                   │
                   ▼
           LatticeDB.write() → atom .md files + graph sidecars
```

When the daemon is not running, `lattice_ingest` falls back to inbox drop (file written to `LATTICE_INBOX`; picked up when daemon restarts).

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


select(query, as_of)
        │
        ▼
   BM25 search           top-20 non-superseded atoms scored on subject+content
        │
        ▼
   Source-diversity      probe top-7 seeds; if all from ≤1 source →
   probe                 pointed path (7 seeds, max_atoms=14);
                         if multiple sources → expansion path
                         (all 20 seeds, max_atoms=60)
        │
        ▼
   Graph BFS expansion   bounded BFS (depth=4, max=14 or 60) through committed
                         graph snapshot — traverses segment, source, subject,
                         supersedes, same_hash edges;
                         falls back to evidence_pack() if graph is empty
        │
        ▼
   Collapse + filter     drop superseded; deduplicate by normalized hash;
                         apply as_of temporal filter;
                         recommendation cap: max 5 kind=recommendation
                         (tunable via LATTICE_RECOMMENDATION_CAP);
                         kind fallback: if primary_kind absent, scan all
        │
        ▼
   Return atom dicts     with full provenance fields


stream_synthesis(query, atoms)
        │
        ▼
   Tool loop             blocking rounds (up to 5) for date_diff / sum_numbers;
                         only runs if model calls a tool — most queries skip this
        │
        ▼
   Streaming LLM call    OpenAI-compat API, stream=True; yields token chunks
        │
        ▼
   SSE events            {"type":"token","text":"..."} per chunk →
                         {"type":"citations_applied","answer":"..."} →
                         {"type":"done"}
```

---

## Module Map

| Module | Role |
|--------|------|
| `lattice/daemon.py` | Persistent daemon. Sole writer to `LatticeDB`. Watches `LATTICE_INBOX` via `watchdog`; ingests `.txt`/`.md` files on drop, moves to `processed/`. Binds a Unix domain socket (`LATTICE_SOCK`) for IPC. Runs the FastAPI web server inline via `uvicorn` on `LATTICE_WEB_PORT` (default 7337). Manages PID file and graceful shutdown on SIGTERM/SIGINT. CLI: `lattice-daemon` (start), `lattice-daemon status`. |
| `lattice/client.py` | `DaemonClient` — thin IPC client. Connects to `LATTICE_SOCK`, sends JSON-newline messages (`ping`, `ingest`), returns responses. Used by `server.py` when daemon is running. Falls back gracefully when socket is absent. |
| `lattice/web/app.py` | FastAPI web UI. Routes: `GET /` (chat + recent atoms HTML), `POST /api/query` (streaming SSE synthesis with citations), `GET /api/atoms/recent` (last N atoms). Read-only — reads `LatticeDB` directly from disk. |
| `lattice/config.py` | `Config` dataclass. Reads all path/network env vars (`LATTICE_DIR`, `LATTICE_INBOX`, `LATTICE_SOCK`, `LATTICE_WEB_HOST`, `LATTICE_WEB_PORT`) in one place. LLM vars remain in `llm.py`. |
| `server.py` | MCP stdio entrypoint. Routes `lattice_ingest` (inbox drop or `DaemonClient`), `lattice_select`, `lattice_answer`. Read-only for select/answer. |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared low-level helpers: `write_file_atomic()` (canonical tempfile+rename utility); `_write_json_atomic()` delegates to it. |
| `lattice/parsers/` | Source-aware segmentation. `infer_source_type()` detects chat/markdown/code. `parse()` returns `list[Segment]` (frozen dataclass with `text`, `role`, `source_type`, `context`, `start`, `end`). `chat.py` handles windowed turn parsing with role tagging. `markdown.py` splits on headings. |
| `lattice/ingest.py` | Segments source via `parsers/` → LLM extracts atoms per segment → dedup + supersession check → write to DB. |
| `lattice/selection.py` | `select()` — BM25 top-k → source-diversity probe → graph BFS (depth=4, max=14 or 60) → collapse superseded/duplicates → recommendation cap → kind fallback. Returns atom dicts. Falls back to `evidence_pack()` if graph is empty. |
| `lattice/query.py` | `parse_query()` — detects query shape (`temporal`/`preference`/`recommendation`/`factual`) and `primary_kind`. Returns `QueryIntent`. Used by `select()`. |
| `lattice/synthesis.py` | Tool-calling agent via raw OpenAI-compat SDK. Model from `SYNTHESIS_MODEL` env var (falls back to `LLM_MODEL`). Tools: `date_diff`, `sum_numbers`. `synthesize()` → `SynthesisResult`. `stream_synthesis()` → SSE generator used by the web UI. Supports `ollama` and `openai`; Anthropic via `LLM_PROVIDER=openai` + `LLM_BASE_URL=https://api.anthropic.com/v1`. |
| `lattice/llm.py` | Thin litellm wrapper. `complete(messages) → str`. Used by ingest, selection, supersession — not synthesis. Reads `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL`. |

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

- **Local-only.** No hosted service, no external DB. Everything in `LATTICE_DIR`.
- **Daemon is the sole writer.** Only the daemon writes atom files and graph sidecars. MCP server and web UI are read-only clients. Atom writes are atomic (tempfile + rename), making reads always safe without locking.
- **Human-readable atoms.** `.md` files can be hand-edited, deleted, or committed to git without breaking the server.
- **Committed snapshots.** Selection reads stable graph/BM25 snapshots; it never waits for active ingest.
- **Superseded atoms stay on disk** with `is_superseded=true` and bidirectional links. History is preserved, not deleted.
- **Expensive enrichment is optional.** Embeddings, semantic relation enrichment, and hub labeling must remain off by default for Ollama users.
- **LLM calls are mockable at the module level.** Ingest/selection/supersession patch `lattice.ingest.complete` / `lattice.selection.complete`. Synthesis patches `lattice.synthesis._make_client` — not `lattice.llm.complete`.

---

## Roadmap

**Phase 1 complete.** Daemon, inbox watcher, IPC protocol, MCP read-only refactor, web UI (chat + recent atoms), streaming synthesis, source citations, Anthropic via OpenAI-compat.

**Phase 2 next:** multi-device sync (mDNS discovery, Ed25519 device pairing, mTLS delta sync) and Homebrew install + first-run setup wizard.
