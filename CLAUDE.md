# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # install deps
uv run pytest                  # all tests
uv run pytest tests/test_db.py # single file
uv run pytest -k test_supersession_links_atoms  # single test
uv run lattice             # run MCP server (requires env vars)
uv run lattice-daemon          # start persistent daemon
uv run lattice-daemon status   # check daemon health (JSON)
uv run lc "text"               # capture a one-liner from terminal
```

Web UI auto-starts with the daemon at http://localhost:7337 (port tunable via `LATTICE_WEB_PORT`).

Required env vars: `LLM_PROVIDER`, `LLM_MODEL`, `LATTICE_DIR`. `LLM_API_KEY` required for all providers except `ollama`. Per-stage model overrides: `INGEST_MODEL`, `SYNTHESIS_MODEL`, `REFORMULATION_MODEL` (falls back to `INGEST_MODEL` → `LLM_MODEL`). `LLM_BASE_URL` overrides the API endpoint — use for OpenRouter (`https://openrouter.ai/api/v1`), Anthropic-compat (`https://api.anthropic.com/v1`), or any OpenAI-compat endpoint; set `LLM_PROVIDER=openai` in all cases. Conversation tuning: `LATTICE_REFORMULATION=0` disables multi-turn reformulation; `LATTICE_CONVERSATION_TURNS` (default 2) sets history window.

## Architecture

The current pipeline is: **ingest → select → synthesize**. Ingest and synthesis use LLM via `lattice/llm.py`; selection is LLM-free (BM25 + graph BFS). The product direction is local-first lattice: source-aware ingest, provenance, deterministic graph sidecars, graph-seeded selection, and optional enrichment that never blocks local querying.

```
server.py          MCP stdio entrypoint. Owns one shared LatticeDB instance.
lattice/
  config.py        Centralised env-var parsing → Config dataclass. All env vars here:
                   paths, LLM, selection tuning, ingest tuning, PII, embed, conversation.
                   __post_init__ derives path fields from lattice_dir. Tests use Config(lattice_dir=tmp_path).
  conversation.py  Multi-turn query reformulation + intent classification.
                   is_followup(query) → bool detects anaphoric/short follow-ups via phrase
                   fast-path + pronoun heuristic + proper-noun check.
                   reformulate(query, history, cfg) → str: single LLM call (REFORMULATION_MODEL →
                   INGEST_MODEL → LLM_MODEL) with PII redact/restore; fallbacks on empty/identical/
                   too-long response. Logs WARNING on LLM failure instead of silently falling back.
                   classify_intent(question, cfg) → 'capture'|'recall': fast path on '?' → recall;
                   else single LLM call; falls back to 'recall' on error. Used by web UI and
                   Telegram to route messages without regex.
                   reformulate_capture(text, history, cfg) → str: rewrites imperative captures
                   into self-contained factual assertions with pronoun resolution. _REFUSAL_PREFIXES
                   check catches LLM refusal responses. Falls back to original text.
                   Tests mock at lattice.conversation.complete.
  llm.py           LLM client with dual routing. Claude models (anthropic/* or claude-*) use
                   native Anthropic SDK (_anthropic_complete); all others use openai.OpenAI compat.
                   make_llm_client(cfg), resolve_model(cfg, override), complete(messages, cfg).
                   All read from Config, not os.environ. complete() retries on 429 (2s/5s/15s).
                   LLM_BASE_URL trailing /v1 stripped for Anthropic SDK (SDK appends it).
                   Ollama gets extra_body={num_ctx, think:false}; others don't.
  models.py        Atom pydantic model + markdown serialization (python-frontmatter).
  db.py            File-based store: one .md file per atom in LATTICE_DIR. BM25 search.
                   subjects.json is a subject→atom_id index for O(1) supersession lookups.
                   Holds a LatticeGraph instance; updated on every write/supersede/preload.
                   _query_words() strips possessive apostrophes ("John's" → "John", "Jane Doe's" →
                   "Jane Doe") before tokenizing — prevents BM25 miss on apostrophe variants.
                   find_by_normalized_hash() skips superseded atoms — prevents "Already in memory"
                   false positives when re-ingesting a value that was previously superseded.
  graph.py         Heterogeneous graph index (networkx MultiDiGraph). Writes committed
                   sidecars to LATTICE_DIR/graph/{nodes.jsonl,edges.jsonl,manifest.json}.
                   Node types: atom:<id>, source:<id>, segment:<cid>:<sid>, subject:<norm>.
                   Edge types: source_contains_segment, segment_contains_atom,
                   atom_has_subject, same_subject_as, same_hash, supersedes.
  daemon.py        Persistent process that owns all LatticeDB writes. Watches LATTICE_INBOX
                   via watchdog; processes dropped files → ingest → moves to processed/.
                   IPC via Unix socket (LATTICE_SOCK). Also spawns the FastAPI web server.
                   Auto-saves completed chat threads (≥2 turns, last turn >10 min old) every 30 min.
                   JSON-lines log to LATTICE_DIR/daemon.log.
                   Passes its own LatticeDB instance to web app via set_config(cfg, db=_db) —
                   daemon and web share one cache; no stale reads across write/query boundary.
  client.py        DaemonClient: thin IPC wrapper over the Unix socket. Used by server.py
                   to delegate writes to the daemon. ingest_full(text, source_id, metadata)
                   returns full result dict {atoms_new, atoms_updated, duplicates_skipped,
                   atom_ids}. ingest() is a back-compat alias returning only atom_ids.
  parsers/         Source-aware pre-ingest segmentation. `infer_source_type()` detects chat/
                   markdown/code. `parse()` returns list[Segment] with role, context, span.
                   chat.py preserves turn windowing + role field. markdown.py splits on headings.
  ingest.py        Four public pipeline stages: segment_source() → extract_atoms()
                   → detect_supersession() → persist_atoms(). ingest() orchestrates
                   all four. Each stage is independently callable and testable.
                   detect_supersession() returns list[str] (was str|None) — supersedes ALL
                   matching atoms for a subject, not just one.
                   PII fast path: _pii_content_type() + _pii_supersession() handle phone/email
                   atoms deterministically (regex, no LLM call) — prevents PII reaching cloud.
                   Auto-save skip: atoms with metadata channel="auto_save" bypass supersession
                   entirely to prevent historical Q&A threads overwriting manual captures.
                   Word-overlap pre-filter on slow-path candidates reduces spurious LLM calls.
  query.py         Query intent classifier: detects aggregation/temporal/recommendation/preference
                   signals. Returns QueryIntent with shape + primary_kind. Stateless; used by selection.py.
  selection.py     select() = _retrieve(): BM25 scored seeds → optional dense NN augmentation
                   (LATTICE_DENSE_SEEDS, top-K=20 cosine hits merged; re-sorted by decay after
                   merge except for TEMPORAL queries) → zero-score seed filter
                   (LATTICE_SEED_MIN_SCORE) → source-diversity probe → graph BFS → optional BFS
                   rescore (LATTICE_BFS_RESCORE) → atom dicts. 0 LLM calls.
                   Superseded atoms are filtered from the result before returning — synthesis
                   LLM never sees stale facts even if graph BFS expands into superseded nodes.
  synthesis.py     LLM generates prose answer from atom dicts. Uses SYNTHESIS_MODEL env var
                   (falls back to LLM_MODEL). Ollama path uses OpenAI-compat client with
                   num_ctx=4096 and tool calls for date_diff + sum_numbers.
  embed.py         Optional semantic embedding via fastembed (install semantic extra). Guards
                   import; no-ops cleanly if fastembed absent. Not on hot query path.
  privacy.py       PII round-trip redaction. EntityRedactor: redact_batch(texts) →
                   (redacted_texts, entity_map); restore(text, entity_map) swaps tags back.
                   is_active(cfg) → True when LATTICE_PII_SCRUB=true and provider != ollama.
                   NER via LATTICE_NER_MODEL (Ollama model); regex-only fallback (email+phone)
                   when unset. Used by ingest.py (before cloud LLM extraction) and
                   synthesis.py (before cloud LLM call). Atoms on disk always have real names.
  util.py          Shared helpers: write_file_atomic, _normalized_subject,
                   extract_file_text(path) → (text, source_id) dispatches by extension
                   (PDF/docx/pptx/xlsx/xls/plain). Used by daemon, web, lc, telegram.
  cli.py           Entry point for `lc` terminal command. `lc <text>` captures via DaemonClient
                   over Unix socket; fails fast if daemon not running. Prints followup tip if
                   is_followup() detects an anaphoric query. `lc status` reads LatticeDB
                   directly (no daemon needed) and prints memory count + streak + today's journey
                   (grouped branches via _build_journey_text from telegram_bot).
                   `lc clear` removes today's turns from chat.jsonl — same as web UI clear
                   and Telegram /reset.
  telegram_bot.py  Telegram polling bot (STORY-018). Runs as independent launchd service
                   (dev.lattice.telegram.plist) — not a daemon subprocess. On daemon-down:
                   writes inbox file as telegram-{chat_id}-{uuid}.txt and replies immediately.
                   Daemon drains inbox on startup (_drain_inbox) and sends follow-up reply via
                   urllib using LATTICE_TELEGRAM_TOKEN. Requires: uv sync --group telegram.
                   Intent routing: _handle_message() calls classify_intent() (no regex) →
                   routes to _do_recall() or _do_capture(). _do_capture() calls
                   reformulate_capture() for pronoun resolution, then POSTs to /api/capture-log.
                   /start fires _send_opening_strip_if_due (streak + topics + last question).
                   /reset clears today's journey via /api/chat/clear-today.
                   /journey renders multi-branch tree via _get_journey_branches() +
                   _build_journey_text(); correctly splits branches by query_topic, not just
                   context_reset (fixes single-topic merge when context_reset=false on first turn).
                   plist (extras/dev.lattice.telegram.plist) must include LLM_PROVIDER,
                   LLM_BASE_URL, LLM_MODEL, LLM_API_KEY — launchd doesn't inherit shell env.
  web/app.py       FastAPI app. Started by daemon. set_config(cfg, db) accepts the daemon's
                   shared LatticeDB instance — web and daemon share one cache.
                   _best_topic_label(question, reformulated, subjects) → str|None: word-overlap
                   (words >2 chars) between query and subject strings; stored as query_topic in
                   chat.jsonl so all channels have consistent journey branch labels.
                   Routes:
                   GET /               → index.html
                   POST /api/ingest    → text capture (source_id + metadata, observed_at stamped)
                   POST /api/ingest-file → multipart file upload; calls extract_file_text()
                   POST /api/query     → streaming SSE synthesis (web UI path); accepts
                                         conversation_history + session_id; runs classify_intent()
                                         first — CAPTURE path calls reformulate_capture() then
                                         DaemonClient.ingest_full(), yields 'captured' SSE event;
                                         RECALL path runs is_followup() → reformulate() → synthesize,
                                         yields 'atoms' (with query_topic) + 'token' + 'done' events;
                                         writes turn to chat.jsonl for both paths
                   POST /api/answer    → blocking JSON synthesis (Telegram path); same
                                         conversation_history support; returns {answer, atoms,
                                         pii_protected, context_reset}
                   POST /api/capture-log → write a capture turn to chat.jsonl from external
                                           channels (Telegram, future channels); accepts
                                           {question, reformulated_query, session_id, channel}
                   GET /api/chat/recent   → last N Q&A turns (all channels); used for page-reload
                                            restore and "Last question" in opening strip
                   GET /api/chat/today    → today's chat.jsonl entries, all channels (journey rebuild)
                   POST /api/chat/clear-today → remove today's entries; shared by web, Telegram
                                                /reset, and lc clear
                   GET /api/auto-save/status → whether auto-save sweep is currently running
                   GET /api/atoms/recent  → recent non-superseded atoms JSON
                   GET /api/atoms/related → BFS from cited atom subjects → top-N related subjects
                                           (curiosity chips: 'You also know about…')
                   GET /api/usage/summary → streak, query counts, avg latency, atom count
                   GET /api/usage/weekly  → weekly report data (atoms, recalls, topics, new topics)
                   GET /api/topic/depth   → atom count for a given subject
                   POST /api/feedback     → writes {ts, question, answer, rating, reason,
                                            atom_ids, dismissed_atom_ids, citation_map} to feedback.jsonl
                   GET /api/health        → {ok: true}
                   chat.jsonl: every turn appended with {ts, session_id, question,
                               reformulated_query?, answer, atom_ids, subjects, channel,
                               context_reset, query_topic?}
                               capture turns have answer="[captured: N new, M updated]"
```

### Ingest drop mechanism

Drop any `.md` (or text) file into `LATTICE_INBOX` (default `LATTICE_DIR/inbox/`). The daemon's watchdog picks it up within seconds, runs `ingest()`, then moves it to `processed/`. This is the primary human-facing write path; MCP `ingest_text` goes through `DaemonClient` to the same daemon.

### Distribution channel consistency

Lattice has multiple capture/recall channels: MCP tools (Claude Code), web UI, `lc` CLI, Telegram bot, Chrome browser extension, and future channels (VS Code extension, Apple Shortcuts, menu bar app).

**Rule 1 — New channel:** when a new distribution channel is added, all existing functionality (capture + recall) should be implemented in that channel where technically feasible. Don't ship a channel that only does half the job if the other half is achievable.

**Rule 2 — New functionality:** when a new capability is added to any channel, evaluate adding it to all other channels. If feasible, add it. If not feasible for a channel (e.g. streaming synthesis in a CLI), note it explicitly.

**Current channel capability matrix:**

| Capability | MCP | Web UI | `lc` CLI | Telegram | Browser ext | VS Code* |
|---|---|---|---|---|---|---|
| Capture (ingest) | ✅ | ✅ text + classify_intent routing | ✅ | ✅ auto-detect + capture | ✅ right-click / ⌥⇧S | planned |
| File ingest | ✅ `file_path` | ✅ drag-drop | ✅ `lc path/to/file` | ✅ document attach | — | planned |
| Recall (synthesized answer) | ✅ | ✅ | — (out of scope) | ✅ auto-detect + `/ask` | — | planned |
| Capture reformulation | — | ✅ reformulate_capture → pronoun resolution | — | ✅ reformulate_capture | — | — |
| Session-end capture | ✅ | ✅ auto-save (daemon sweep) | — (atomic by design) | ✅ `/save` | — | — |
| Memory count / status | ✅ `lattice_status` | ✅ (recent atoms) | ✅ `lc status` | ✅ `/status` | ✅ popup count | — |
| Daemon status | — | — | — | — | ✅ popup dot | — |
| Recall feedback | ❌ redundant (Claude Code has own UI) | ✅ thumbs + reason + per-source ✕ dismiss | — (no recall) | ✅ 👍/👎 (answer-level only) | — | — |
| Usage streak | ✅ `lattice_status` | ✅ "N days deep" badge | ✅ `lc status` shows streak | ✅ `/status` shows streak | — | — |
| Milestone moments | — | ✅ opening strip (absorbed) | ✅ `lc status` prints msg | — (removed) | — | — |
| PII indicator | — (no UI) | ✅ `🔒` badge | — (no recall) | ✅ `🔒 PII protected` footer | — | — |
| Rediscovery highlight | — (no UI) | ✅ amber glow + inline note | — (no recall) | ✅ age note in answer | — | — |
| Weekly report | — | ✅ Monday opening strip | — | ✅ Monday prepend | — | — |
| Topic depth | — | ✅ inline annotation below answer | ✅ note on capture | ✅ note on capture | — | — |
| Multi-turn reformulation | — (Claude owns context) | ✅ is_followup + reformulate, history in JS | ✅ followup tip on capture | ✅ qa_history passed on /ask | — | — |
| Context reset on topic shift | — | ✅ context_reset SSE → clear JS history | — | ✅ qa_history cleared | — | — |
| Opening strip (journey context) | — | ✅ page load strip: streak + topics + last Q | ✅ `lc status` journey | ✅ /start fires strip | — | — |
| Journey path | — | ✅ sidebar tree, 30s cross-channel poll | ✅ `lc status` journey summary | ✅ `/journey` multi-branch tree | — | — |
| Journey clear / reset | — | ✅ clear button → reload strip | ✅ `lc clear` | ✅ `/reset` | — | — |
| Curiosity chips | — | ✅ chips below answer | — | ✅ footer after /ask | ✅ related_subjects field | — |
| Auto-save chat threads | ✅ daemon sweep | ✅ daemon sweep | — | ✅ daemon sweep (covers telegram channel) | — | — |

*not yet built. Update this table whenever a channel ships or gains a capability.

### Product roadmap guardrails

- Keep architecture local-first: no hosted service, no required daemon, no external DB.
- Keep atoms human-readable and git-trackable.
- Treat LongMemEval as an eval yardstick only; do not add benchmark-shaped hacks to product paths.
- Prefer provenance fields and graph edges over mutating atom content for retrieval.
- Query paths should use committed snapshots and should not wait for active ingest/enrichment.
- Expensive relation enrichment, embeddings, and hub labeling must remain optional, especially for Ollama users.

### Key data flow details

**Supersession** (in `ingest.py`): when a new atom has the same subject as an existing one, supersession runs in priority order: (1) PII fast path — phone/email atoms matched by `_pii_content_type()` regex, no LLM; (2) auto-save skip — `channel=auto_save` atoms bypass supersession entirely; (3) LLM multi-supersession — `_SupersessionMultiResult` returns a list of ALL atom IDs to supersede (not just one). Fast path uses `subjects.json`; slow path scans files with word-overlap pre-filter. Superseded atoms stay on disk with `is_superseded=true` and bidirectional links (`superseded_by` / `supersedes`). Results filtered from selection — synthesis never sees superseded atoms.

**LLM calls**: ingest/supersession go through `lattice.llm.complete(messages, cfg)`. Tests mock at `lattice.ingest.complete` — patch the module-level name, not `lattice.llm.complete`. For Claude models, `complete()` dispatches to `_anthropic_complete`; tests mock `lattice.llm._anthropic_complete` for those paths. Synthesis is different: patch `lattice.synthesis.make_llm_client` (returns a mock OpenAI client). Selection has no LLM calls.

**Atom storage**: every atom is a `.md` file with YAML frontmatter. `LatticeDB` has an in-memory cache (`_atom_cache`). Cache is per-instance; `server.py` reuses one instance per process.

**BM25**: cached on `LatticeDB` as `_bm25_cache` keyed by frozenset of atom IDs. Invalidated on every `write()` or `supersede()`. Rebuilt lazily on next `search()` call.

**Graph sidecars**: `LatticeGraph` writes `LATTICE_DIR/graph/` on every atom write. `db.preload()` loads from sidecars if manifest atom_count matches; otherwise rebuilds. Access via `db.graph`. Selection uses BFS over graph edges to expand evidence packs from BM25 seeds.

This is current MVP behavior, not the target product shape.

### Test conventions

All tests mock LLM via `unittest.mock.patch`. Ingest responses mock two calls per atom: first the extraction JSON, then the supersession reply (`'{"superseded_atom_ids": []}'` or `'{"superseded_atom_ids": ["<id>"]}'` — multi-result format). Use `tmp_path` fixture for isolated `LatticeDB` instances. Function-level tests construct `Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")` directly — no `monkeypatch.setenv` needed for behavior control. Tests for `classify_intent` and `reformulate_capture` mock at `lattice.conversation.complete`.

### Memory: Lattice is the sole memory system

**Do not write user facts, preferences, or decisions to Claude's internal auto-memory system.** Do not save anything to `~/.claude/projects/.../memory/`. Lattice is the only memory store for this project.

When the user says any of: "save", "done", "goodbye", "wrap up", "end session", "save session" — summarize decisions made, things built, and conclusions reached, then call `lattice_capture` (not `lattice_ingest`) with that summary. Always set `metadata.source_id="claude-code"` and `metadata.observed_at=<current ISO timestamp>`.

When the user shares a preference, decision, fact, or anything worth remembering, call `lattice_ingest` immediately.
- Single fact from the user → set `metadata.source="user"`, `metadata.source_id="claude-code"`, `metadata.observed_at=<current ISO timestamp>`.
- Conversation chunk (multiple turns) → format as `"user: ...\nassistant: ..."` and omit `metadata.source` — the pipeline attributes per-turn automatically.

When answering a recall question ("what did I decide about X", "what do I prefer", "remind me of Y"), call `lattice_select` first and ground the answer in returned atoms.
