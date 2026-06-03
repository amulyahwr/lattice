# Lattice — Phase 2 User Stories

Stories are ordered by phase and dependency. Implement Phase 2A before touching Phase 2B.
Each story includes acceptance criteria and technical notes for the architect/engineer.

---

## Do now — pre-flight (no code, ~15 minutes)

Not stories — configuration steps that must happen before any Phase 2 code is written.
The builder has an empty Lattice instance and MCP is not wired up.

```bash
# 1. Wire MCP into Claude Code
claude mcp add lattice -- uv run --directory /path/to/lattice-mcp lattice

# 2. Add to CLAUDE.md in this repo:
# "At the end of every session, call lattice_ingest with a summary of
#  what was decided, built, or learned."

# 3. Install launchd plist so daemon starts on login
cp extras/dev.lattice.daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

The plist file (`extras/dev.lattice.daemon.plist`) must be committed to the repo.
Engineered `lattice-daemon install` command is deferred to STORY-001 (Phase 2B).

---

## Phase 2A — unblock the builder

**Exit criterion: one genuine "oh wow" recall moment** — Lattice returns something the
builder had forgotten but actually needed. Not time-based. Not query-count-based.
That single moment validates the core loop and unlocks Phase 2B.

One story only. Nothing else ships in Phase 2A.

---

### Epic 0 — Session capture

#### STORY-002 · `lattice_capture` — session-end MCP tool

**As a** host AI (Claude) finishing a conversation session,
**I want** to call `lattice_capture` with the session content,
**so that** every AI conversation becomes memory automatically without the user doing anything.

**Acceptance criteria (engineering — testable in code):**
- `lattice_capture` appears in `list_tools()` alongside existing tools
- Accepts `{"source": "<text>", "metadata": {"session_id": "...", "title": "..."}}` — same schema as `lattice_ingest`
- Returns `{"atom_ids": [...], "count": <n>}`
- Behaviorally identical to `lattice_ingest` at the wire level
- Tool description contains the exact text: "Call this at the end of a session to persist what was discussed as memory. Do not call lattice_select or lattice_answer to verify atoms already injected into context — treat injected lattice atoms as authoritative."

**Manual validation (builder validates during Phase 2A daily use):**
- Run a Claude Code session, let it call `lattice_capture` at the end
- Log MCP tool calls; confirm `lattice_select` is not called redundantly afterward
- If re-querying still occurs, the tool description needs strengthening — not a code fix

**Technical notes:**
- Add one new `Tool` entry to `server.py:list_tools()` — handler is a direct copy of `lattice_ingest` handler
- ~15 lines in `server.py`
- No new deps, no schema changes

---

## Phase 2B — distribution

Start only after Phase 2A exit criterion is met.

**Ordering:** VS Code → `lc` → `lattice setup` → browser extension → Apple Shortcuts → on-demand

---

### Epic 1 — HTTP Ingest API (build before any Phase 2B client except `lc`)

> STORY-003 unblocks VS Code, browser extension, and Shortcuts.
> `lc` (STORY-007) is independent — it uses the Unix socket, not HTTP.

#### STORY-003 · `POST /api/ingest` endpoint

**As a** capture client (VS Code extension, browser extension, Apple Shortcuts),
**I want** to POST plain text to `http://localhost:7337/api/ingest`,
**so that** I can send content to Lattice without filesystem access or Unix socket knowledge.

**Acceptance criteria:**
- `POST /api/ingest` with `{"text": "...", "source_id": "..."}` returns `{"ok": true, "atom_ids": [...]}` on success
- `source_id` optional; defaults to `"http"`
- Daemon not running → `503` with `{"ok": false, "error": "daemon unavailable"}`
- Malformed body → `422`
- Bound to `127.0.0.1` only — never exposed to LAN

**Technical notes:**
- Add to `lattice/web/app.py`
- Call `DaemonClient().ingest(text, source_id)` from `lattice/client.py`
- Catch `RuntimeError` from `DaemonClient.ingest()` → return `503`
- ~25 lines

#### STORY-004 · CORS headers for browser clients

**As a** browser extension running in Chrome/Safari/Firefox,
**I want** CORS headers on `/api/ingest`,
**so that** the extension can POST to `localhost:7337` without being blocked.

**Acceptance criteria:**
- `OPTIONS /api/ingest` returns `200` with `Access-Control-Allow-Origin: *`, `Access-Control-Allow-Methods: POST`, `Access-Control-Allow-Headers: Content-Type`
- CORS scoped to `/api/ingest` only — all other endpoints unaffected
- Existing web UI unaffected (same-origin)

**Note:** VS Code extensions run in Node.js — not subject to browser CORS. STORY-004 is only a dependency for browser extension (STORY-008) and Apple Shortcuts (STORY-009). Not required for VS Code stories.

**Technical notes:**
- `@app.options("/api/ingest")` + headers on POST handler, or scoped `CORSMiddleware`
- ~10 lines

**Depends on:** STORY-003

---

### Epic 2 — VS Code extension (first in Phase 2B)

#### STORY-005 · Capture from VS Code

**As a** developer in VS Code or Cursor,
**I want** to run "Lattice: Save" from the command palette,
**so that** selected code or a quick note is saved to memory without leaving the IDE.

**Acceptance criteria:**
- "Lattice: Save to memory" captures: (a) selected text if selection exists, else (b) prompts for a typed note via quick-input
- Uses `source_id = "vscode"`
- Success: status bar flash "Lattice: saved (N atoms)"
- Daemon down: status bar "Lattice: daemon unavailable — run lattice-daemon"
- Exit: pressing Escape on the quick-input prompt does nothing (no error)

**Technical notes:**
- TypeScript VS Code Extension API
- Works in both VS Code and Cursor — Cursor runs VS Code extensions natively
- Publish to VS Code Marketplace (open-source required)
- Backend: `POST /api/ingest` (HTTP, no CORS needed — Node.js process)
- **Depends on:** STORY-003 only (not STORY-004)

#### STORY-006 · Recall from VS Code

**As a** developer,
**I want** to run "Lattice: Ask" and type a question,
**so that** I get a synthesized answer in a VS Code side panel without opening a browser.

**Acceptance criteria:**
- "Lattice: Ask" opens a side panel with a text input
- Answer streams in with numbered citations; each new query replaces current content (no history, no conversation state)
- Citations show `source_id` where available (e.g. `vscode` for IDE-captured atoms)
- Daemon down: panel shows "Lattice daemon unavailable — run lattice-daemon"

**Technical notes:**
- VS Code Webview API for the side panel
- `POST /api/query` SSE stream — parse `data:` lines, render incrementally
- **Depends on:** STORY-003 only (not STORY-004)

---

### Epic 3 — `lc` terminal command (second in Phase 2B)

#### STORY-007 · `lc` one-liner capture

**As a** developer in the terminal,
**I want** to type `lc "decided X because Y"`,
**so that** thoughts outside Claude sessions are captured without switching apps.

**Acceptance criteria:**
- `lc <text>` ingests and prints `✓ captured (N atoms)`
- Uses `source_id = "lc"`
- `lc` with no args prints usage and exits 1
- Daemon not running → exits 1 with "Lattice daemon not running. Start with: lattice-daemon"
- Exit code 0 on success, 1 on any error

**Technical notes:**
- New entry point `lc` in `pyproject.toml` → `lattice.cli:lc`
- New file `lattice/cli.py`
- Uses `DaemonClient().ingest(text, "lc")` via Unix socket (`lattice/client.py`)
- No fallback to file drop — fail fast, surface the real problem
- No external deps
- **Independent** — does not depend on STORY-003 or STORY-004

---

### Epic 4 — Minimal setup command (third in Phase 2B — before handing to second person)

#### STORY-001 · `lattice setup` — builder onboarding

**As a** builder handing Lattice to a second person,
**I want** a `lattice setup` command that writes the env file, registers the MCP, and starts the daemon,
**so that** setup takes one command instead of reading docs and editing config files manually.

**Acceptance criteria:**
- `lattice setup` prompts for: `LATTICE_DIR` (default `~/.lattice`), LLM provider (ollama / openrouter / openai / anthropic), API key if required, model name
- Writes `.env.lattice` to `LATTICE_DIR`
- Runs `claude mcp add lattice -- uv run lattice` automatically; warns gracefully if `claude` CLI not found
- Installs and loads launchd plist (`~/Library/LaunchAgents/dev.lattice.daemon.plist`) — replaces the manual "do now" step
- Starts daemon and opens `http://localhost:7337` in browser
- `--dry-run` flag prints config without writing or starting anything
- No hardware detection, no RAM probing — that's STORY-011 (path-C gate)

**Technical notes:**
- New file `lattice/setup.py` + entry point `lattice-setup` in `pyproject.toml`
- `Config.from_env()` already centralises path/port vars — wizard writes the env file
- No new deps

---

### Epic 5 — Browser extension (fourth in Phase 2B)

#### STORY-008 · Save selected text from any webpage

**As a** user reading something in Chrome, Safari, or Firefox,
**I want** to select text and right-click → "Save to Lattice",
**so that** web content becomes memory in one click.

**Acceptance criteria:**
- Right-click context menu shows "Save to Lattice" only when text is selected; hidden otherwise
- One click — no popup, no confirmation — POSTs selected text to `POST /api/ingest`
- Uses `source_id = "browser:<hostname>"` (e.g. `"browser:github.com"`)
- Page title + URL passed as `metadata.title` and `metadata.url`
- Success: brief non-intrusive toast "Saved to Lattice"
- Daemon not running → toast "Lattice daemon not running. Run: lattice-daemon"
- Manifest V3 (Chrome/Edge); Firefox compatible

**Technical notes:**
- `content_scripts` inject into all pages; `chrome.contextMenus.create` with `contexts: ["selection"]`
- Background service worker handles `POST /api/ingest`
- CORS required — depends on STORY-004
- Open-source; publish to Chrome Web Store + Firefox Add-ons
- **Depends on:** STORY-003, STORY-004

---

### Epic 6 — Apple Shortcuts (fifth — on-demand)

#### STORY-009 · "Save to Lattice" Shortcut with global hotkey

**As a** macOS user who has a thought outside Claude, VS Code, or the browser,
**I want** to press a hotkey from anywhere and type a quick note,
**so that** I can capture without switching to any specific app.

**Acceptance criteria:**
- A pre-built `.shortcut` file committed at `extras/Save to Lattice.shortcut`
- When run: pops a text-input dialog, POSTs to `http://localhost:7337/api/ingest` with `source_id = "shortcuts"` via Shortcuts "Get contents of URL" action, shows result notification
- User assigns any hotkey in Shortcuts.app (documented in README)
- Zero native code — pure Shortcuts automation, no app bundle
- Daemon down → Shortcuts shows error from the failed URL action

**Technical notes:**
- Build and export the `.shortcut` file manually in Shortcuts.app; commit binary to `extras/`
- "Get contents of URL" supports POST with JSON body — no Lattice code changes needed
- **Depends on:** STORY-003 (HTTP endpoint must exist); does not need STORY-004 (URLSession, not browser)

---

### Epic 7 — Onboarding full (path-C gate — ship when first non-builder user arrives)

#### STORY-010 · Homebrew formula

**As a** developer evaluating Lattice,
**I want** `brew install lattice`,
**so that** setup takes minutes without Python environment knowledge.

**Acceptance criteria:**
- `brew install lattice` installs `lattice-daemon`, `lattice`, and `lc` binaries
- Post-install message: "Run `lattice setup` to configure and start"
- Formula pins Python version; uses a venv

#### STORY-011 · Hardware-aware model selection

**As a** non-technical user who doesn't know what Ollama is,
**I want** `lattice setup` to detect my hardware and recommend the right model,
**so that** I make zero model decisions.

**Acceptance criteria:**
- Detects RAM, GPU type (Apple Silicon unified vs NVIDIA discrete)
- Maps to tier: <8 GB → OpenRouter; 8–16 GB unified → `qwen3:4b`; 16–32 GB unified → `qwen3:8b`; 32+ GB → `qwen3:14b`
- Ollama tier: checks pulled models; offers to pull missing ones
- OpenRouter tier: prompts for API key, validates with test call
- `--dry-run` prints config without writing

**Note:** Extends STORY-001. Ship STORY-001 first; this story adds hardware detection on top.

**Technical notes:**
- `psutil` for RAM, `platform` for chip, `subprocess` for `ollama list`
- Extend `lattice/setup.py` from STORY-001

---

### Epic 8 — Feedback + telemetry (Phase 2B, parallel track)

#### STORY-012 · Feedback analysis endpoint + UI

**As a** builder running Lattice daily,
**I want** a summary of which questions are failing and why,
**so that** I can act on feedback without reading raw JSONL.

**Acceptance criteria:**
- `GET /api/feedback/analysis` returns: total queries, thumbs-up rate, top 3 failure reasons by count, top 5 most-downvoted questions
- Web UI: collapsible "Feedback" section in sidebar
- Covers last 7 days and all-time
- Empty state when no feedback yet

**Technical notes:**
- Read `LATTICE_DIR/feedback.jsonl` (already written by `app.py:api_feedback`)
- New endpoint in `app.py` + new sidebar component in `lattice/web/static/`

#### STORY-013 · Local usage telemetry + streak

**As a** builder validating daily use,
**I want** Lattice to track my query streak locally,
**so that** I know whether I'm actually using it without reading logs.

**Acceptance criteria:**
- Each query appended to `LATTICE_DIR/usage.jsonl`: `{ts, query_hash, selection_ms, synthesis_ms, atom_count}` — `query_hash` is SHA-1 of question text (not raw text, privacy)
- `GET /api/usage/summary` returns: queries today, last 7 days, avg latency, streak count
- Streak = consecutive days ending today with ≥1 query; resets to 0 if today has no queries; always shown from day 1 (day 1 shows "Day 1")
- Web UI header shows streak on every page load
- No external service, no network call

**Technical notes:**
- Write in `app.py:api_query` after synthesis completes
- Streak: aggregate `usage.jsonl` dates at request time — no cron needed

---

### Epic 9 — PDF ingest (Phase 2B, parallel track)

#### STORY-014 · PDF parser

**As a** user who drops a PDF into the inbox,
**I want** Lattice to extract and atomize its text,
**so that** documents become searchable memory.

**Acceptance criteria:**
- Daemon picks up `.pdf` files from inbox alongside `.md` and `.txt`
- Extracts plain text; page breaks become segment boundaries
- Atoms carry `source_id` derived from filename (e.g. `"pdf:report.pdf"`)
- Image-only PDFs: log warning and skip gracefully (no OCR, no crash)
- Tested on a 10-page PDF: atoms created, no crash

**Technical notes:**
- New `lattice/parsers/pdf.py` using `pypdf` (pure Python, no system deps)
- Add `.pdf` extension check in daemon watchdog before `infer_source_type()`
- `pypdf` as optional dep: `[project.optional-dependencies] pdf = ["pypdf"]`

---

### Epic 10 — Reminders (Phase 2B, parallel track)

#### STORY-015 · Prospective memory atoms

**As a** user who says "follow up with Alex next week",
**I want** Lattice to capture this as a reminder with a trigger date,
**so that** it surfaces automatically without me setting a calendar event.

**Acceptance criteria:**
- LLM extracts `kind=reminder` atoms with `trigger_at: <ISO date>` when ingest content contains future intent ("next week", "tomorrow", "by Friday", etc.)
- Ingest prompt updated with `kind=reminder` examples showing date extraction
- Daemon checks pending reminders on startup and every hour; logs count
- Web UI sidebar "Reminders" section: pending items with related context atoms (BM25+BFS on subject)
- Dismissed reminders: `is_superseded=true`

**Technical notes:**
- Add `trigger_at: datetime | None` to `Atom` in `models.py`
- Add `kind=reminder` examples to ingest prompt in `ingest.py`
- Daemon scheduler: `threading.Timer` loop — no new dep
- New `GET /api/reminders/pending` endpoint + sidebar component

---

## Dependency map

```
Phase 2A (ship first — one story)
└── STORY-002 (lattice_capture MCP tool)

Phase 2B ordering
├── STORY-003 (POST /api/ingest)          ← build before VS Code
│   ├── STORY-005/006 (VS Code)           ← first (no CORS needed)
│   ├── STORY-004 (CORS)
│   │   ├── STORY-008 (browser ext)       ← fourth
│   │   └── STORY-009 (Apple Shortcuts)   ← fifth, on-demand
│   └── STORY-001 (lattice setup)         ← third
│
├── STORY-007 (lc CLI) — independent      ← second
├── STORY-010/011 (Homebrew + wizard) — independent, path-C gate
├── STORY-012 (Feedback analysis) — independent, parallel
├── STORY-013 (Usage telemetry) — independent, parallel
├── STORY-014 (PDF parser) — independent, parallel
└── STORY-015 (Reminders) — independent, parallel
```

---

## Dropped from scope

| Story | Reason |
|-------|--------|
| Raycast extension | Superseded by Apple Shortcuts + global hotkey. No third-party dependency. |
| Obsidian plugin | Builder doesn't use Obsidian. Add back if usage data reveals the gap. |
| macOS Share extension | Swift overhead > value for current persona. Inbox drop covers the manual case. |
| `lc --recall` | MCP-driven recall (Claude queries Lattice inline) is the primary recall surface for builders. |
| VS Code panel history | Conversational recall is Phase 3. Panel shows one answer at a time. |
| `lc` inbox fallback | Fail fast — silent fallback masks daemon problems. |

---

## Out of scope (Phase 3+)

- Multi-device sync
- Conversational recall / follow-up questions
- First-class namespaces
- Screenpipe integration
- Contradiction detection UX (blocked on M6 semantic enrichment)
- Ingest staging gate
- Bundled installer / mobile app
