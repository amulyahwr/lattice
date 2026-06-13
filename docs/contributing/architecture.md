# Architecture

Lattice is a local-first personal memory OS. Raw text is decomposed into typed, timestamped **atoms** and stored as markdown files. A persistent daemon owns all writes, watches an inbox folder for ambient ingest, and serves a local web UI for recall. A graph index connects atoms through provenance, subject, and supersession edges so retrieval can navigate context instead of scanning a flat folder.

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
   _retrieve()           BM25 top-20 (scored, time-decayed) → optional dense NN merge
        │                 (LATTICE_DENSE_SEEDS; cosine top-20 from embed index,
        │                 LATTICE_DENSE_TOP_K=20) → combined list re-sorted by decay
        │                 (skipped for TEMPORAL queries) →
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

## Module map

| Module | Role |
|--------|------|
| `lattice/daemon.py` | Persistent daemon. Sole writer to `LatticeDB`. Watches `LATTICE_INBOX` via `watchdog`; accepts any file type — `extract_file_text()` dispatches by extension (PDF, docx, pptx, xlsx, xls, plain text); binary/unreadable files are moved to `processed/` with a warning. On startup, drains any pre-existing inbox files (`_drain_inbox`). After draining a `telegram-{chat_id}-{uuid}.txt` file, sends a follow-up reply via Telegram HTTP API (`_notify_telegram`). Binds a Unix domain socket (`LATTICE_SOCK`) for IPC. Passes its own `LatticeDB` instance to the web app via `set_config(cfg, db=_db)` — daemon and web share one in-memory cache, eliminating stale-read bugs. Runs the FastAPI web server inline via `uvicorn` on `LATTICE_WEB_PORT` (default 7337). Manages PID file and graceful shutdown on SIGTERM/SIGINT. CLI: `lattice-daemon` (start), `lattice-daemon status`. |
| `lattice/cli.py` | `lc` entry point. `lc "text"` or `lc path/to/file` — if argument is an existing file path, calls `extract_file_text()` before ingesting; captures via `DaemonClient().ingest_full()` over Unix socket; exits 1 with actionable message if daemon not running. `lc status` reads `LatticeDB` directly (no daemon needed) and prints memory count + top-5 topics + streak ("N days deep") from `usage.jsonl` + today's journey (grouped branches via `_build_journey_text` from `telegram_bot`). `lc clear` removes today's entries from `chat.jsonl` — same effect as web UI clear button and Telegram `/reset`. |
| `lattice/telegram_bot.py` | Telegram capture bot. Independent launchd service (`dev.lattice.telegram.plist`). Polls via `python-telegram-bot`. **Intent routing:** `_handle_message()` calls `classify_intent()` (LLM, no regex) → routes to `_do_capture()` or `_do_recall()`; fast path on `?` → recall. **Capture:** `_do_capture()` calls `reformulate_capture()` for pronoun resolution, then `DaemonClient().ingest_full()`; logs turn to `chat.jsonl` via `POST /api/capture-log`. **Recall:** `POST /api/answer` → numbered citations + compact footer; 👍/👎 feedback prompt. Document attachments: `_handle_document()` downloads to temp file, calls `extract_file_text()`. **Journey:** `/journey` renders multi-branch tree via `_get_journey_branches()` + `_build_journey_text()`; branches split by `query_topic` field (not just `context_reset`). **Opening strip:** `/start` fires `_send_opening_strip_if_due` (streak + topics + last Q from any channel). **Reset:** `/reset` clears today's journey via `POST /api/chat/clear-today`. Daemon-down: inbox fallback with chat_id in filename. Commands: `/ask`, `/save`, `/status`, `/start`, `/sources`, `/journey`, `/reset`. **plist must include LLM env vars** (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`) — launchd does not inherit shell environment. Requires `uv sync --group telegram`. |
| `lattice/client.py` | `DaemonClient` — thin IPC client. `ingest(text, source_id, metadata) → list[str]` (back-compat); `ingest_full(text, source_id, metadata) → dict` returns full result with `atoms_new`, `atoms_updated`, `duplicates_skipped`, `atom_ids`. Used by all write channels (server.py, web UI, lc, telegram bot). |
| `lattice/web/app.py` | FastAPI web UI. Accepts daemon's shared `LatticeDB` via `set_config(cfg, db)`. `_best_topic_label()` computes word-overlap topic label stored as `query_topic` in `chat.jsonl`. Routes: `GET /` → `index.html`, `POST /api/query` (streaming SSE; runs `classify_intent()` first — CAPTURE path calls `reformulate_capture()` + `DaemonClient.ingest_full()`, yields `captured` event; RECALL path runs `is_followup()` → `reformulate()` → synthesize, yields `atoms`+`token`+`done`; writes turn to `chat.jsonl` for both paths), `POST /api/answer` (blocking JSON synthesis; Telegram path), `POST /api/capture-log` (write capture turn to `chat.jsonl` from external channels), `GET /api/chat/recent?limit=` (last N turns, all channels; page-reload restore + opening strip "Last Q"), `GET /api/chat/today` (today's turns, all channels; journey rebuild), `POST /api/chat/clear-today` (remove today's entries; shared by web, Telegram `/reset`, `lc clear`), `GET /api/auto-save/status`, `POST /api/ingest` (text), `POST /api/ingest-file` (multipart), `GET /api/usage/summary`, `GET /api/usage/weekly`, `GET /api/atoms/recent`, `GET /api/atoms/related`, `GET /api/topic/depth`, `POST /api/feedback`, `GET /api/trace/{trace_id}` (returns matching line from `traces.jsonl`; 404 if tracing off or id not found), `GET /api/health`. `chat.jsonl` schema: `{ts, session_id, question, reformulated_query?, answer, atom_ids, subjects, channel, context_reset, query_topic?}`; capture turns use `answer="[captured: N new, M updated]"`. UI: classify_intent text capture, 30s cross-channel journey poll, clear reloads opening strip. |
| `lattice/web/mock.py` | GPU-free dev server (`uv run lattice-mock`). Serves the same static files as `app.py` but stubs `/api/query` with canned SSE token stream and `/api/atoms/recent` with hardcoded atoms. Hot-reloads on file save. Use this to iterate on HTML/CSS/JS without a running daemon or LLM. |
| `lattice/config.py` | `Config` dataclass — single source of truth for all env vars. `__post_init__` derives path fields from `lattice_dir`. `from_env()` reads all 21 env vars (paths, LLM, selection tuning, ingest tuning, PII, embed). Tests construct `Config(lattice_dir=tmp_path)` directly — no env mutation needed. |
| `server.py` | MCP stdio entrypoint. Exposes five tools: `lattice_ingest`, `lattice_capture` (session-end summary, always `source=assistant`), `lattice_select`, `lattice_answer`, `lattice_status` (returns non-superseded atom count). Validates ingest args via `_IngestArgs`/`_CaptureArgs` Pydantic models — auto-strips `metadata.source` for chat-formatted input (mode B), enforces `_MCP_SESSION_ID` (process-level UUID, stable across all calls in one Claude Code session) and precise `observed_at` (server clock, overrides caller). Calls `_db.preload_if_stale()` before select/answer/status (O(1) manifest check). |
| `lattice/models.py` | `Atom` — Pydantic model with all provenance fields. Serialized to/from YAML frontmatter + markdown body via `python-frontmatter`. |
| `lattice/db.py` | `LatticeDB` — one `.md` file per atom in `LATTICE_DIR`. In-memory `_atom_cache`. `subjects.json` for O(1) subject lookup. Holds a `LatticeGraph` instance; updates it on every `write()` and `supersede()`. Thread-safe: `self._lock = threading.RLock()` guards all mutating methods. `db.lock` exposed so `ingest.py` can hold it across the atomic check+write sequence. `_query_words()` strips possessive apostrophes (`'s`, `s'`) before BM25 tokenizing — prevents miss on `"John's"` vs `"John"` variants. `find_by_normalized_hash()` skips superseded atoms — prevents false-positive "Already in memory" when re-ingesting a value that was previously superseded. On every `write()`, appends/updates embed matrix row if fastembed available. |
| `lattice/graph.py` | `LatticeGraph` — `networkx.MultiDiGraph` backed by committed sidecars. Incrementally updated; full rebuild triggered when manifest atom count diverges from disk. |
| `lattice/util.py` | Shared helpers: `write_file_atomic()` (canonical tempfile+rename); `_write_json_atomic()` delegates to it; `extract_file_text(path) → (text, source_id)` — dispatches by extension: `.pdf` via `pypdf`, `.docx` via `python-docx`, `.pptx` via `python-pptx`, `.xlsx` via `openpyxl`, `.xls` via `xlrd`, all others as UTF-8 text. Raises `ImportError` (missing optional dep) or `ValueError` (binary/unreadable). Used by daemon inbox watcher, web `/api/ingest-file`, `lc` CLI, and Telegram `_handle_document`. |
| `lattice/parsers/` | Source-aware segmentation. `infer_source_type()` checks `metadata["source_id"]` prefix/suffix first (`pdf:*`, `*.pptx`, `*.xlsx`), then falls back to content heuristics for chat/markdown/code. `parse()` returns `list[Segment]` (frozen dataclass with `text`, `role`, `source_type`, `context`, `start`, `end`). `chat.py`: windowed turn parsing with role tagging. `markdown.py`: splits on headings. `pdf.py`: splits on `\f` (form feed) page separators, `context="page N"`. `pptx.py`: splits on `[Slide N]` markers, `context="Slide N"`. `xlsx.py`: splits on `[Sheet: name]` markers, `context="Sheet: name"`. |
| `lattice/ingest.py` | Four named pipeline stages, each independently callable and testable. `segment_source(source, metadata) → list[Segment]` — pure parsing, no LLM. `extract_atoms(segments, metadata, ref, cfg) → list[dict]` — PII redact (batch) → LLM extraction per segment (optionally parallel) → PII restore; `_extract_atoms()` is the private per-segment worker. `detect_supersession(db, atom, cfg) → list[str]` (was `str|None`) — supersedes ALL matching atoms for a subject; runs in priority order: (1) PII fast path via `_pii_content_type()` + `_pii_supersession()` (phone/email matched by regex, no LLM, no cloud exposure); (2) auto-save skip — `channel=auto_save` atoms return `[]` unconditionally; (3) LLM multi-supersession via `_SupersessionMultiResult` — fast path via `subjects.json`, slow path via `by_subject()` with word-overlap pre-filter. `persist_atoms(atoms_data, db, source_id, observed_at, ref, cfg) → dict` — dedup by normalized hash (skipping superseded atoms) + supersession + `db.write()`/`db.supersede()`, all inside `with db.lock:`. `ingest()` orchestrates all four stages. Returns `{atoms_new, atoms_updated, duplicates_skipped, atom_ids, …}`. Extraction prompt (`_SYSTEM`): kind taxonomy — `preference`, `fact`, `event`. Document sources use actual names not "User". People facts rule: each contact/identity detail → separate `kind=fact` atom per field. Source addendums: `_PDF_ADDENDUM`, `_PPTX_ADDENDUM`, `_XLSX_ADDENDUM`. |
| `lattice/selection.py` | `select()` = `_retrieve()` — BM25 scored seeds → optional dense seed augmentation (top-20 cosine NN hits merged; combined list re-sorted by time decay except for TEMPORAL queries, so fresh atoms lead BFS) → zero-score seed filter → source-diversity probe → graph BFS → optional BFS rescore → **superseded atoms filtered from result** (synthesis never sees stale facts even if BFS expanded into superseded nodes). 0 LLM calls. Env: `LATTICE_SEED_MIN_SCORE`, `LATTICE_BFS_RESCORE`, `LATTICE_RECOMMENDATION_CAP`, `LATTICE_DENSE_SEEDS`, `LATTICE_DENSE_TOP_K` (default 20). |
| `lattice/query.py` | `parse_query()` — detects query shape (`aggregation`/`temporal`/`preference`/`recommendation`/`factual`) and `primary_kind`. Returns `QueryIntent`. Used by `_retrieve()`. |
| `lattice/synthesis.py` | Tool-calling agent via OpenAI-compat SDK. `synthesize(query, atoms, cfg)` and `stream_synthesis(query, atoms, cfg)` both require a `Config`. Model from `cfg.synthesis_model` (falls back to `cfg.llm_model`). Tools: `date_diff`, `sum_numbers`. PII redaction: when `cfg.pii_scrub=true` and provider is not Ollama, atom content is redacted via `EntityRedactor` before the LLM call and restored in the response. `synthesize()` → `SynthesisResult`. `stream_synthesis()` → SSE generator; assigns `src_key = "{i+1}"` to atoms, builds `num_map` server-side, emits `pii_protected` flag in `citations_applied` event. `_is_no_answer(text)` — `<<NO_INFO>>` sentinel + fuzzy regex fallback. |
| `lattice/llm.py` | `make_llm_client(cfg)` — builds an `openai.OpenAI` client from `cfg.llm_base_url` + `cfg.llm_api_key`. Default: Ollama at `localhost:11434`. Works with any OpenAI-compat endpoint. `resolve_model(cfg, override)` — returns model name from override or `cfg.llm_model`; raises `EnvironmentError` with actionable message if neither is set. `complete(messages, cfg) → str` — used by ingest and supersession. `cfg.llm_provider=ollama` adds Ollama-specific `extra_body`; all other values use plain OpenAI-compat API. |
| `lattice/conversation.py` | Multi-turn reformulation + intent classification. `is_followup(query)` — detects anaphoric/short follow-ups via phrase fast-path, pronoun tokens, no-proper-noun heuristic. `reformulate(query, history, cfg)` — PII redact/restore + single LLM call; logs WARNING on LLM failure. `classify_intent(question, cfg) → 'capture'|'recall'` — fast path on `?` → recall; else single LLM call; falls back to `'recall'` on error. Used by web UI `/api/query` and Telegram `_handle_message` for regex-free intent routing. `reformulate_capture(text, history, cfg) → str` — rewrites imperative captures into self-contained factual assertions with pronoun resolution; `_REFUSAL_PREFIXES` guard catches LLM refusals; falls back to original text. Tests mock `lattice.conversation.complete`. |
| `lattice/migrations/` | Graph schema migration package. `__init__.py` provides `MigrationRunner`: discovers numbered modules (`m001_base`, `m002_episode_nodes`, …) by convention, runs pending migrations in order, creates `graph.backup.v{N}/` before each, restores on failure, updates `schema_version` in manifest on success. Each module exposes `SCHEMA_VERSION: int`, `DESCRIPTION: str`, `run(db, cfg)`. Migrations run in a background thread after web UI is available; queries fall back to pre-migration graph during run. `migration.log` records every attempt. `CURRENT_SCHEMA_VERSION` defined in `graph.py`. `preload()` triggers runner on version mismatch. `lattice graph rebuild` and `lattice graph status` subcommands in `cli.py`. |
| `lattice/telemetry_export.py` | Privacy-preserving telemetry + debug bundle. `compute_aggregates(cfg)` — reads `usage.jsonl`, `traces.jsonl`, `feedback.jsonl`; produces rate/distribution metrics with no content fields. `upload_telemetry(aggregates, endpoint)` — stdlib `urllib` POST; once per 24h when `LATTICE_TELEMETRY=true`. `sanitize_feedback_record(record)` — strips `question`/`answer`; replaces `atom_ids` with positional labels. `generate_debug_bundle(cfg) → Path` — stdlib `zipfile`; includes `traces.jsonl` + `usage.jsonl` as-is + sanitised feedback + `system_info.json`. Entry point: `lattice-debug`. Zero new deps. |
| `lattice/trace.py` | `QueryTrace` dataclass + `TraceWriter`. Captures per-query pipeline trace: BM25 seeds+scores, dense hits, BFS-expanded atoms, cited atoms, latency per stage. Written to `LATTICE_DIR/traces.jsonl` when `LATTICE_TRACE=true` (default false). OTel-compatible span structure. Query hashed (SHA-1), never raw text. Used by `selection.py`, `synthesis.py`, `app.py`. Zero overhead when disabled. |
| `lattice/archive.py` | `suggest_candidates(db)` — atoms with `quality_score < 0.3` AND `last_recalled_at > 365d` AND not superseded. `LatticeDB.archive(atom_id)` moves `.md` to `archive/`, removes from cache+graph, invalidates BM25. `LatticeDB.unarchive(atom_id)` reverses. Entry point: `lattice-archive`. Never automatic — always user-initiated. |
| `lattice/consolidation.py` | `check_consolidation(db, subject, cfg)` — called from `ingest.py` after every write. At subject atom count thresholds (3/5/10/20), creates/updates a `kind=synthesis` atom from top-3 episodic atoms by `quality_score × recency` (extractive, zero LLM). `tier=semantic`, `quality_score=1.5`. `supports_semantic` edges written to graph. Optional generative enrichment via `LATTICE_CONSOLIDATE_ENRICH=true` — Ollama only, never cloud providers. |
| `lattice/serendipity.py` | `SerendipityAgent` — daemon background thread, opt-in (`LATTICE_SERENDIPITY=true`). Top-50 atoms by `recall_count` → dense nearest-neighbor search → filter for zero graph overlap → LLM generates `kind=insight` atom. `leads_to_idea` edges to both source atoms. Max 1 surface/day, max 3 LLM calls/day. Requires fastembed; no-op if absent. |
| `lattice/privacy.py` | PII round-trip redaction. `is_active()` — returns `True` when `LATTICE_PII_SCRUB=true` (default) and `LLM_PROVIDER != ollama`. `EntityRedactor` — stateless; `redact_batch(texts)` returns `(redacted_texts, entity_map)` where `entity_map = {tag: original}`; consistent entity numbering across all texts in the batch. `redact(text)` / `restore(text, entity_map)` — single-text variants. `_run_ner(text)` — calls `LATTICE_NER_MODEL` Ollama endpoint for person+org extraction; falls back to regex-only (email + phone) if model unset or NER fails. Used by `ingest.py` (redact before cloud LLM extraction, restore in atom content) and `synthesis.py` (redact atom content before cloud LLM call, restore in streamed response). |

---

## Atom data model

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
quality_score        float (default 1.0); seed score multiplier; updated by feedback loop
recall_count         int (default 0); incremented each time atom is cited in synthesis
last_recalled_at     datetime | None; timestamp of most recent citation
tier                 stm | episodic | semantic; stm = ingested < 48h with recall_count=0
episode_id           str | None; f"{observed_at.date()}:{session_id}" — used for episode graph nodes
```

---

## Graph index

After every atom write, `LatticeGraph` upserts nodes and edges into a `networkx.MultiDiGraph` and writes committed sidecars to `LATTICE_DIR/graph/`.

**Node types:**

| ID pattern | Represents |
|-----------|-----------|
| `atom:<atom_id>` | One per atom (including superseded) |
| `source:<source_id>` | One per unique source document / ingest batch |
| `segment:<container_id>:<segment_id>` | One per chunk; container = source_id or session_id |
| `subject:<normalized>` | One per unique normalized subject string |
| `episode:<date>:<session_id>` | One per (day, session) pair; groups episodic atoms |
| `insight:<id>` | Serendipity agent connection atoms |

**Edge types:**

| Type | Direction | Meaning |
|------|-----------|---------|
| `atom_has_subject` | atom → subject | Always present |
| `same_subject_as` | atom ↔ atom | Bidirectional; same normalized subject |
| `source_contains_segment` | source → segment | When atom has source_id + segment_id |
| `segment_contains_atom` | segment → atom | When atom has segment_id |
| `supersedes` | new atom → old atom | Written by `db.supersede()` |
| `same_hash` | atom → atom | Same `normalized_content_hash` |
| `episode_contains_atom` | episode → atom | Groups atoms under a temporal episode |
| `supports_semantic` | episodic atom → synthesis atom | Consolidation pipeline; episodic → semantic tier |
| `enriches` | companion atom → source atom | Ambient enrichment agent |
| `leads_to_idea` | atom ↔ insight atom | Serendipity agent cross-domain connection |

**Sidecar files:**

```
LATTICE_DIR/
  graph/
    nodes.jsonl       one JSON line per node {id, type, …attrs}
    edges.jsonl       one JSON line per edge {src, dst, type, key}
    manifest.json     {version, schema_version, atom_count, edge_count, built_at}
    migration.log     append-only log — one line per migration attempt {ts, migration, from_version, to_version, duration_ms, status}
```

`preload()` loads sidecars when `manifest.atom_count` matches disk atom count; otherwise rebuilds from scratch. All writes are atomic (tempfile + rename).

---

## Key design invariants

- **Local-only.** No hosted service, no external DB. Everything in `LATTICE_DIR`.
- **Daemon is the sole writer.** Only the daemon writes atom files and graph sidecars. MCP server and web UI are read-only clients. Atom writes are atomic (tempfile + rename), making reads always safe without locking.
- **Human-readable atoms.** `.md` files can be hand-edited, deleted, or committed to git without breaking the server.
- **Committed snapshots.** Selection reads stable graph/BM25 snapshots; it never waits for active ingest.
- **Superseded atoms stay on disk** with `is_superseded=true` and bidirectional links. History is preserved, not deleted.
- **Expensive enrichment is optional.** Embeddings, semantic relation enrichment, and hub labeling must remain off by default for Ollama users.
- **LLM calls are mockable at the module level.** Ingest/supersession patch `lattice.ingest.complete`. Synthesis patches `lattice.synthesis.make_llm_client` (returns a mock OpenAI client) — not `lattice.llm.complete`. Selection has no LLM calls. Tests construct `Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")` directly; no env mutation via `monkeypatch.setenv` needed for function-level tests.
