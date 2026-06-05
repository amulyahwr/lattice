# Architecture

lattice is a local-first personal memory OS. Raw text is decomposed into typed, timestamped **atoms** and stored as markdown files. A persistent daemon owns all writes, watches an inbox folder for ambient ingest, and serves a local web UI for recall. A graph index connects atoms through provenance, subject, and supersession edges so retrieval can navigate context instead of scanning a flat folder.

MCP integration exposes the atom store to AI coding assistants as a read-mostly interface; the daemon remains the sole writer.

---

## Write path

All writes go through the daemon. No caller writes atoms directly.

```
inbox/*.txt|*.md   MCP lattice_ingest   MCP lattice_capture   POST /api/ingest
        │                  │                     │                    │
        └──────────────────┴─────────────────────┴────────────────────┘
                                        │
                                        ▼
                                lattice-daemon        ← sole writer; owns LatticeDB instance
                                        │
                                        ▼
                                ingest pipeline (below)
                                        │
                                        ▼
                                LatticeDB.write() → atom .md files + graph sidecars
```

When the daemon is not running: MCP tools and `POST /api/ingest` fall back to inbox drop (file written to `LATTICE_INBOX`; picked up when daemon restarts).

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


select(query, as_of)          ← production path used by web UI, MCP server
        │
        ▼
   _retrieve()           BM25 top-20 (scored) → drop zero-score seeds
        │                 (LATTICE_SEED_MIN_SCORE) → source-diversity probe →
        │                 graph BFS; pointed path (7 seeds, max=14) or
        │                 expansion path (all seeds, max=60); collapse
        │                 superseded/dups; recommendation cap (max 5);
        │                 kind fallback; optional BFS rescore by BM25
        │                 (LATTICE_BFS_RESCORE)
        │
        ▼
   Return atom dicts     with full provenance fields; 0 LLM calls


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
| `lattice/daemon.py` | Persistent daemon. Sole writer to `LatticeDB`. Watches `LATTICE_INBOX` via `watchdog`; ingests `.txt`/`.md` files on drop, moves to `processed/`. On startup, drains any pre-existing inbox files (`_drain_inbox`) — processes queued messages written while daemon was down. After draining a `telegram-{chat_id}-{uuid}.txt` file, sends a follow-up reply to the user via Telegram HTTP API (`_notify_telegram`) using `LATTICE_TELEGRAM_TOKEN`. Binds a Unix domain socket (`LATTICE_SOCK`) for IPC. Runs the FastAPI web server inline via `uvicorn` on `LATTICE_WEB_PORT` (default 7337). Manages PID file and graceful shutdown on SIGTERM/SIGINT. CLI: `lattice-daemon` (start), `lattice-daemon status`. |
| `lattice/cli.py` | `lc` entry point. `lc "decided X because Y"` captures via `DaemonClient().ingest()` over Unix socket; exits 1 with actionable message if daemon not running. `lc status` reads `LatticeDB` directly (no daemon needed) and prints memory count. |
| `lattice/telegram_bot.py` | Telegram capture bot. Runs as an **independent** launchd service (`dev.lattice.telegram.plist`) — not a daemon subprocess. Polls Telegram via `python-telegram-bot` (`bootstrap_retries=-1`, `timeout=30`). Accepts messages only from `LATTICE_TELEGRAM_ALLOWED_IDS`; silently drops all others. Auto-detects intent (`_classify`): question → recall, statement → capture, ambiguous → clarification prompt. Capture: calls `DaemonClient().ingest()` over Unix socket. Recall: calls `POST /api/answer` on local web server (daemon has LLM env vars; bot does not) → strips `[label][src:id]` citation markers from prose, appends `Sources:\n· label` footer. Daemon-down path: writes `telegram-{chat_id}-{uuid}.txt` to inbox; daemon drains on restart and sends follow-up reply. Commands: `/ask`, `/save`, `/status`, `/start`. Requires `uv sync --group telegram`. |
| `lattice/client.py` | `DaemonClient` — thin IPC client. Connects to `LATTICE_SOCK`, sends JSON-newline messages (`ping`, `ingest`), returns responses. `ingest(text, source_id, metadata)` passes the full metadata dict through the socket so provenance fields (`observed_at`, `session_id`, `source`, etc.) reach `ingest()` in the daemon. Used by `server.py` when daemon is running. Falls back gracefully when socket is absent. |
| `lattice/web/app.py` | FastAPI web UI. Serves static files from `lattice/web/static/` via `StaticFiles`. Routes: `GET /` → `index.html`, `POST /api/query` (streaming SSE synthesis for web UI), `POST /api/answer` (blocking JSON synthesis for Telegram bot — `{"question": "..."}` → `{"ok": true, "answer": "...", "atom_count": N}`), `GET /api/atoms/recent`, `POST /api/feedback`, `POST /api/ingest` (HTTP ingest — `source_id` + metadata pass-through, `observed_at` server-stamped; returns `503` if daemon down; bound to `127.0.0.1`). UI has "Save session" button that POSTs accumulated Q&A pairs as a conversation chunk to `/api/ingest` with `source_id="web"`. Holds a module-level `LatticeDB` singleton. |
| `lattice/web/mock.py` | GPU-free dev server (`uv run lattice-mock`). Serves the same static files as `app.py` but stubs `/api/query` with canned SSE token stream and `/api/atoms/recent` with hardcoded atoms. Hot-reloads on file save. Use this to iterate on HTML/CSS/JS without a running daemon or LLM. |
| `lattice/config.py` | `Config` dataclass. Reads all path/network env vars (`LATTICE_DIR`, `LATTICE_INBOX`, `LATTICE_SOCK`, `LATTICE_WEB_HOST`, `LATTICE_WEB_PORT`) in one place. LLM vars remain in `llm.py`. |
| `server.py` | MCP stdio entrypoint. Exposes five tools: `lattice_ingest`, `lattice_capture` (session-end summary, always `source=assistant`), `lattice_select`, `lattice_answer`, `lattice_status` (returns non-superseded atom count). Validates ingest args via `_IngestArgs`/`_CaptureArgs` Pydantic models — auto-strips `metadata.source` for chat-formatted input (mode B), enforces `_MCP_SESSION_ID` (process-level UUID, stable across all calls in one Claude Code session) and precise `observed_at` (server clock, overrides caller). Calls `_db.preload_if_stale()` before select/answer/status (O(1) manifest check). |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared low-level helpers: `write_file_atomic()` (canonical tempfile+rename utility); `_write_json_atomic()` delegates to it. |
| `lattice/parsers/` | Source-aware segmentation. `infer_source_type()` detects chat/markdown/code. `parse()` returns `list[Segment]` (frozen dataclass with `text`, `role`, `source_type`, `context`, `start`, `end`). `chat.py` handles windowed turn parsing with role tagging. `markdown.py` splits on headings. |
| `lattice/ingest.py` | Segments source via `parsers/` → LLM extracts atoms per segment → dedup + supersession check → write to DB. |
| `lattice/selection.py` | `select()` = `_retrieve()` — BM25 scored seeds → zero-score seed filter → source-diversity probe → graph BFS → optional BFS rescore. 0 LLM calls. Env: `LATTICE_SEED_MIN_SCORE`, `LATTICE_BFS_RESCORE`, `LATTICE_RECOMMENDATION_CAP`. |
| `lattice/query.py` | `parse_query()` — detects query shape (`aggregation`/`temporal`/`preference`/`recommendation`/`factual`) and `primary_kind`. Returns `QueryIntent`. Used by `_retrieve()`. |
| `lattice/synthesis.py` | Tool-calling agent via OpenAI-compat SDK (uses `make_llm_client()` from `llm.py`). Model from `SYNTHESIS_MODEL` (falls back to `LLM_MODEL`). Tools: `date_diff`, `sum_numbers`. `synthesize()` → `SynthesisResult`. `stream_synthesis()` → SSE generator used by the web UI. Ollama-specific `extra_body` applied only when `LLM_PROVIDER=ollama`. |
| `lattice/llm.py` | `make_llm_client()` — builds an `openai.OpenAI` client from `LLM_BASE_URL` + `LLM_API_KEY`. Default: Ollama at `localhost:11434`. Works with any OpenAI-compat endpoint (OpenRouter, Anthropic compat, hosted APIs). `resolve_model(override)` — returns model name from override or `LLM_MODEL` env var; raises `EnvironmentError` with actionable message if neither is set. `complete(messages) → str` — used by ingest, selection, supersession. `LLM_PROVIDER=ollama` (default) adds Ollama-specific `extra_body`; all other values treat the endpoint as a plain OpenAI-compat API. |

---

## Atom Data Model

Every atom is a `.md` file with YAML frontmatter:

```
atom_id              UUID (stable, used in supersession links and lattice_answer calls)
kind                 free-form: fact | event | decision | preference | belief | count | …
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
- **LLM calls are mockable at the module level.** Ingest/supersession patch `lattice.ingest.complete`. Synthesis patches `lattice.synthesis.make_llm_client` (returns a mock OpenAI client) — not `lattice.llm.complete`. Selection has no LLM calls.

---

## Roadmap

**Phase 1 complete.** Daemon, inbox watcher, IPC protocol, MCP read-only refactor, web UI (chat + recent atoms + feedback), streaming synthesis, numbered source citations, markdown rendering, circular ETA ring with localStorage history, dark mode toggle, Anthropic via OpenAI-compat. Feedback collected to `feedback.jsonl`; mock server (`lattice-mock`) ships for GPU-free UI development.

**Phase 2A complete.** `lattice_capture` session-end MCP tool (distinct from `lattice_ingest`; enforces `source=assistant`); `_db` staleness fix (`preload_if_stale()` on select/answer); `POST /api/ingest` HTTP endpoint; Pydantic input validation for MCP tools with mode A/B ingest routing.

**Phase 2B in progress** — capture channel expansion + channel consistency.
- ✅ `lc` CLI (`lattice/cli.py`) — terminal capture + `lc status` memory count
- ✅ Telegram bot (`lattice/telegram_bot.py`) — phone capture + `/ask` recall (auto-detect intent, clarification prompt for ambiguous messages) + `/save` session-end + `/status` count; independent launchd service; inbox fallback with daemon-restart follow-up reply
- ✅ Daemon Power Nap (`ProcessType=Background` in plist) — wakes on macOS Power Nap
- ✅ Web UI Save session — "Save session" button POSTs Q&A thread as conversation chunk to `/api/ingest`
- ✅ `lattice_status` MCP tool — memory count for Claude Code parity
- Next: VS Code extension (TypeScript, separate repo) → `lattice setup` wizard → browser extension → Apple Shortcuts → macOS menu bar → Cloudflare Tunnel

See STORIES.md for acceptance criteria and FEATURES.md for rationale.

**Phase 3:** multi-device sync (mDNS discovery, Ed25519 pairing, mTLS delta), native iOS/Android app (on-device inference), Screenpipe integration.
