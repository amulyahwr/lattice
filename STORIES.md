# Lattice — Phase 2 User Stories

Stories are ordered by phase and dependency. Implement Phase 2A before touching Phase 2B.
Each story includes acceptance criteria and technical notes for the architect/engineer.

---

## Do now — pre-flight ✅ COMPLETE

Not stories — configuration steps that must happen before any Phase 2 code is written.
The builder has an empty Lattice instance and MCP is not wired up.

```bash
# 1. Wire MCP into Claude Code
claude mcp add lattice -- uv run --directory /path/to/lattice-mcp lattice

# 3. Install launchd plist so daemon starts on login
cp extras/dev.lattice.daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

**Step 2 — add this block to CLAUDE.md in this repo:**

```
When the user says any of: "save", "done", "goodbye", "wrap up",
"end session", "save session" — summarize what was decided, built,
or learned in this session and call lattice_ingest with that summary.
```

**Important:** hitting X closes the window without Claude acting — the instruction
above only fires during an active turn. Build the habit: say "save" before closing.
Closing without saying "save" = session not captured.

**Step 4 — add Lattice priority instruction to CLAUDE.md:**

```
When the user shares a preference, decision, fact, or anything worth remembering,
call lattice_ingest immediately — do not rely on Claude's internal memory.
When answering a recall question ("what did I decide about X", "what do I prefer",
"remind me of Y"), call lattice_select first and ground the answer in returned atoms.
```

This fixes Claude defaulting to its own context window instead of Lattice. Without it,
preferences land in Claude's ephemeral memory and are lost between sessions.

**Step 5 — allow Lattice MCP tools without permission prompts:**

Add to `.claude/settings.json` (create if absent):

```json
{
  "allowedTools": [
    "mcp__lattice__lattice_ingest",
    "mcp__lattice__lattice_select",
    "mcp__lattice__lattice_answer"
  ]
}
```

Without this, Claude Code prompts for approval on every tool call — killing the ambient feel.

The plist file (`extras/dev.lattice.daemon.plist`) must be committed to the repo.
Engineered `lattice-daemon install` command is deferred to STORY-001 (Phase 2B).

---

## Phase 2A — unblock the builder

**Exit criterion: one genuine "oh wow" recall moment** — Lattice returns something the
builder had forgotten but actually needed. Not time-based. Not query-count-based.
That single moment validates the core loop and unlocks Phase 2B.

Two stories only. Nothing else ships in Phase 2A.

---

### Epic 0 — Staleness fix (ship before STORY-002)

#### STORY-016 ✅ · `_db` staleness — preload before select

**As a** user querying Lattice after the daemon has ingested atoms,
**I want** `lattice_select` and `lattice_answer` to see atoms written after server startup,
**so that** recall works without restarting the MCP server.

**Acceptance criteria:**
- `lattice_select` returns atoms ingested after server.py started
- `lattice_answer` same
- No restart required after first ingest into a previously empty lattice

**Technical notes:**
- Root cause: `server.py` calls `_db.preload()` once at startup; `db.graph` is stale (0 nodes if lattice was empty); new atoms written by daemon are not visible to the graph path in `_retrieve()`
- Fix: call `_db.preload()` at the top of the `lattice_select` and `lattice_answer` handlers in `server.py`
- `preload()` is already incremental — skips atoms in `_atom_cache` (db.py:137), only rebuilds graph if manifest count changed (db.py:147). Per-query cost: one dir glob + one manifest read
- ~2 lines added to `server.py`
- No new deps, no schema changes

**Depends on:** nothing

---

### Epic 0 — Session capture

#### STORY-002 ✅ · `lattice_capture` — session-end MCP tool

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
- Also update `lattice_ingest` tool description to guide AI assistants to pass proper metadata: `source` (`"user"` if content came from the user, `"assistant"` if AI-generated), `source_id` (surface name e.g. `"claude-code"`), `observed_at` (current ISO timestamp). Without this, `source` defaults to `"document"` (LLM-guessed, meaningless).
- `lattice_capture` description focuses on decisions/outcomes at session end — it does not attempt to avoid re-stating real-time atoms. Deduplication between real-time and session-end atoms is handled by the existing pipeline (content hash exact dedup + subject-based supersession). No caller-side coordination logic.
- ~20 lines in `server.py`
- No new deps, no schema changes

---

## Phase 2B — distribution

Start only after Phase 2A exit criterion is met.

**Ordering:** `lc` → Telegram → VS Code → `lattice setup` → browser extension → Apple Shortcuts → menu bar → on-demand

---

### Epic 1 — HTTP Ingest API (build before any Phase 2B client except `lc`)

> STORY-003 unblocks VS Code, browser extension, and Shortcuts.
> `lc` (STORY-007) is independent — it uses the Unix socket, not HTTP.

#### STORY-003 ✅ · `POST /api/ingest` endpoint

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

### Epic 2 — VS Code extension (third in Phase 2B)

> **Builder note:** STORY-005/006 are TypeScript, not Python — separate repo, different language,
> VS Code Extension API, and Marketplace publishing required. Bigger lift than the Python stories.
> Backend dependency (STORY-003 ✅) is already done. `lc` (STORY-007 ✅) and Telegram (STORY-018 ✅)
> shipped. Start VS Code when ready to context-switch to TypeScript.

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

#### STORY-007 ✅ · `lc` one-liner capture

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

### Epic 3B — Telegram mobile capture (third in Phase 2B)

> Covers Android and any phone with Telegram. Validates the mobile capture habit before
> building the native mobile app (Phase 3). Apple Shortcuts (STORY-009) ships in parallel
> for iPhone/macOS users. Both depend on STORY-003.

#### STORY-018 ✅ · Telegram bot — text capture from phone

**As a** user on my phone away from my laptop,
**I want** to send a text message to a Telegram bot,
**so that** the thought is saved as atoms in Lattice without opening a browser or app.

**Acceptance criteria:**
- User sends any text message to the bot → bot POSTs to `POST /api/ingest` with `source_id = "telegram"`
- Bot replies inline: `✓ saved N atoms` on success; `⚠ daemon offline — queued to inbox` if daemon down
- Bot only accepts messages from `LATTICE_TELEGRAM_ALLOWED_IDS` (comma-separated); silently drops all others
- `lattice-telegram setup` command: interactive enrollment — user sends `/start` to bot, command captures sender ID, writes `LATTICE_TELEGRAM_TOKEN` + `LATTICE_TELEGRAM_ALLOWED_IDS` to `.env.lattice`
- Daemon spawns bot as subprocess when `LATTICE_TELEGRAM_TOKEN` is set; silently skips if absent
- If daemon is down: bot falls back to inbox file drop (same fallback as `lattice_ingest`)
- Messages queue on Telegram's servers while laptop is off; processed in order when bot reconnects

**Technical notes:**
- `python-telegram-bot` library (polling mode — no port forwarding, works behind NAT)
- New `lattice/telegram_bot.py` + entry point `lattice-telegram` in `pyproject.toml`
- Daemon spawns via `subprocess.Popen` in `daemon.py` when env var present; process exits with daemon
- `lattice-telegram setup` in `lattice/setup.py` — extend existing setup module
- Optional dep: `[project.optional-dependencies] telegram = ["python-telegram-bot"]`
- **Depends on:** STORY-003

#### STORY-019 ✅ · Daemon Power Nap resilience

**As a** macOS user with laptop lid closed,
**I want** the Lattice daemon (and Telegram bot) to wake during Power Nap,
**so that** messages are processed within minutes even when the screen is off.

**Acceptance criteria:**
- `ProcessType = Background` set in `extras/dev.lattice.daemon.plist`
- Daemon wakes during Power Nap (plugged in) and processes Telegram message backlog
- No behaviour change when laptop is fully awake
- Existing `lattice setup` wizard installs the updated plist automatically

**Technical notes:**
- One line added to `extras/dev.lattice.daemon.plist`
- No code changes
- **Depends on:** STORY-018 (ships alongside it)

---

### Epic 4 — Minimal setup command (fourth in Phase 2B — before handing to second person)

#### STORY-001 · `lattice setup` — builder onboarding

> **Competitive urgency (from SWOT):** GBrain requires Postgres + VPS — a setup cost most users won't pay. Lattice's answer is zero-infra. `lattice setup` is what makes that real for non-builders. Ship before Jan.ai adds persistent memory — distribution speed is the moat.

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

### Epic 6B — Menu bar app (Phase 2B — after browser extension)

#### STORY-020 · macOS menu bar wrapper

**As a** non-technical user on macOS,
**I want** a menu bar icon for Lattice,
**so that** I can see daemon status and capture a quick note from anywhere without remembering a localhost port.

**Acceptance criteria:**
- Menu bar icon shows daemon status: green (running), amber (no atoms yet), red (stopped)
- Click → dropdown: "Ask Lattice…" opens `http://localhost:7337` in browser; "Save a note…" opens a one-line text input; "Quit" stops daemon
- "Save a note…" input: type text → Enter → POSTs to `POST /api/ingest`, shows brief OS notification `✓ saved N atoms`
- Global hotkey (user-configurable, default ⌘⇧Space) opens "Save a note…" from anywhere
- Daemon not running: icon red, click → "Start Lattice daemon" option
- Auto-starts with login via existing launchd plist (no second plist needed)

**Technical notes:**
- `rumps` library (pure Python macOS menu bar, ~200 lines)
- New `lattice/menubar.py` + entry point `lattice-menubar` in `pyproject.toml`
- Daemon spawns menubar as subprocess alongside Telegram bot (same pattern as STORY-017)
- Optional dep: `[project.optional-dependencies] menubar = ["rumps"]`
- macOS only — skip silently on other platforms
- **Depends on:** STORY-003

---

### Epic 6C — Cloudflare Tunnel (Phase 2B — after menu bar app)

> Unlocks three things at once: Claude mobile / ChatGPT mobile / any cloud AI app via
> remote MCP; ChatGPT Custom GPT Actions; Telegram laptop-off delivery. One tunnel,
> one launchd entry. Atoms never leave the machine — tunnel is relay-only.

#### STORY-022 · Cloudflare Tunnel — bridge to cloud AI apps

**As a** user who wants to query Lattice from Claude mobile, ChatGPT mobile, or any cloud AI app,
**I want** a persistent HTTPS URL that forwards to my local Lattice,
**so that** any AI app can reach my memory store without my laptop being on the same network.

**Acceptance criteria:**
- `cloudflared` installed and running as a launchd service alongside the daemon
- Tunnel URL written to `LATTICE_DIR/tunnel.url` on start; daemon logs it
- `lattice setup` installs the tunnel plist and prints the URL
- `/openapi.json` endpoint added to `lattice/web/app.py` — minimal spec covering `POST /api/ingest` and `POST /api/query`; enables ChatGPT Custom GPT Actions
- `GET /api/health` returns `{"ok": true}` — used by remote clients to check daemon status
- README documents how to add the tunnel URL as a remote MCP server in Claude desktop, Claude mobile, and ChatGPT

**Technical notes:**
- `cloudflared tunnel --url http://localhost:7337 --no-autoupdate` — no Cloudflare account required (quick tunnels)
- For persistent URL (same URL on every restart): requires free Cloudflare account + named tunnel (`cloudflared tunnel create lattice`)
- Launchd plist: `extras/dev.lattice.tunnel.plist` — separate from daemon plist so tunnel can be disabled independently
- `/openapi.json`: FastAPI can auto-generate from route definitions — minimal manual work
- **Security note:** tunnel exposes Lattice to the internet. `/api/ingest` should check `LATTICE_TUNNEL_TOKEN` header if set (optional env var); unauthenticated by default for local-first simplicity
- **Depends on:** STORY-003 (HTTP ingest endpoint must exist)

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

#### STORY-013 ✅ · Local usage telemetry + streak

**As a** builder validating daily use,
**I want** Lattice to track my query streak locally,
**so that** I know whether I'm actually using it without reading logs.

**Acceptance criteria:**
- Each recall query appended to `LATTICE_DIR/usage.jsonl`: `{ts, query_hash, selection_ms, synthesis_ms, atom_count, channel}` — `query_hash` is SHA-1 of question text (not raw text, privacy); `channel` = `"web"` / `"telegram"` / `"mcp"`
- Written from ALL recall channels: `POST /api/query` (web UI), `POST /api/answer` (Telegram), `lattice_answer` MCP tool — streak is only meaningful if it counts all recall, not just web UI
- `GET /api/usage/summary` returns: queries today, last 7 days, avg latency, streak count
- Streak = consecutive days ending today with ≥1 query; resets to 0 if today has no queries; always shown from day 1 (day 1 shows "Day 1")
- Web UI header shows streak on every page load
- No external service, no network call

**Technical notes:**
- Extract `_record_usage(question, selection_ms, synthesis_ms, atom_count, channel)` helper in `app.py` — shared by `api_query` and `api_answer`
- Also call from `server.py:lattice_answer` handler
- Streak: aggregate `usage.jsonl` dates at request time — no cron needed

---

### Epic 9 — PDF ingest (Phase 2B, parallel track)

#### STORY-014 ✅ · File ingest — all types, all channels

**As a** user who drops any document into the inbox,
**I want** Lattice to extract and atomize its text regardless of file type,
**so that** PDFs, slides, spreadsheets, and Word docs all become searchable memory.

**Acceptance criteria:**
- Daemon picks up `.pdf`, `.pptx`, `.xlsx`, `.xls`, `.docx` files from inbox alongside `.md` and `.txt`
- **PDF**: page breaks (`\f`) become segment boundaries; atoms carry `source_id = "pdf:<filename>"`
- **PPTX**: each `[Slide N]` marker → one segment; source_type `"pptx"`; `source_id = "<filename>.pptx"`
- **XLSX/XLS**: each `[Sheet: name]` marker → one segment; source_type `"xlsx"`/`"xls"`; `source_id = "<filename>"`
- **DOCX**: heading styles (`Heading 1`–`4`, `Title`, `Subtitle`) preserved as markdown prefix (`#`, `##`, …) before LLM extraction
- Image-only PDFs: log warning and skip gracefully (no OCR, no crash)
- File type detected from `source_id` prefix/suffix before falling back to content heuristics
- **People facts**: when text mentions a named person with contact or identity details, each detail extracted as a separate `kind=fact` atom with `subject = full name` — covers email, phone, job title, employer, location, LinkedIn/URL
- Source-specific LLM addendums injected per file type: PDF (page-scoped context), PPTX (one main point per slide), XLSX (row-per-item facts, `kind=count` for numeric aggregates)
- All file types available through all ingest channels: inbox drop, `POST /api/ingest`, `lc`, Telegram, MCP `lattice_ingest`

**Technical notes:**
- `lattice/parsers/pdf.py`: `extract_pdf_text()` → pages joined by `\f`; `parse_pdf_text()` splits on `\f`, `context="page N"`, `source_type="pdf"`
- `lattice/parsers/pptx.py` (new): splits on `[Slide N]\n` markers; `context="Slide N"`, `source_type="pptx"`
- `lattice/parsers/xlsx.py` (new): splits on `[Sheet: name]\n` markers; `context="Sheet: name"`, `source_type="xlsx"`
- `lattice/parsers/__init__.py`: `infer_source_type()` checks `metadata["source_id"]` prefix/suffix first; `parse()` dispatches to new parsers
- `lattice/util.py`: `extract_file_text()` handles `.pptx` via `python-pptx`, `.xlsx` via `openpyxl`, `.xls` via `xlrd`, `.docx` heading map
- `lattice/ingest.py`: `_SYSTEM` extended with "People facts" rule; `_PDF_ADDENDUM`, `_PPTX_ADDENDUM`, `_XLSX_ADDENDUM` added; `_source_addendum()` dispatches to all three
- Optional deps: `pdf = ["pypdf"]`, `office = ["python-pptx", "openpyxl", "xlrd"]`, `docx = ["python-docx"]`

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

### Epic 11 — Semantic dedup (Phase 2B, parallel track)

#### STORY-017 · Near-duplicate detection at ingest

**As a** user capturing the same fact from multiple surfaces (real-time MCP call, session-end summary, `lc` CLI, browser extension),
**I want** Lattice to detect near-duplicate atoms across all sources,
**so that** my atom store doesn't accumulate semantically identical facts with slightly different wording.

**Background:** Content-hash dedup (exact) and subject-based supersession (same subject, LLM decides) cover common cases. The gap is same-meaning atoms with different wording and different subjects — e.g. "user dislikes mountains" (real-time) and "Amulya expressed strong preference against mountains" (session summary). Subject supersession doesn't fire because subjects differ. This story closes that gap.

**Acceptance criteria:**
- At ingest time, new atoms are embedded and compared against existing atom embeddings
- If cosine similarity exceeds `LATTICE_DEDUP_THRESHOLD` (default `0.92`), the existing atom is a supersession candidate — existing supersession LLM call decides which wins
- If `fastembed` is not installed, ingest proceeds unchanged (no-op graceful degradation)
- Atoms from different sources that carry the same semantic content → one survives
- No change to atom schema, no change to query path

**Technical notes:**
- `lattice/embed.py` already exists with fastembed guard — extend it with `nearest_neighbors(atom, db, threshold)` returning candidate atom_ids
- Call from `ingest.py` after extraction, before writing, alongside existing subject supersession check
- `LATTICE_DEDUP_THRESHOLD` env var; default `0.92` (tight — avoids false positives)
- Optional dep: `[project.optional-dependencies] semantic = ["fastembed"]` (already exists)
- **Independent** — does not depend on any other Phase 2B story

---

### Epic 12 — Channel consistency (fill recall + session gaps across all channels)

> **Principle:** every distribution channel should support both capture AND recall where feasible.
> Add these stories before building new channels.

#### STORY-023 ✅ · `lc status` — memory count from terminal

**As a** developer in the terminal,
**I want** to run `lc status` and see how many memories are stored,
**so that** I can confirm Lattice is working without opening a browser.

**Acceptance criteria:**
- `lc status` prints `{count} memories stored` and exits 0
- Daemon not running → prints count directly from `LatticeDB` (read-only, no daemon needed)
- `lc` with no args still prints usage and exits 1 (unchanged)

**Technical notes:**
- Add `status` subcommand check to `lattice/cli.py` — if `sys.argv[1] == "status"`, read DB directly
- `LatticeDB(Config.from_env().lattice_dir)` → count non-superseded atoms
- ~10 lines
- **Independent**

---

#### STORY-024 ✅ · Telegram `/ask` — recall from phone

**As a** user on my phone,
**I want** to send `/ask what do I prefer for coffee?` to the Lattice bot,
**so that** I can recall memories without opening a browser or Claude.

**Acceptance criteria:**
- `/ask <question>` returns a synthesized prose answer in Telegram
- If no atoms found → `Nothing stored about that yet.`
- Daemon not running → `Lattice is offline right now. Try again in a moment.`
- Long answers (>4096 chars) split into multiple Telegram messages
- **Depends on:** STORY-018 ✅

**Technical notes:**
- Add `CommandHandler("ask", _handle_ask)` to bot
- Call `POST /api/answer` on the local web server (blocking JSON response) — bot has no LLM env vars, daemon does
- Strip `[label][src:id]` citation markers from prose; collect unique labels and append as `Sources:\n· label` footer
- ~25 lines in `lattice/telegram_bot.py`

---

#### STORY-025 ✅ · Telegram `/save` — capture conversation thread

**As a** user who has been asking questions and sending thoughts via Telegram,
**I want** to run `/save` at the end of a session,
**so that** the Q&A thread is captured as memory automatically.

**Acceptance criteria:**
- `/save` ingests the last N messages from the current bot session (questions asked + answers received) as a conversation chunk
- Replies: `Saved. {n} new things added from this session.`
- No messages in session → `Nothing to save from this session.`
- **Depends on:** STORY-024 (needs `/ask` to have a meaningful session to save)

**Technical notes:**
- Bot maintains an in-memory per-chat message buffer (list of `{role, text}` dicts) — cleared on `/save`
- Format as `user: ...\nassistant: ...` and call `DaemonClient().ingest()` — pipeline auto-attributes per turn
- Buffer lives in `context.chat_data` (python-telegram-bot persistence)
- ~30 lines

---

#### STORY-026 ✅ · Web UI session-end capture

**As a** user who has asked several questions in the web UI,
**I want** to click "Save this session" at the end,
**so that** the questions I asked and answers I received are captured as memory.

**Acceptance criteria:**
- "Save session" button appears in the web UI after at least one Q&A exchange
- Clicking it POSTs the session Q&A pairs to `POST /api/ingest` as a conversation chunk
- Success: button changes to `✓ Saved` briefly, then resets
- Empty session → button is disabled
- **Depends on:** STORY-003 ✅

**Technical notes:**
- Client-side: collect `{question, answer}` pairs in JS as queries are made
- Format as `user: {question}\nassistant: {answer}` joined by `\n\n`, POST to `/api/ingest`
- Button in `lattice/web/static/index.html`
- ~20 lines JS + ~5 lines HTML

#### STORY-027 ✅ · Telegram recall feedback

**As a** user who receives an answer via Telegram `/ask`,
**I want** to give a quick thumbs up or down on the answer,
**so that** Lattice can track recall quality across all channels, not just the web UI.

**Acceptance criteria:**
- After every recall answer, bot sends a follow-up: `"Was this helpful? Reply 👍 or 👎"`
- 👍 → writes `{rating: "up"}` to `feedback.jsonl` via `POST /api/feedback`; replies `Thanks!`
- 👎 → asks `"What went wrong? Reply: wrong sources / inaccurate / incomplete / off topic"`; on reason reply → writes `{rating: "down", reason: <reason>}`; replies `Got it, thanks.`
- Any other reply while feedback pending → drops pending feedback, processes new message normally
- Feedback silently skipped if `/api/feedback` is unreachable
- **Depends on:** STORY-024 ✅

**Technical notes:**
- Store `pending_feedback: {question, answer}` in `context.chat_data` after each recall reply
- Add feedback prompt detection in `_handle_message` before intent classification — check `pending_feedback` first
- Thumbs detection: `👍` / `👎` / `yes` / `no` / `good` / `bad`
- Reason detection: partial match against `["wrong sources", "inaccurate", "incomplete", "off topic"]`
- POST to `http://127.0.0.1:{LATTICE_WEB_PORT}/api/feedback` via `urllib.request`
- ~40 lines in `lattice/telegram_bot.py`

---

### Epic 12 — Recall UX polish (Phase 2B, parallel track)

#### STORY-029 ✅ · Memory Sparks — empty state query direction

**As a** user opening the web UI with nothing to ask,
**I want** the interface to surface what I could ask and show me how to phrase it,
**so that** I never stare at a blank input unsure where to start.

**Acceptance criteria:**

**Ghost queries in input placeholder:**
- Placeholder text cycles through 3–4 example queries built from recent atom subjects (e.g. `"What did I decide about postgres?"`, `"What do I prefer when traveling?"`)
- Generated client-side from `GET /api/atoms/recent` on page load — no new endpoint
- Cycles every 3s with a CSS crossfade transition
- Clicking anywhere on placeholder text fills the input with that query
- Falls back to static `"Ask your memory anything…"` when no atoms stored yet

**Memory Spark cards in empty state:**
- 3 cards shown below the cube logo when no conversation has started
- Each derived from a recent atom: kind icon (♥ ◆ ★ ◎) + time label ("from yesterday", "3 days ago") + one auto-generated question
- Question generation: `"What did I decide about {subject}?"` for `kind=decision`; `"What do I prefer about {subject}?"` for `kind=preference`; `"Tell me about {subject}"` for all others
- Generated from first 3 subjects in `/api/atoms/recent` response
- One-tap on card → fills input and submits immediately
- Cards pulse softly on hover (CSS `scale(1.02)` transition, 150ms)
- Hidden once user starts typing or a conversation is active

**True empty state (no atoms yet):**
- Replace cards with: *"Nothing here yet. Send me a thought on Telegram, drop a note in your inbox, or just type something — then come back and ask."*
- No cards, no ghost queries

**Cross-channel:**
- **Telegram `/start`**: include 3 suggested questions from recent atom subjects:
  `"You could ask:\n· What did I decide about {subject}?\n· What do I prefer for {subject}?\nOr just send me a thought."`
  Falls back to: `"Nothing stored yet. Send me anything worth keeping."` when empty.
- **`lc status`**: append recent topics: `"12 memories · Topics: hiking, coffee, travel"`
- **MCP**: N/A — Claude understands context natively

**Technical notes:**
- All logic in `lattice/web/static/app.js` — no backend changes
- Card HTML injected into existing `#empty-state` div
- Ghost query: replace static `placeholder` attribute with JS interval cycling `input.setAttribute("placeholder", ...)`
- **Depends on:** nothing (uses existing `/api/atoms/recent`)

---

#### STORY-030 ✅ · Memory Depth — streak reframe + grace day + milestone moments

**As a** user building a recall habit,
**I want** the streak indicator to feel meaningful, forgiving, and motivating,
**so that** one missed day doesn't kill my momentum and I understand what I'm building toward.

**Acceptance criteria:**

**Streak label reframe:**
- Replace `"Day N"` with `"N day deep"` (singular) / `"N days deep"` (plural)
- Tooltip on hover: `"Consecutive days you've recalled something. Goal: 30 days deep."`
- Day 30+: label becomes `"30 days deep 🎯"`
- Day 0 (no queries yet today): `"Ask something to start your streak"`

**Forgiving streak — grace day:**
- User gets one grace day per 7-day window before streak resets
- On the grace day: label shows `"N days deep · rest day"` — streak count does not decrease
- Grace day is consumed silently; on the next day if they query, streak continues from N
- If two consecutive days are missed → streak resets to 0, grace day refills
- `GET /api/usage/summary` returns `grace_day_active: bool` alongside `streak_count`
- Grace day tracked in `usage.jsonl` as a `{type: "grace_day_used", ts: ...}` entry

**Milestone moment cards:**
- One-time animated card in the chat area (not blocking input) on first query of each milestone day
- Warm background (`#f5ede3` light / `#2a2a2a` dark), subtle fade-in, single dismiss ✕

| Day | Message |
|-----|---------|
| 1 | *"First recall. Good start."* |
| 7 | *"A week in. Lattice is starting to know you."* |
| 14 | *"Two weeks of asking and remembering. You have [N] things stored — this is becoming real."* |
| 30 | *"30 days. You've built something here. Try going a week without it — you'll know it's working."* |

- `localStorage` key per milestone (`lattice_milestone_shown_7`, etc.) — shown once, never again
- `[N]` in day-14 message from `GET /api/usage/summary` atom count

**Cube animation on milestone:**
- 3D rotating cube briefly emits CSS particle burst (4–6 `::after` elements, `scale` + `opacity` keyframe, 800ms) on milestone days
- Triggered once per session via `localStorage` check

**Cross-channel:**
- **Telegram `/status`**: `"12 memories · 3 days deep"` or `"12 memories · 3 days deep · rest day"` on grace day
- **Telegram milestones**: on first interaction of a milestone day, prepend milestone message before normal reply
- **`lc status`**: `"12 memories stored · 3 days deep"`
- **MCP `lattice_status`**: add `"streak"` and `"grace_day_active"` to returned JSON

**Technical notes:**
- Frontend: `app.js` + `style.css`; backend: extend `_record_usage()` + `GET /api/usage/summary` in `app.py`
- Grace day logic: in `usage/summary` endpoint, check if yesterday has 0 queries and grace not yet used this week
- Streak label: update element currently rendering `"Day N"` in header
- **Depends on:** STORY-013 ✅

---

#### STORY-031 ✅ · Weekly memory report + topic depth cards

**As a** user who has been using Lattice for a week or more,
**I want** a personal weekly summary and topic depth recognition,
**so that** I can see my memory growing in concrete terms and feel the value of the habit.

**Acceptance criteria:**

**Weekly memory report:**
- Every Monday on first page load, a report card appears inline in chat area:

```
This week
23 things saved · 8 questions asked · 4 topics
Most on your mind: Lattice architecture
Something new: Travel planning
14 days deep.                  [Dismiss]
```

- Data sourced entirely from `usage.jsonl` + `LATTICE_DIR` atom scan — no new endpoint needed
- `localStorage` key `lattice_weekly_report_{ISO_week}` — shown once per week
- Only shown if user has been active for ≥7 days (no report on week 1 day 1)
- "New this week" = subjects that appear in atoms ingested in the last 7 days but not before

**Topic depth cards:**
- When a subject accumulates 5+ atoms, a one-time card appears after the next recall:

> *"You've saved 6 things about [Lattice architecture]. That's a topic you know well."*

- Subject pulled from atom `subject` field; count from `subjects.json` (already maintained by db)
- `localStorage` key `lattice_topic_depth_{normalized_subject}` — shown once per subject, never again
- Thresholds: 5 atoms (`"That's a topic you know well."`), 10 atoms (`"You've thought about this a lot."`), 20 atoms (`"This is one of the things you know best."`)
- Shown after synthesis completes — appended below the answer, not blocking

**Technical notes:**
**Cross-channel:**
- **Telegram weekly**: every Monday, first message of day gets the weekly summary prepended:
  `"This week — 23 things saved, 8 questions asked, 4 topics. Most on your mind: Lattice architecture."`
- **Telegram topic depth**: after a capture that crosses the 5-atom threshold for a subject:
  `"You've saved 5 things about [hiking]. That's a topic you know well."`
- **`lc` topic depth**: same message appended to capture confirmation when threshold crossed
- **Web UI**: inline cards as spec'd above

**Technical notes:**
- New `GET /api/usage/weekly` endpoint in `app.py` — returns: `atoms_this_week`, `recalls_this_week`, `topics_this_week`, `new_topics`, `streak_count`; reads `usage.jsonl` + scans atom `ingested_at` fields
- Topic depth check: after every synthesis response in `app.js`, call `GET /api/atoms/recent?subject={subject}` and count — if ≥ threshold and localStorage key absent, show card
- Weekly report: on page load, call `/api/usage/weekly`, check localStorage week key
- **Depends on:** STORY-013 ✅, STORY-029 (shares card component pattern)

---

#### STORY-032 ✅ · Rediscovery highlight — surfacing old atoms in recall

**As a** user who gets a recall answer citing an atom stored weeks ago,
**I want** to see that it was remembered from far back,
**so that** I feel the "oh wow" moment of Lattice working and am motivated to keep the habit.

**Acceptance criteria:**
- When a synthesis response cites an atom with `ingested_at` ≥ 30 days ago, that citation renders with a subtle highlight and age label:
  - `[1] · 34 days ago` — the `[1]` superscript gets a warm amber glow (`#c97d3a`) for 2s then fades
  - In the sources section: `· from 34 days ago` — quiet, not alarming
- Threshold: 30 days. Atoms < 30 days show no highlight
- Multiple old atoms in one answer: all highlighted
- Highlight is purely cosmetic — no change to selection or synthesis logic

**Cross-channel:**
- **Telegram `/ask`**: after sources footer, if any cited atom is ≥30 days old, append:
  `"One of these memories is from 34 days ago."` — quiet, no exclamation, just a fact
- **Web UI**: amber glow + age label as spec'd above
- **MCP `lattice_answer`**: omit — adding age annotation to Claude's context is noise

**Technical notes:**
- `GET /api/atoms/recent` already returns `ingested_at` — pass it through the SSE `atoms` event to the frontend
- In `app.js` citation rendering: after `citations_applied` SSE event, check each cited atom's `ingested_at`; if `Date.now() - ingested_at > 30 * 86400 * 1000` → add `rediscovery` CSS class + age label
- Age label: `Math.floor(days)` + `" days ago"` — no rounding needed
- CSS: `.rediscovery { animation: amber-pulse 2s ease-out forwards; }`
- **Depends on:** nothing (uses existing SSE atom payload)

---

### Epic 13 — Privacy + trust (Phase 2B, parallel track)

> **Why now:** the technical pitch explicitly commits to this — "Lattice takes responsibility for ensuring no PII reaches the API." That promise needs an implementation. Also directly addresses the privacy tailwind from the SWOT — local-first is only a durable moat if the cloud fallback path is equally trustworthy.

#### STORY-033 · PII round-trip redaction for cloud providers ✅

**As a** user whose device can't run a local model and falls back to OpenRouter,
**I want** Lattice to redact PII before text leaves my machine and restore it after,
**so that** sensitive personal facts never reach a third-party API, and atom content on disk always has real names.

**Background:** Simple scrubbing (replace with `[NAME]`) is destructive — the name is lost forever from the atom. Round-trip redaction maps entities to numbered tags (`PER_0`, `ORG_0`), sends the tagged text to the cloud LLM, receives back tagged output, then restores real values before writing to disk. Atoms on disk always contain real names; names never leave the machine.

**Acceptance criteria:**
- When `LLM_PROVIDER != ollama` and `LATTICE_NER_MODEL` is set: full round-trip NER redaction (persons, orgs, emails, phones)
- When `LLM_PROVIDER != ollama` and `LATTICE_NER_MODEL` not set: regex-only (emails, phones, URLs — no name NER)
- When `LLM_PROVIDER=ollama`: skip entirely — data never leaves machine
- Entity types redacted: PER → `PER_0/PER_1/…`, ORG → `ORG_0/ORG_1/…`, EMAIL → `EMAIL_0/…`, PHONE → `PHONE_0/…`. **DATE is never redacted** — breaks temporal reasoning.
- Original atoms on disk always contain real values — redaction is in-memory only
- LLM instructed to preserve entity tags exactly as written
- `LATTICE_PII_SCRUB=true` default when not ollama; `false` to disable explicitly
- Web UI: subtle `🔒 PII protected` label in synthesis header when active
- Applies to both ingest (segment text → LLM extraction) and synthesis (atom content → LLM synthesis)

**Technical notes:**
- New `lattice/privacy.py` — `EntityRedactor` class:
  - `.redact(text, provider) → (redacted_text, entity_map)` — no-op if ollama or scrub disabled
  - `.restore(text, entity_map) → text` — replaces `PER_0` etc. back with real values
- `LATTICE_NER_MODEL` env var (e.g. `qwen3:0.6b`) — if set, uses that Ollama model for NER via `lattice/llm.py`; if absent, regex-only
- NER call batches all segments from one document in a single LLM call → consistent entity map across segments, one inference call per document
- `ingest.py`: redact segment text before `_extract_atoms()`, restore entity tags in returned atom `content` and `subject` fields
- `synthesis.py`: redact atom content before building prompt, restore entity tags in prose response before yielding to caller
- `LATTICE_PII_SCRUB` and `LATTICE_NER_MODEL` parsed in `config.py`
- **Accuracy tradeoff:** spaCy en_core_web_sm (~85% F1 on Western names) rejected — too low recall for diverse names (South Asian, East Asian, etc.) where a miss means real names reach the API. Ollama NER has better generalization but requires a local model to be available. Regex-only is the honest fallback when no local model is present.
- **NER reuse:** `EntityRedactor` is the shared foundation for M16 (named entity graph nodes). M16 depends on M7 (topic hubs) to avoid p21-style over-connection.
- **Independent** — no other story dependencies

---

### Epic 14 — Portability + sharing (Phase 2B, parallel track)

> **Why now:** the non-technical pitch closes with "share your entire knowledge graph with someone you trust — as easily as sharing a file." No mechanism exists for this today. A simple export/import story delivers on the promise without requiring Phase 3 sync.

#### STORY-034 · `lattice export` — portable atom archive

**As a** user who wants to share my knowledge graph with a trusted person or back it up,
**I want** to run `lattice export` and get a single portable file,
**so that** my second brain is as easy to share as an email attachment — no vendor, no platform, no permission needed.

**Acceptance criteria:**
- `lattice export` creates a timestamped `.zip` of all non-superseded atom `.md` files: `lattice-export-{YYYY-MM-DD}.zip`
- Written to current working directory; prints path on completion
- `lattice export --all` includes superseded atoms (full history)
- `lattice export --subject <subject>` exports only atoms matching that subject (partial match)
- `lattice import <file.zip>` ingests exported atoms into a new or existing Lattice instance — runs normal ingest pipeline (dedup + supersession apply)
- Import prints: `Imported N atoms. M already existed, skipped.`
- Zero data transformation — atoms stay as `.md` + YAML frontmatter; recipient Lattice reads them natively

**Technical notes:**
- New `lattice/export.py` — `export(path, include_superseded, subject_filter)` using stdlib `zipfile`
- New `lattice/import_.py` — `import_archive(path)` unzips to a temp dir, calls `LatticeDB.write()` per atom
- New entry points: `lattice-export` and `lattice-import` in `pyproject.toml`
- No new deps — stdlib only
- **Independent** — no other story dependencies

---

## Dependency map

```
Phase 2A (ship first — two stories)
├── STORY-016 (_db staleness fix) — ship before STORY-002
└── STORY-002 (lattice_capture MCP tool)

Phase 2B ordering
├── STORY-003 (POST /api/ingest)          ← build before VS Code and Telegram
│   ├── STORY-005/006 (VS Code)           ← third (no CORS needed, TypeScript context-switch)
│   ├── STORY-018 (Telegram bot)          ← third (no CORS needed, polling)
│   │   └── STORY-019 (Power Nap plist)  ← ships alongside STORY-018
│   ├── STORY-004 (CORS)
│   │   ├── STORY-008 (browser ext)       ← fifth
│   │   └── STORY-009 (Apple Shortcuts)   ← sixth, iPhone/macOS only
│   ├── STORY-020 (menu bar app)          ← seventh, macOS only
│   ├── STORY-022 (Cloudflare Tunnel)     ← eighth; unlocks cloud AI mobile apps
│   └── STORY-001 (lattice setup)         ← fourth
│
├── STORY-007 (lc CLI) — independent      ← second
├── STORY-010/011 (Homebrew + wizard) — independent, path-C gate
├── STORY-012 (Feedback analysis) — independent, parallel
├── STORY-013 (Usage telemetry) — independent, parallel
├── STORY-029 (Memory Sparks empty state) — independent, parallel; no backend deps
├── STORY-030 (Memory Depth + grace day + milestones) — depends on STORY-013 ✅
├── STORY-031 (Weekly report + topic depth) — depends on STORY-013 ✅; new /api/usage/weekly endpoint
├── STORY-032 (Rediscovery highlight) — independent; uses existing SSE atom payload
├── STORY-014 ✅ (PDF parser + all file types + all channels) — independent, parallel
├── STORY-015 (Reminders) — independent, parallel
├── STORY-017 (Semantic dedup) — independent, parallel; requires fastembed optional dep
├── STORY-033 (PII scrubbing) — independent, parallel; activates only when LLM_PROVIDER != ollama
└── STORY-034 (lattice export/import) — independent, parallel; stdlib only

Phase 3 (deferred)
└── STORY-021 (Telegram voice notes)      ← after mobile habit validated
```

---

#### STORY-028 ✅ · Synthesis "no answer" post-processing

**As a** user querying Lattice about something not in memory,
**I want** a clean short response instead of a verbose explanation of what IS stored,
**so that** unrelated memories are not revealed and the UX is not jarring.

**Problem:** BM25 retrieves loosely related atoms (e.g. "hiking", "mountains" for a "skiing" query). Synthesis is then passed these atoms and writes a paragraph explaining why they don't answer the question — revealing unrelated stored facts and producing noisy output.

**Acceptance criteria:**
- When synthesis output contains "I can't determine", "not mentioned", "no information about", "atoms do not", "cannot determine" etc. → replace entire answer with `"Nothing stored about that yet."`
- Clean one-sentence response, no unrelated facts revealed
- Applies to web UI, Telegram `/ask`, and MCP `lattice_answer`
- Existing tests for relevant answers unaffected

**Technical notes:**
- Add `_is_no_answer(text) -> bool` in `lattice/synthesis.py` using a regex of known "I don't know" phrases
- Call after `replace_citations()` in both `synthesize()` and `stream_synthesis()`
- For streaming: detect in the `citations_applied` event before yielding
- Phrase list needs tuning — start tight, expand as false positives appear
- **Independent** — no dependencies

---

## Dropped from scope

| Story | Reason |
|-------|--------|
| Per-turn progressive capture | Too noisy and expensive — 2 LLM calls/atom on every message, captures exploratory/tentative statements that shouldn't be memory. Covered by: signal-based real-time capture via CLAUDE.md instruction (fires on facts/prefs/decisions) + session-end `lattice_capture`. |
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
- Bundled installer / native mobile app
- STORY-021: Telegram voice notes — deferred until 2 weeks of Telegram text capture confirmed as daily habit (STORY-018 must ship and be used first)
- Cloudflare Queue relay (ordered delivery when laptop off for days) — deferred until laptop-off gap confirmed in daily use; STORY-022 Tunnel covers the common case
