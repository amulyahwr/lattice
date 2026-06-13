# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
uv sync                        # base deps only
uv sync --group full           # + semantic, pdf, docx, office, telegram (recommended)
uv sync --group docs           # + mkdocs-material (for building docs)
uv run pytest                  # all tests
uv run pytest tests/test_db.py # single file
uv run pytest -k test_supersession_links_atoms  # single test
uv run lattice                 # run MCP server (requires env vars)
uv run lattice-daemon          # start persistent daemon
uv run lattice-daemon status   # check daemon health (JSON)
uv run lc "text"               # capture a one-liner from terminal
uv run --group docs mkdocs serve  # preview docs at localhost:8000
```

Web UI auto-starts with the daemon at http://localhost:7337 (port tunable via `LATTICE_WEB_PORT`).

Required env vars: `LLM_PROVIDER`, `LLM_MODEL`, `LATTICE_DIR`. `LLM_API_KEY` required for all providers except `ollama`. Per-stage model overrides: `INGEST_MODEL`, `SYNTHESIS_MODEL`, `REFORMULATION_MODEL` (falls back to `INGEST_MODEL` → `LLM_MODEL`). `LLM_BASE_URL` overrides the API endpoint — use for OpenRouter (`https://openrouter.ai/api/v1`), Anthropic-compat (`https://api.anthropic.com/v1`), or any OpenAI-compat endpoint; set `LLM_PROVIDER=openai` in all cases. Conversation tuning: `LATTICE_REFORMULATION=0` disables multi-turn reformulation; `LATTICE_CONVERSATION_TURNS` (default 2) sets history window.

## Architecture

The current pipeline is: **ingest → select → synthesize**. Ingest and synthesis use LLM via `lattice/llm.py`; selection is LLM-free (BM25 + graph BFS). The product direction is local-first lattice: source-aware ingest, provenance, deterministic graph sidecars, graph-seeded selection, and optional enrichment that never blocks local querying.

```
server.py          MCP stdio entrypoint. Owns one shared LatticeDB instance.
lattice/
  config.py        Centralised env-var parsing → Config dataclass. All env vars here.
                   __post_init__ derives path fields from lattice_dir. Tests use Config(lattice_dir=tmp_path).
  conversation.py  Multi-turn query reformulation + intent classification.
                   is_followup(query) → bool. reformulate(query, history, cfg) → str.
                   classify_intent(question, cfg) → 'capture'|'recall': fast path on '?' → recall.
                   reformulate_capture(text, history, cfg) → str: pronoun resolution for captures.
                   Tests mock at lattice.conversation.complete.
  llm.py           Dual routing: Claude models (anthropic/* or claude-*) → native Anthropic SDK
                   (_anthropic_complete); all others → openai.OpenAI compat.
                   complete() retries on 429 (2s/5s/15s). Tests mock lattice.llm._anthropic_complete
                   for Anthropic paths.
  models.py        Atom pydantic model + markdown serialization (python-frontmatter).
  db.py            File-based store: one .md file per atom in LATTICE_DIR. BM25 search.
                   subjects.json is a subject→atom_id index for O(1) supersession lookups.
                   _query_words() strips possessive apostrophes before tokenizing.
                   find_by_normalized_hash() skips superseded atoms — prevents false-positive dedup.
  graph.py         Heterogeneous graph index (networkx MultiDiGraph). Committed sidecars:
                   LATTICE_DIR/graph/{nodes.jsonl,edges.jsonl,manifest.json}.
  daemon.py        Sole writer. Watches LATTICE_INBOX via watchdog. IPC via Unix socket (LATTICE_SOCK).
                   Spawns FastAPI web server. Passes own LatticeDB to web via set_config(cfg, db=_db)
                   — daemon and web share one cache; no stale reads.
  client.py        DaemonClient: IPC wrapper. ingest_full() → {atoms_new, atoms_updated,
                   duplicates_skipped, atom_ids}. ingest() is back-compat alias.
  parsers/         Source-aware segmentation. infer_source_type() detects chat/markdown/code.
                   parse() → list[Segment]. chat.py: turn windowing + role. markdown.py: headings.
  ingest.py        Four stages: segment_source() → extract_atoms() → detect_supersession()
                   → persist_atoms(). detect_supersession() returns list[str] — supersedes ALL
                   matching atoms. PII fast path (regex, no LLM). auto_save skip bypasses supersession.
                   Tests mock at lattice.ingest.complete — two calls per atom (extract, then supersede).
  query.py         parse_query() → QueryIntent with shape + primary_kind. Stateless; used by selection.
  selection.py     BM25 seeds → optional dense NN → zero-score filter → source diversity → graph BFS
                   → BFS rescore → atom dicts. 0 LLM calls. Superseded atoms filtered before return.
  synthesis.py     Streaming LLM call over atom pack → prose answer with citations. Tool calls for
                   date_diff + sum_numbers. Tests mock lattice.synthesis.make_llm_client (not llm.complete).
  embed.py         Optional fastembed semantic embeddings. No-ops if fastembed absent.
  privacy.py       PII round-trip redaction. EntityRedactor: redact_batch() → (redacted, entity_map);
                   restore() swaps tags back. is_active() → True when LATTICE_PII_SCRUB=true and
                   provider != ollama. Atoms on disk always have real names.
  util.py          write_file_atomic, extract_file_text(path) → (text, source_id) — dispatches
                   by extension (PDF/docx/pptx/xlsx/xls/plain).
  cli.py           lc entry point. lc <text|file> captures via DaemonClient. lc status prints
                   memory count + streak + today's journey. lc clear removes today's chat.jsonl turns.
  telegram_bot.py  Independent launchd service. classify_intent() routing (no regex).
                   On daemon-down: writes inbox file, replies immediately.
                   plist must include LLM_PROVIDER, LLM_BASE_URL, LLM_MODEL, LLM_API_KEY —
                   launchd doesn't inherit shell env. Requires: uv sync --group telegram.
  web/app.py       FastAPI app. set_config(cfg, db) shares daemon's LatticeDB instance.
                   Routes: GET /, POST /api/ingest, POST /api/ingest-file, POST /api/query (SSE),
                   POST /api/answer, POST /api/capture-log, GET /api/chat/recent,
                   GET /api/chat/today, POST /api/chat/clear-today, GET /api/auto-save/status,
                   GET /api/atoms/recent, GET /api/atoms/related, GET /api/usage/summary,
                   GET /api/usage/weekly, GET /api/topic/depth, POST /api/feedback, GET /api/health.
                   chat.jsonl: {ts, session_id, question, reformulated_query?, answer, atom_ids,
                   subjects, channel, context_reset, query_topic?}
```

→ Full module detail: `docs/contributing/architecture.md`

### Ingest drop mechanism

Drop any `.md` (or text) file into `LATTICE_INBOX` (default `LATTICE_DIR/inbox/`). The daemon's watchdog picks it up within seconds, runs `ingest()`, then moves it to `processed/`.

### Distribution channel consistency

**Rule 1 — New channel:** implement all existing functionality (capture + recall) in the new channel where technically feasible.

**Rule 2 — New functionality:** when a capability is added to any channel, evaluate adding it to all others. If not feasible, note it explicitly.

→ Full channel capability matrix: `docs/concepts/capture-channels.md`

### Product roadmap guardrails

- Keep architecture local-first: no hosted service, no required daemon, no external DB.
- Keep atoms human-readable and git-trackable.
- Treat LongMemEval as an eval yardstick only; do not add benchmark-shaped hacks to product paths.
- Prefer provenance fields and graph edges over mutating atom content for retrieval.
- Query paths should use committed snapshots and should not wait for active ingest/enrichment.
- Expensive relation enrichment, embeddings, and hub labeling must remain optional, especially for Ollama users.

### Key data flow details

**Supersession** (in `ingest.py`): priority order: (1) PII fast path — phone/email matched by regex, no LLM; (2) auto-save skip — `channel=auto_save` atoms return `[]` unconditionally; (3) LLM multi-supersession — `_SupersessionMultiResult` returns ALL atom IDs to supersede. Superseded atoms stay on disk with `is_superseded=true` and bidirectional links. Results filtered from selection.

**LLM calls**: ingest/supersession → `lattice.llm.complete`. Tests mock at `lattice.ingest.complete` (module-level name). For Anthropic paths, mock `lattice.llm._anthropic_complete`. Synthesis: mock `lattice.synthesis.make_llm_client`. Selection has 0 LLM calls.

**Atom storage**: every atom is a `.md` file with YAML frontmatter. `LatticeDB` has `_atom_cache` (per-instance). BM25 cached as `_bm25_cache` keyed by frozenset of atom IDs — invalidated on every `write()` or `supersede()`.

**Graph sidecars**: `LatticeGraph` writes `LATTICE_DIR/graph/` on every atom write. `db.preload()` loads from sidecars if manifest atom_count matches; otherwise rebuilds. Selection uses BFS over graph edges to expand evidence packs from BM25 seeds.

### Test conventions

All tests mock LLM via `unittest.mock.patch`. Ingest mocks two calls per atom: extraction JSON, then supersession reply (`'{"superseded_atom_ids": []}'`). Use `tmp_path` for isolated `LatticeDB` instances. Construct `Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")` directly — no `monkeypatch.setenv`. Mock `lattice.conversation.complete` for classify_intent and reformulate_capture tests.

### Memory: Lattice is the sole memory system

**Do not write user facts, preferences, or decisions to Claude's internal auto-memory system.** Do not save anything to `~/.claude/projects/.../memory/`. Lattice is the only memory store for this project.

When the user says any of: "save", "done", "goodbye", "wrap up", "end session", "save session" — summarize decisions made, things built, and conclusions reached, then call `lattice_capture` (not `lattice_ingest`) with that summary. Always set `metadata.source_id="claude-code"` and `metadata.observed_at=<current ISO timestamp>`.

When the user shares a preference, decision, fact, or anything worth remembering, call `lattice_ingest` immediately.
- Single fact from the user → set `metadata.source="user"`, `metadata.source_id="claude-code"`, `metadata.observed_at=<current ISO timestamp>`.
- Conversation chunk (multiple turns) → format as `"user: ...\nassistant: ..."` and omit `metadata.source` — the pipeline attributes per-turn automatically.

When answering a recall question ("what did I decide about X", "what do I prefer", "remind me of Y"), call `lattice_select` first and ground the answer in returned atoms.
