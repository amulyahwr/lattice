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

Required env vars: `LLM_PROVIDER`, `LLM_MODEL`, `LATTICE_DIR`. `LLM_API_KEY` required for all providers except `ollama`. Per-stage model overrides: `INGEST_MODEL`, `SYNTHESIS_MODEL`. `LLM_BASE_URL` overrides the API endpoint — use for OpenRouter (`https://openrouter.ai/api/v1`), Anthropic-compat (`https://api.anthropic.com/v1`), or any OpenAI-compat endpoint; set `LLM_PROVIDER=openai` in all cases.

## Architecture

The current pipeline is: **ingest → select → synthesize**. Ingest and synthesis use LLM via `lattice/llm.py`; selection is LLM-free (BM25 + graph BFS). The product direction is local-first lattice: source-aware ingest, provenance, deterministic graph sidecars, graph-seeded selection, and optional enrichment that never blocks local querying.

```
server.py          MCP stdio entrypoint. Owns one shared LatticeDB instance.
lattice/
  config.py        Centralised env-var parsing → Config dataclass. All path/port vars here;
                   LLM vars stay in llm.py pending refactor.
  llm.py           openai.OpenAI wrapper. make_llm_client() builds client from env; resolve_model()
                   returns model name or raises EnvironmentError if LLM_MODEL unset; complete() calls
                   chat.completions.create. Ollama gets extra_body={num_ctx, think:false}; others don't.
  models.py        Atom pydantic model + markdown serialization (python-frontmatter).
  db.py            File-based store: one .md file per atom in LATTICE_DIR. BM25 search.
                   subjects.json is a subject→atom_id index for O(1) supersession lookups.
                   Holds a LatticeGraph instance; updated on every write/supersede/preload.
  graph.py         Heterogeneous graph index (networkx MultiDiGraph). Writes committed
                   sidecars to LATTICE_DIR/graph/{nodes.jsonl,edges.jsonl,manifest.json}.
                   Node types: atom:<id>, source:<id>, segment:<cid>:<sid>, subject:<norm>.
                   Edge types: source_contains_segment, segment_contains_atom,
                   atom_has_subject, same_subject_as, same_hash, supersedes.
  daemon.py        Persistent process that owns all LatticeDB writes. Watches LATTICE_INBOX
                   via watchdog; processes dropped files → ingest → moves to processed/.
                   IPC via Unix socket (LATTICE_SOCK). Also spawns the FastAPI web server.
                   JSON-lines log to LATTICE_DIR/daemon.log.
  client.py        DaemonClient: thin IPC wrapper over the Unix socket. Used by server.py
                   to delegate writes to the daemon.
  parsers/         Source-aware pre-ingest segmentation. `infer_source_type()` detects chat/
                   markdown/code. `parse()` returns list[Segment] with role, context, span.
                   chat.py preserves turn windowing + role field. markdown.py splits on headings.
  ingest.py        Segments source via parsers/, then LLM extracts atoms per segment,
                   then checks supersession per atom.
  query.py         Query intent classifier: detects aggregation/temporal/recommendation/preference
                   signals. Returns QueryIntent with shape + primary_kind. Stateless; used by selection.py.
  selection.py     select() = _retrieve(): BM25 scored seeds → zero-score seed filter
                   (LATTICE_SEED_MIN_SCORE) → source-diversity probe → graph BFS → optional BFS
                   rescore (LATTICE_BFS_RESCORE) → atom dicts. 0 LLM calls.
  synthesis.py     LLM generates prose answer from atom dicts. Uses SYNTHESIS_MODEL env var
                   (falls back to LLM_MODEL). Ollama path uses OpenAI-compat client with
                   num_ctx=4096 and tool calls for date_diff + sum_numbers.
  embed.py         Optional semantic embedding via fastembed (install semantic extra). Guards
                   import; no-ops cleanly if fastembed absent. Not on hot query path.
  util.py          Shared helpers: write_file_atomic, _normalized_subject.
  cli.py           Entry point for `lc` terminal command. `lc <text>` captures via DaemonClient
                   over Unix socket; fails fast if daemon not running. `lc status` reads LatticeDB
                   directly (no daemon needed) and prints memory count.
  telegram_bot.py  Telegram polling bot (STORY-018). Runs as independent launchd service
                   (dev.lattice.telegram.plist) — not a daemon subprocess. On daemon-down:
                   writes inbox file as telegram-{chat_id}-{uuid}.txt and replies immediately.
                   Daemon drains inbox on startup (_drain_inbox) and sends follow-up reply via
                   urllib using LATTICE_TELEGRAM_TOKEN. Requires: uv sync --group telegram.
  web/app.py       FastAPI app: GET / (chat UI), POST /api/ingest (HTTP capture — source_id +
                   metadata pass-through, observed_at server-stamped), POST /api/query (streaming
                   SSE synthesis), GET /api/atoms/recent (recent atoms JSON), POST /api/feedback.
                   Started by daemon.
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
| Capture (ingest) | ✅ | ✅ | ✅ | ✅ | ✅ right-click / ⌥⇧S | planned |
| File ingest | ✅ `file_path` | ✅ drag-drop | ✅ `lc path/to/file` | ✅ document attach | — | planned |
| Recall (synthesized answer) | ✅ | ✅ | — (out of scope) | ✅ auto-detect + `/ask` | — | planned |
| Session-end capture | ✅ | ✅ Save session btn | — (atomic by design) | ✅ `/save` | — | — |
| Memory count / status | ✅ `lattice_status` | ✅ (recent atoms) | ✅ `lc status` | ✅ `/status` | ✅ popup count | — |
| Daemon status | — | — | — | — | ✅ popup dot | — |
| Recall feedback | ❌ redundant (Claude Code has own UI) | ✅ thumbs + reason (all answers) | — (no recall) | ✅ 👍/👎 (all answers) | — | — |
| Usage streak | ✅ `lattice_status` | ✅ "N days deep" badge | ✅ `lc status` shows streak | ✅ `/status` shows streak | — | — |
| Milestone moments | — | ✅ cards Day 1/7/14/30 | ✅ `lc status` prints msg | ✅ prepended on recall | — | — |
| PII indicator | — (no UI) | ✅ `🔒` badge | — (no recall) | ✅ `🔒 PII protected` footer | — | — |
| Rediscovery highlight | — (no UI) | ✅ amber glow | — (no recall) | ✅ age note in answer | — | — |
| Weekly report | — | ✅ Monday card | — | ✅ Monday prepend | — | — |
| Topic depth | — | ✅ depth cards | ✅ note on capture | ✅ note on capture | — | — |

*not yet built. Update this table whenever a channel ships or gains a capability.

### Product roadmap guardrails

- Keep architecture local-first: no hosted service, no required daemon, no external DB.
- Keep atoms human-readable and git-trackable.
- Treat LongMemEval as an eval yardstick only; do not add benchmark-shaped hacks to product paths.
- Prefer provenance fields and graph edges over mutating atom content for retrieval.
- Query paths should use committed snapshots and should not wait for active ingest/enrichment.
- Expensive relation enrichment, embeddings, and hub labeling must remain optional, especially for Ollama users.

### Key data flow details

**Supersession** (in `ingest.py`): when a new atom has the same subject as an existing one, an LLM call decides if it supersedes. Fast path uses `subjects.json`; slow path scans files (handles hand-edited atoms). Superseded atoms stay on disk with `is_superseded=true` and bidirectional links (`superseded_by` / `supersedes`).

**LLM calls**: ingest/supersession go through `lattice.llm.complete(messages)`. Tests mock at `lattice.ingest.complete` — patch the module-level name, not `lattice.llm.complete`. Synthesis is different: patch `lattice.synthesis.make_llm_client` (returns a mock OpenAI client). Selection has no LLM calls.

**Atom storage**: every atom is a `.md` file with YAML frontmatter. `LatticeDB` has an in-memory cache (`_atom_cache`). Cache is per-instance; `server.py` reuses one instance per process.

**BM25**: cached on `LatticeDB` as `_bm25_cache` keyed by frozenset of atom IDs. Invalidated on every `write()` or `supersede()`. Rebuilt lazily on next `search()` call.

**Graph sidecars**: `LatticeGraph` writes `LATTICE_DIR/graph/` on every atom write. `db.preload()` loads from sidecars if manifest atom_count matches; otherwise rebuilds. Access via `db.graph`. Selection uses BFS over graph edges to expand evidence packs from BM25 seeds.

This is current MVP behavior, not the target product shape.

### Test conventions

All tests mock LLM via `unittest.mock.patch`. Ingest responses mock two calls per atom: first the extraction JSON, then the supersession reply (`"null"` or an atom_id string). Use `tmp_path` fixture for isolated `LatticeDB` instances.

### Memory: Lattice is the sole memory system

**Do not write user facts, preferences, or decisions to Claude's internal auto-memory system.** Do not save anything to `~/.claude/projects/.../memory/`. Lattice is the only memory store for this project.

When the user says any of: "save", "done", "goodbye", "wrap up", "end session", "save session" — summarize decisions made, things built, and conclusions reached, then call `lattice_capture` (not `lattice_ingest`) with that summary. Always set `metadata.source_id="claude-code"` and `metadata.observed_at=<current ISO timestamp>`.

When the user shares a preference, decision, fact, or anything worth remembering, call `lattice_ingest` immediately.
- Single fact from the user → set `metadata.source="user"`, `metadata.source_id="claude-code"`, `metadata.observed_at=<current ISO timestamp>`.
- Conversation chunk (multiple turns) → format as `"user: ...\nassistant: ..."` and omit `metadata.source` — the pipeline attributes per-turn automatically.

When answering a recall question ("what did I decide about X", "what do I prefer", "remind me of Y"), call `lattice_select` first and ground the answer in returned atoms.
