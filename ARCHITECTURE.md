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
        │
        ▼
   embed index update    (if fastembed available) append row to embed_matrix.npy + embed_ids.json


select(query, as_of)          ← production path used by web UI, MCP server
        │
        ▼
   _retrieve()           BM25 top-20 (scored) → optional dense NN merge
        │                 (LATTICE_DENSE_SEEDS; cosine top-10 from embed index) →
        │                 drop zero-score seeds (LATTICE_SEED_MIN_SCORE) →
        │                 source-diversity probe → graph BFS; pointed path
        │                 (7 seeds, max=14) or expansion path (all seeds, max=60);
        │                 collapse superseded/dups; recommendation cap (max 5);
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
                         {"type":"citations_applied","answer":"...","num_map":{"1":1,...},"pii_protected":false} →
                         {"type":"done"}
```

---

## Module Map

| Module | Role |
|--------|------|
| `lattice/daemon.py` | Persistent daemon. Sole writer to `LatticeDB`. Watches `LATTICE_INBOX` via `watchdog`; accepts any file type — `extract_file_text()` dispatches by extension (PDF, docx, pptx, xlsx, xls, plain text); binary/unreadable files are moved to `processed/` with a warning. On startup, drains any pre-existing inbox files (`_drain_inbox`). After draining a `telegram-{chat_id}-{uuid}.txt` file, sends a follow-up reply via Telegram HTTP API (`_notify_telegram`). Binds a Unix domain socket (`LATTICE_SOCK`) for IPC. Runs the FastAPI web server inline via `uvicorn` on `LATTICE_WEB_PORT` (default 7337). Manages PID file and graceful shutdown on SIGTERM/SIGINT. CLI: `lattice-daemon` (start), `lattice-daemon status`. |
| `lattice/cli.py` | `lc` entry point. `lc "text"` or `lc path/to/file` — if argument is an existing file path, calls `extract_file_text()` before ingesting; captures via `DaemonClient().ingest_full()` over Unix socket; exits 1 with actionable message if daemon not running. `lc status` reads `LatticeDB` directly (no daemon needed) and prints memory count + top-5 topics + streak ("N days deep") from `usage.jsonl`. |
| `lattice/telegram_bot.py` | Telegram capture bot. Independent launchd service (`dev.lattice.telegram.plist`). Polls via `python-telegram-bot`. Auto-detects intent (`_classify`): question → recall, statement → capture, ambiguous → clarification prompt. Capture: `DaemonClient().ingest_full()`. Document attachments (PDF, docx, pptx, xlsx, plain text): `_handle_document()` downloads to temp file, calls `extract_file_text()`, ingests and replies with warm diff message ("absorbed ✓ — N new ideas…"). Recall: `POST /api/answer` → numbered inline citations `[1]`, `[2]` → compact footer `📚 N sources · channel` + `/sources` for full detail; appends rediscovery note if any cited atom ≥30 days old; prompts 👍/👎 feedback on all answers. `/save` ingests session history. `/status` shows memory count + streak + grace day. `/start` shows 3 suggested questions. `/sources` shows full source detail for last recall. Milestone moments (Day 1/7/14/30) prepended on milestone day. Daemon-down: inbox fallback with chat_id in filename. Commands: `/ask`, `/save`, `/status`, `/start`, `/sources`. Requires `uv sync --group telegram`. |
| `lattice/client.py` | `DaemonClient` — thin IPC client. `ingest(text, source_id, metadata) → list[str]` (back-compat); `ingest_full(text, source_id, metadata) → dict` returns full result with `atoms_new`, `atoms_updated`, `duplicates_skipped`, `atom_ids`. Used by all write channels (server.py, web UI, lc, telegram bot). |
| `lattice/web/app.py` | FastAPI web UI. Routes: `GET /` → `index.html`, `POST /api/query` (streaming SSE synthesis), `POST /api/answer` (blocking JSON synthesis — assigns `src_key = "{i+1}"` (pure numeric) to atoms; response includes `atoms` array with `src_key`, `subject`, `source_id`, `content_preview`), `POST /api/ingest` (text), `POST /api/ingest-file` (multipart — accepts any file type via `extract_file_text()`; returns `atoms_new`, `atoms_updated`, `duplicates_skipped`), `GET /api/usage/summary`, `GET /api/usage/weekly`, `GET /api/atoms/recent`, `GET /api/topic/depth`, `POST /api/feedback` (stores `atom_ids` of cited atoms), `GET /api/health`. UI: multi-file upload (parallel `Promise.allSettled`), warm diff toasts stacked via `#toast-container`, spark cards + ghost queries in empty state, "Save session" button, streak badge, milestone cards, rediscovery amber glow, scrollable sources panel with content preview + kind pill + channel + age, thumbs feedback on all answers, PII badge when `pii_protected`. |
| `lattice/web/mock.py` | GPU-free dev server (`uv run lattice-mock`). Serves the same static files as `app.py` but stubs `/api/query` with canned SSE token stream and `/api/atoms/recent` with hardcoded atoms. Hot-reloads on file save. Use this to iterate on HTML/CSS/JS without a running daemon or LLM. |
| `lattice/config.py` | `Config` dataclass — single source of truth for all env vars. `__post_init__` derives path fields from `lattice_dir`. `from_env()` reads all 21 env vars (paths, LLM, selection tuning, ingest tuning, PII, embed). Tests construct `Config(lattice_dir=tmp_path)` directly — no env mutation needed. |
| `server.py` | MCP stdio entrypoint. Exposes five tools: `lattice_ingest`, `lattice_capture` (session-end summary, always `source=assistant`), `lattice_select`, `lattice_answer`, `lattice_status` (returns non-superseded atom count). Validates ingest args via `_IngestArgs`/`_CaptureArgs` Pydantic models — auto-strips `metadata.source` for chat-formatted input (mode B), enforces `_MCP_SESSION_ID` (process-level UUID, stable across all calls in one Claude Code session) and precise `observed_at` (server clock, overrides caller). Calls `_db.preload_if_stale()` before select/answer/status (O(1) manifest check). |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. Thread-safe: `self._lock = threading.RLock()` guards all mutating methods (`write`, `supersede`, `register_subject`, `read`, `_get_bm25`). `db.lock` exposed so `ingest.py` can hold it across the atomic check+write sequence. On every `write()`, appends/updates a row in `_embed_matrix` (shape `n×384`, float32) and `_embed_ids` if fastembed is available; persists to `LATTICE_DIR/graph/embed_matrix.npy` + `embed_ids.json`. `_rebuild_embed_index()` builds index from all cached atoms when sidecar is missing (e.g. first run after enabling fastembed). |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared helpers: `write_file_atomic()` (canonical tempfile+rename); `_write_json_atomic()` delegates to it; `extract_file_text(path) → (text, source_id)` — dispatches by extension: `.pdf` via `pypdf`, `.docx` via `python-docx`, `.pptx` via `python-pptx`, `.xlsx` via `openpyxl`, `.xls` via `xlrd`, all others as UTF-8 text. Raises `ImportError` (missing optional dep) or `ValueError` (binary/unreadable). Used by daemon inbox watcher, web `/api/ingest-file`, `lc` CLI, and Telegram `_handle_document`. |
| `lattice/parsers/` | Source-aware segmentation. `infer_source_type()` checks `metadata["source_id"]` prefix/suffix first (`pdf:*`, `*.pptx`, `*.xlsx`), then falls back to content heuristics for chat/markdown/code. `parse()` returns `list[Segment]` (frozen dataclass with `text`, `role`, `source_type`, `context`, `start`, `end`). `chat.py`: windowed turn parsing with role tagging. `markdown.py`: splits on headings. `pdf.py`: splits on `\f` (form feed) page separators, `context="page N"`. `pptx.py`: splits on `[Slide N]` markers, `context="Slide N"`. `xlsx.py`: splits on `[Sheet: name]` markers, `context="Sheet: name"`. |
| `lattice/ingest.py` | Four named pipeline stages, each independently callable and testable. `segment_source(source, metadata) → list[Segment]` — pure parsing, no LLM. `extract_atoms(segments, metadata, ref, cfg) → list[dict]` — PII redact (batch) → LLM extraction per segment (optionally parallel) → PII restore; `_extract_atoms()` is the private per-segment worker. `detect_supersession(db, atom, cfg) → str|None` — fast path via `subjects.json`, slow path via `by_subject()`, fuzzy path via token overlap; single or multi-candidate LLM call. `persist_atoms(atoms_data, db, source_id, observed_at, ref, cfg) → dict` — dedup by normalized hash + supersession + `db.write()`/`db.supersede()`, all inside `with db.lock:`. `ingest()` orchestrates all four stages and appends `segments_processed`. Returns `{atoms_new, atoms_updated, duplicates_skipped, atom_ids, …}`. Extraction prompt (`_SYSTEM`): kind taxonomy — `preference` covers personal habits, tendencies, dietary patterns (test: "would knowing this inform a recommendation?"); `fact` is objective circumstance; `event` is one-time occurrence. Document sources use actual names not "User". People facts rule: each contact/identity detail (email, phone, title, employer, location, URL) → separate `kind=fact` atom with `subject = full name`. Source addendums: `_PDF_ADDENDUM`, `_PPTX_ADDENDUM`, `_XLSX_ADDENDUM`. |
| `lattice/selection.py` | `select()` = `_retrieve()` — BM25 scored seeds → optional dense seed augmentation (cosine NN hits merged before BFS) → zero-score seed filter → source-diversity probe → graph BFS → optional BFS rescore. 0 LLM calls. Env: `LATTICE_SEED_MIN_SCORE`, `LATTICE_BFS_RESCORE`, `LATTICE_RECOMMENDATION_CAP`, `LATTICE_DENSE_SEEDS` (enable dense augmentation; requires fastembed + embed index), `LATTICE_DENSE_TOP_K` (default 10). |
| `lattice/query.py` | `parse_query()` — detects query shape (`aggregation`/`temporal`/`preference`/`recommendation`/`factual`) and `primary_kind`. Returns `QueryIntent`. Used by `_retrieve()`. |
| `lattice/synthesis.py` | Tool-calling agent via OpenAI-compat SDK. `synthesize(query, atoms, cfg)` and `stream_synthesis(query, atoms, cfg)` both require a `Config`. Model from `cfg.synthesis_model` (falls back to `cfg.llm_model`). Tools: `date_diff`, `sum_numbers`. PII redaction: when `cfg.pii_scrub=true` and provider is not Ollama, atom content is redacted via `EntityRedactor` before the LLM call and restored in the response. `synthesize()` → `SynthesisResult`. `stream_synthesis()` → SSE generator; assigns `src_key = "{i+1}"` to atoms, builds `num_map` server-side, emits `pii_protected` flag in `citations_applied` event. `_is_no_answer(text)` — `<<NO_INFO>>` sentinel + fuzzy regex fallback. |
| `lattice/llm.py` | `make_llm_client(cfg)` — builds an `openai.OpenAI` client from `cfg.llm_base_url` + `cfg.llm_api_key`. Default: Ollama at `localhost:11434`. Works with any OpenAI-compat endpoint. `resolve_model(cfg, override)` — returns model name from override or `cfg.llm_model`; raises `EnvironmentError` with actionable message if neither is set. `complete(messages, cfg) → str` — used by ingest and supersession. `cfg.llm_provider=ollama` adds Ollama-specific `extra_body`; all other values use plain OpenAI-compat API. |
| `lattice/privacy.py` | PII round-trip redaction. `is_active()` — returns `True` when `LATTICE_PII_SCRUB=true` (default) and `LLM_PROVIDER != ollama`. `EntityRedactor` — stateless; `redact_batch(texts)` returns `(redacted_texts, entity_map)` where `entity_map = {tag: original}`; consistent entity numbering across all texts in the batch. `redact(text)` / `restore(text, entity_map)` — single-text variants. `_run_ner(text)` — calls `LATTICE_NER_MODEL` Ollama endpoint for person+org extraction; falls back to regex-only (email + phone) if model unset or NER fails. Used by `ingest.py` (redact before cloud LLM extraction, restore in atom content) and `synthesis.py` (redact atom content before cloud LLM call, restore in streamed response). |

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
source_type          markdown | chat | code | plain | pdf | pptx | xlsx | xls
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
- **LLM calls are mockable at the module level.** Ingest/supersession patch `lattice.ingest.complete`. Synthesis patches `lattice.synthesis.make_llm_client` (returns a mock OpenAI client) — not `lattice.llm.complete`. Selection has no LLM calls. Tests construct `Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")` directly; no env mutation via `monkeypatch.setenv` needed for function-level tests.

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
- ✅ Usage telemetry (STORY-013) — `usage.jsonl` written from all recall channels; `GET /api/usage/summary`; streak badge in web UI header; UTC-based streak calculation
- ✅ Telegram feedback (STORY-027) — 👍/👎 prompt after every recall; reason collection; posts to `feedback.jsonl` with `atom_ids` of cited atoms; web UI thumbs on all answers (no atom_count gate)
- ✅ Synthesis no-answer cleanup (STORY-028) — `<<NO_INFO>>` sentinel + fuzzy regex replaces verbose LLM non-answers with warm short phrase
- ✅ Memory Sparks (STORY-029) — ghost queries cycling in input placeholder; spark cards in empty state; Telegram `/start` suggestions; `lc status` topics
- ✅ Memory Depth (STORY-030) — streak reframe ("N days deep"); grace day logic; milestone cards (Day 1/7/14/30) with cube animation; cross-channel streak in `/status`, `lc status`, `lattice_status`
- ✅ Rediscovery highlight (STORY-032) — amber glow on citations from atoms ≥30 days old; Telegram appends old-memory note
- ✅ Weekly report + topic depth (STORY-031) — `GET /api/usage/weekly`, `GET /api/topic/depth`; Monday report card in web UI; topic depth cards at 5/10/20 atoms; cross-channel (Telegram weekly summary, lc topic depth, `notified_depths.json`)
- ✅ File ingest — all channels (STORY-014 extended) — `extract_file_text()` in `util.py` handles PDF/docx/pptx/xlsx/xls/plain text; daemon inbox accepts all types; web UI multi-file upload with parallel ingest and stacked toasts; `lc path/to/file`; Telegram document attachments; MCP `file_path` parameter. `ingest()` returns `atoms_new`/`atoms_updated`/`duplicates_skipped`; all channels show warm diff messages. `LatticeDB` fully thread-safe via `RLock`.
- ✅ PII round-trip redaction (STORY-033) — `lattice/privacy.py` `EntityRedactor`; regex (email+phone) + optional NER via `LATTICE_NER_MODEL`; redact before cloud LLM call, restore in atom content + streamed response; `LATTICE_PII_SCRUB` env var; `🔒 PII protected` badge in web UI; no-op for Ollama.
- ✅ Sources UX — content preview + kind pill + channel + age in web UI sources panel (scrollable); Telegram progressive disclosure: compact footer `📚 N sources · channel` + `/sources` command for full detail
- ✅ Browser extension (`extras/browser-extension/`) — Manifest V3 Chrome extension; right-click context menu + ⌥+⇧+S keyboard shortcut (uses `e.code` not `e.key` for Mac compatibility); sends selected text + page URL + title to `POST /api/ingest`; popup shows daemon status dot + memory count; source_id set to page URL so web UI citations panel renders clickable links. Load unpacked in Chrome Developer mode.
- Next: STORY-034 (lattice export/import) → STORY-035 (response stats + cost display) → STORY-036 (memory collage) → STORY-037 (user taste profile) → VS Code extension; STORY-038 (ambient enrichment agent) is Phase 3

See STORIES.md for acceptance criteria and FEATURES.md for rationale.

**Phase 3:** multi-device sync (mDNS discovery, Ed25519 pairing, mTLS delta), native iOS/Android app (on-device inference), Screenpipe integration, Messages/iMessage integration (macOS passive ingest via `~/Library/Messages/chat.db`; iOS/Android via native app Share Sheet).
