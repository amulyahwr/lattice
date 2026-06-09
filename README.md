# Lattice

**Lattice is your second brain — local, structured, private, and omnipresent.**

Your personal memory OS — local, private, always running. Everything you tell it becomes a typed, timestamped fact stored as plain markdown on your own machine. Ask it anything; it answers in prose with citations.

---

## The pitch

### For everyone

**The problem**

Your life generates more than you can hold. Decisions, reminders, half-formed ideas, things you learned last Tuesday — most of it disappears. What if you could offload all of it to a [second brain](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) that breaks every thought into a small, typed, timestamped _memory_, and actually organizes it so you can find it again?

**The gap**

The right pieces exist — LLM agents that ingest, connect, and synthesize information. But every tool built on them stores your memories as flat blobs of text, with no structure and no connections. Worse, they live on someone else's server. You can't truly delete a memory. You can't see what's stored. Your second brain isn't yours.

**Lattice**

Memories become powerful when they connect — a decision linked to the facts that drove it, a preference linked to the experience that shaped it. Connect enough memories and you get a _lattice_: a structured graph of everything you know, living on your own device. Send a thought from your phone while commuting, find it waiting on your laptop at work, ask for it from your car on the way home — no vendor in the middle, no lock-in, no permission needed. Any device. Any OS. Any platform. Your second brain. Your memories. Your rules.

---

### For engineers

_This is what "local, structured, private" actually means in code. What you call a memory, Lattice calls an atom._

**Ingest**

Every piece of text — a Telegram message, a file dropped in an inbox folder, a Claude conversation, a terminal one-liner — enters a pipeline that segments it by source type (chat, markdown, code), then runs an LLM extraction pass to decompose it into _atoms_: typed, timestamped Pydantic models with fields like `kind`, `subject`, `content`, `valid_from`, `valid_until`, `observed_at`, and full provenance (`source_id`, `session_id`, `segment_id`). Each atom is stored as a plain `.md` file with YAML frontmatter — human-readable, git-trackable, hand-editable.

**Graph**

After every write, a `LatticeGraph` (networkx `MultiDiGraph`) upserts nodes and edges into committed sidecars on disk. Node types: `atom`, `source`, `segment`, `subject`. Edge types: `supersedes`, `same_subject_as`, `same_hash`, `atom_has_subject`, `source_contains_segment`. Superseded atoms stay on disk with bidirectional links — history is never deleted, only layered. The graph is the connective tissue that makes atoms more than a flat list.

**Selection**

Query path is deliberately LLM-free. BM25 seeds the top candidates → zero-score seeds filtered → source-diversity probe → graph BFS expands the evidence pack along supersession, subject, and provenance edges → optional BFS rescore. The result is a ranked list of atom dicts with full provenance, ready for synthesis. Fast, deterministic, auditable.

**Synthesis**

A streaming LLM call takes the atom pack and generates a prose answer with numbered source citations. Tool calls handle date arithmetic and aggregation. The answer streams token-by-token to the web UI via SSE. The goal is fully on-device inference via Ollama — such as [Gemma 4](https://ollama.com/library/gemma4) — your thoughts never leave your machine. For devices that can't run a capable local model, OpenRouter is the supported fallback; Lattice implements round-trip PII redaction so sensitive names never reach the API. `EntityRedactor` (`lattice/privacy.py`) maps persons, orgs, emails, and phones to numbered tags (`PER_0`, `ORG_0`, …) before any cloud LLM call and restores real values afterward — atoms on disk always contain real names. Optional local NER via `LATTICE_NER_MODEL`; regex-only fallback when unset. The web UI shows a `🔒 PII protected` badge when active.

**Architecture**

A persistent daemon owns all writes — MCP server, web UI, Telegram bot, `lc` CLI, and browser extension are all read-only clients that delegate over a Unix socket. The web UI runs at `localhost:7337`. Capture channels today: MCP tools (Claude Code), web UI, Telegram bot, `lc` terminal command, inbox file drop, Chrome browser extension. All channels write to the same atom store; all recall channels record to `usage.jsonl` for streak tracking and feedback collection.

---

## How Lattice compares

> ✅ Yes &nbsp;&nbsp; ⚠️ Partial / conditions apply &nbsp;&nbsp; ❌ No

|                             | **Lattice**          | **GBrain**                            | **ChatGPT Memory**           | **Claude Projects**          | **Mem0**                     |
| --------------------------- | -------------------- | ------------------------------------- | ---------------------------- | ---------------------------- | ---------------------------- |
| **Stays on my device?**     | ✅ Always            | ⚠️ Dev yes; production needs Postgres | ❌ OpenAI servers            | ❌ Anthropic servers         | ❌ Cloud; local needs Docker |
| **I control deletion?**     | ✅ Delete any file   | ✅                                    | ⚠️ Via UI; 24hr delay        | ⚠️ Via UI                    | ⚠️ Via dashboard             |
| **Works with any AI?**      | ✅ Any MCP client    | ⚠️ MCP yes; built for OpenClaw        | ❌ GPT-only                  | ❌ Claude-only               | ⚠️ API or MCP                |
| **Memories link together?** | ✅ Typed graph       | ✅ Entity graph                       | ❌ Flat notes                | ❌ Flat injection            | ⚠️ Vector + graph            |
| **I can read my files?**    | ✅ Plain `.md` files | ✅ Plain `.md` files                  | ⚠️ Exportable; their servers | ⚠️ Exportable; their servers | ❌                           |
| **Runs without internet?**  | ✅ Ollama-first      | ❌                                    | ❌                           | ❌                           | ⚠️ Needs Docker              |
| **History never deleted?**  | ✅ Always            | ⚠️ Timeline kept; summary rewritten   | ❌                           | ❌                           | ⚠️ Mostly                    |
| **Free & open source?**     | ✅ MIT               | ✅ MIT                                | ❌                           | ❌                           | ⚠️ Partial                   |

**The one thing no competitor matches:** Lattice is the only option where memories are plain files on your machine, history is never deleted, on-device inference is the default, and zero infrastructure is required — no database, no Docker, no account.

---

## Setup

### 1. Install

```bash
git clone https://github.com/amulyahwr/lattice
cd lattice
uv sync --group pdf                        # base + PDF upload (web UI, Telegram, lc)
uv sync --group pdf --group semantic       # + dense retrieval (LATTICE_DENSE_SEEDS=1)
```

Install groups in a single `uv sync` call — running them separately can displace each other. Add `--group telegram` if using the Telegram bot.

### 2. Configure

Copy and fill in your env vars (or export them in your shell profile):

```bash
export LATTICE_DIR=~/.lattice
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_MODEL=openai/gpt-4o-mini
export LLM_API_KEY=sk-or-...       # from openrouter.ai/keys

# PII protection (on by default for cloud providers)
export LATTICE_PII_SCRUB=true      # set false to disable
export LATTICE_NER_MODEL=          # optional: local Ollama model for NER (e.g. gemma4:4b)

# Dense retrieval (optional — fixes vocab-mismatch misses like "gym" ↔ "workout")
# requires: uv sync --group pdf --group semantic  (install both groups together)
export LATTICE_DENSE_SEEDS=1       # enable dense seed augmentation
export LATTICE_DENSE_TOP_K=10      # top-K dense hits merged with BM25 seeds
```

Using Ollama instead? Drop `LLM_BASE_URL` and `LLM_API_KEY`, set `LLM_PROVIDER=ollama` and `LLM_MODEL=gemma4:4b`.

### 3. Wire into Claude Code

```bash
claude mcp add lattice -- uv run --directory /path/to/lattice lattice
```

### 4. Add the memory block to your CLAUDE.md

Copy this entire block into your `CLAUDE.md` (the one Claude Code reads for your project or globally at `~/.claude/CLAUDE.md`):

```
### Memory: Lattice is the sole memory system

**Do not write user facts, preferences, or decisions to Claude's internal
auto-memory system.** Do not save anything to ~/.claude/projects/.../memory/.
Lattice is the only memory store.

When the user says any of: "save", "done", "goodbye", "wrap up", "end session",
"save session" — summarize decisions made, things built, and conclusions reached,
then call `lattice_capture` with that summary. Always set
`metadata.source_id="claude-code"` and `metadata.observed_at=<current ISO timestamp>`.

When the user shares a preference, decision, fact, or anything worth remembering,
call `lattice_ingest` immediately:
- Single fact from the user → set `metadata.source="user"`,
  `metadata.source_id="claude-code"`, `metadata.observed_at=<current ISO timestamp>`.
- Conversation chunk (multiple turns) → format as `"user: ...\nassistant: ..."`
  and omit `metadata.source` — the pipeline attributes per-turn automatically.

When answering a recall question ("what did I decide about X", "what do I prefer",
"remind me of Y"), call `lattice_select` first and ground the answer in returned atoms.
```

### 5. Allow Lattice tools without permission prompts

By default Claude Code asks for approval on every MCP tool call. Add to `.claude/settings.json` to allow Lattice tools automatically:

```json
{
  "autoMemoryEnabled": false,
  "allowedTools": [
    "mcp__lattice__lattice_ingest",
    "mcp__lattice__lattice_capture",
    "mcp__lattice__lattice_select",
    "mcp__lattice__lattice_answer",
    "mcp__lattice__lattice_status"
  ]
}
```

### 6. Start the daemon

The daemon watches your inbox folder, ingests new files automatically, and serves the web UI.

```bash
lattice-daemon
```

**Auto-start on login (macOS):** fill in your env vars in `extras/dev.lattice.daemon.plist`, then:

```bash
cp extras/dev.lattice.daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

### 7. Set up Telegram capture (optional)

Capture thoughts from your phone via a Telegram bot — works even when your laptop is offline (messages queue and process when daemon restarts).

**a. Create a bot** — message [@BotFather](https://t.me/botfather) on Telegram, run `/newbot`, copy the token.

**b. Get your Telegram user ID** — message [@userinfobot](https://t.me/userinfobot), it replies with your numeric ID.

**c. Install the bot dep and plist:**

```bash
uv sync --group pdf --group telegram
cp extras/dev.lattice.telegram.plist ~/Library/LaunchAgents/
```

**d.** Edit `~/Library/LaunchAgents/dev.lattice.telegram.plist` — fill in your bot token, user ID, and paths. Also add `LATTICE_TELEGRAM_TOKEN` to your daemon plist (used to send follow-up confirmations after offline messages are processed).

**e.** Load the bot:

```bash
launchctl load ~/Library/LaunchAgents/dev.lattice.telegram.plist
```

The bot runs independently of the daemon. If the daemon is offline, it replies immediately with a confirmation and queues your message to the inbox for processing on restart.

---

## Use with other AI assistants

### Claude desktop app (macOS / Windows)

Claude desktop supports local MCP servers natively. Add Lattice to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "lattice": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/lattice", "lattice"]
    }
  }
}
```

Restart Claude desktop. Lattice tools appear automatically in every conversation.

### ChatGPT desktop app

ChatGPT desktop supports MCP servers. Add Lattice the same way as Claude desktop via ChatGPT's MCP configuration panel (Settings → Integrations → MCP Servers).

### Claude mobile / ChatGPT mobile / other cloud AI apps

Mobile and web AI apps cannot reach `localhost` directly. Bridge the gap with a Cloudflare Tunnel — a free, persistent HTTPS URL that forwards to your local Lattice:

```bash
# Install once
brew install cloudflare/cloudflare/cloudflared

# Start tunnel (add to launchd plist for auto-start)
cloudflared tunnel --url http://localhost:7337
```

This gives you a stable `https://xxxx.trycloudflare.com` URL. Add it as a remote MCP server in any AI app that supports MCP, or use it as the base URL for ChatGPT Custom GPT Actions (OpenAPI spec at `/openapi.json` — coming in Phase 2B).

**Note:** the tunnel exposes your Lattice to the internet. It is stateless relay-only — your atoms never leave your machine — but protect the URL or add token auth if concerned.

---

## Features

### Recall via web UI

Open `http://localhost:7337`. Ask a natural language question; Lattice streams a prose answer with numbered source citations. Markdown rendering, dark mode, thumbs-up/down feedback. Streak badge ("N days deep") in header tracks consecutive days of recall. "Save session" button captures the Q&A thread as memory at the end of a session.

### Ambient ingest via inbox

Drop any `.txt` or `.md` file into `~/.lattice/inbox/`. The daemon picks it up within seconds, extracts structured facts via LLM, and moves the file to `processed/`. No manual steps.

```bash
echo "Decided to use Postgres over SQLite for the new service" > ~/.lattice/inbox/note.txt
```

### Mobile capture via Telegram

Send any message to your Lattice bot on Telegram — it's saved as memory instantly. Works from any device, any network.

- **Daemon online** → reply within seconds: `Saved. 2 new things added to your memory.`
- **Daemon offline** → message queued to inbox, immediate reply: `Lattice is offline right now. Your message is safe — I'll confirm once it's processed. 📥`
- **Daemon restarts** → inbox drained automatically, follow-up sent: `Back online — processed what you sent earlier. 2 things saved. ✓`

Commands: `/ask <question>` to recall from memory. `/save` to capture the session Q&A thread as memory. `/status` to see your memory count. Bot only responds to your user ID — silently ignores everyone else. After a `/ask` answer, bot prompts 👍/👎 feedback when the answer has low confidence (≤1 source atom).

### Browser extension — right-click any page

Load `extras/browser-extension/` in Chrome (Developer mode → Load unpacked). Select text on any page, then right-click → **Save to Lattice**, or press **⌥+⇧+S** with text selected. The extension sends selected text plus the page URL and title to your local daemon. Captured atoms show a clickable URL source link in the web UI citations panel. The popup shows daemon status and current memory count.

Requires the daemon to be running at `localhost:7337`. When the daemon is offline the extension shows a notification and the save fails — start the daemon first.

### Terminal capture via `lc`

```bash
lc "decided to use Postgres over SQLite for the new service"
# Saved. 1 new thing added to your memory.
```

### MCP tools for AI assistants

Five tools exposed to Claude and any MCP-compatible client:

| Tool              | What it does                                                                                                                                                                                        |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `lattice_ingest`  | Decompose text into memory atoms and store them. Mode A: single fact — set `metadata.source='user'`. Mode B: conversation chunk — format as `user: ...\nassistant: ...` and omit `metadata.source`. |
| `lattice_capture` | Persist a session summary at conversation end. Treats injected atoms as authoritative — do not re-verify with `lattice_select`.                                                                     |
| `lattice_select`  | Return the most relevant atoms for a query (BM25 + graph BFS, 0 LLM calls)                                                                                                                          |
| `lattice_answer`  | Synthesize a prose answer from the atom store                                                                                                                                                       |
| `lattice_status`  | Return the number of memories currently stored                                                                                                                                                      |

### Human-readable atom store

Every fact is a plain `.md` file in `LATTICE_DIR`. Hand-editable, git-trackable. Superseded facts stay on disk with history preserved.

---

## Roadmap

| What                                                                           | Status     |
| ------------------------------------------------------------------------------ | ---------- |
| `lattice_capture` MCP tool — explicit session-end capture                      | ✅ shipped |
| `lc` terminal command — capture + `lc status` memory count                     | ✅ shipped |
| Telegram bot — capture, `/ask` recall, `/save` session, auto-intent detect     | ✅ shipped |
| Web UI "Save session" button — capture Q&A thread as memory                    | ✅ shipped |
| `lattice_status` MCP tool — memory count for Claude Code                       | ✅ shipped |
| Usage telemetry + streak — `usage.jsonl`, streak badge, cross-channel          | ✅ shipped |
| Telegram recall feedback — 👍/👎 on every answer; reason collection            | ✅ shipped |
| Synthesis cleanup — verbose non-answers replaced with warm short phrase        | ✅ shipped |
| Memory Sparks — spark cards, ghost queries, Telegram suggestions, lc topics    | ✅ shipped |
| Memory Depth — "N days deep" streak, grace day, milestone cards, cross-channel | ✅ shipped |
| Rediscovery highlight — amber glow on old citations, Telegram age note         | ✅ shipped |
| Weekly report + topic depth — Monday card, depth notifications cross-channel   | ✅ shipped |
| File ingest — PDF, docx, pptx, xlsx, all channels (inbox, web, lc, Telegram)  | ✅ shipped |
| PII round-trip redaction — `privacy.py` EntityRedactor; restore after LLM     | ✅ shipped |
| Sources UX — content preview + kind + age; Telegram `/sources` command        | ✅ shipped |
| VS Code / Cursor extension — capture + recall from the IDE                     | Phase 2B   |
| Browser extension — right-click selected text → save to Lattice                | ✅ shipped |
| Apple Shortcuts — global hotkey capture (iPhone / macOS)                       | Phase 2B   |
| Menu bar app — macOS status icon + quick capture hotkey                        | Phase 2B   |
| Cloudflare Tunnel — bridge to Claude mobile, ChatGPT mobile, any cloud AI      | Phase 2B   |
| `lattice setup` wizard — one-command onboarding                                | Phase 2B   |
| Prospective reminders (`trigger_at` atoms surfaced by daemon)                  | Phase 2B   |
| Multi-device sync (mDNS discovery + Ed25519 pairing)                           | Phase 3    |
| Native mobile app (iOS / Android, on-device inference)                         | Phase 3    |
| Screenpipe integration — passive ambient capture                               | Phase 3    |
