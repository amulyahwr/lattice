# Lattice

Your personal memory OS — local, private, always running. Everything you tell it becomes a typed, timestamped fact stored as plain markdown on your own machine. Ask it anything; it answers in prose with citations.

Works as an MCP server so Claude and other AI assistants can read and write your memory automatically during conversations.

---

## Setup

### 1. Install

```bash
git clone https://github.com/amulyahwr/lattice
cd lattice
uv sync
```

### 2. Configure

Copy and fill in your env vars (or export them in your shell profile):

```bash
export LATTICE_DIR=~/.lattice
export LLM_PROVIDER=openai
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_MODEL=openai/gpt-4o-mini
export LLM_API_KEY=sk-or-...       # from openrouter.ai/keys
```

Using Ollama instead? Drop `LLM_BASE_URL` and `LLM_API_KEY`, set `LLM_PROVIDER=ollama` and `LLM_MODEL=qwen3:4b`.

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
uv sync --group telegram
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

Open `http://localhost:7337`. Ask a natural language question; Lattice streams a prose answer with numbered source citations. Markdown rendering, dark mode, thumbs-up/down feedback.

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

Commands: `/status` to see your memory count. Bot only responds to your user ID — silently ignores everyone else.

### Terminal capture via `lc`

```bash
lc "decided to use Postgres over SQLite for the new service"
# Saved. 1 new thing added to your memory.
```

### MCP tools for AI assistants

Five tools exposed to Claude and any MCP-compatible client:

| Tool               | What it does                                                               |
| ------------------ | -------------------------------------------------------------------------- |
| `lattice_ingest`   | Decompose text into memory atoms and store them. Mode A: single fact — set `metadata.source='user'`. Mode B: conversation chunk — format as `user: ...\nassistant: ...` and omit `metadata.source`. |
| `lattice_capture`  | Persist a session summary at conversation end. Treats injected atoms as authoritative — do not re-verify with `lattice_select`. |
| `lattice_select`   | Return the most relevant atoms for a query (BM25 + graph BFS, 0 LLM calls) |
| `lattice_answer`   | Synthesize a prose answer from the atom store                              |
| `lattice_status`   | Return the number of memories currently stored                             |

### Human-readable atom store

Every fact is a plain `.md` file in `LATTICE_DIR`. Hand-editable, git-trackable. Superseded facts stay on disk with history preserved.

---

## Roadmap

| What                                                                        | Status    |
| --------------------------------------------------------------------------- | --------- |
| `lattice_capture` MCP tool — explicit session-end capture                   | ✅ shipped |
| `lc` terminal command — capture + `lc status` memory count                  | ✅ shipped |
| Telegram bot — capture, `/ask` recall, `/save` session, auto-intent detect  | ✅ shipped |
| Web UI "Save session" button — capture Q&A thread as memory                 | ✅ shipped |
| `lattice_status` MCP tool — memory count for Claude Code                    | ✅ shipped |
| VS Code / Cursor extension — capture + recall from the IDE                  | Phase 2B  |
| Browser extension — right-click selected text → save to Lattice             | Phase 2B  |
| Apple Shortcuts — global hotkey capture (iPhone / macOS)                    | Phase 2B  |
| Menu bar app — macOS status icon + quick capture hotkey                     | Phase 2B  |
| Cloudflare Tunnel — bridge to Claude mobile, ChatGPT mobile, any cloud AI  | Phase 2B  |
| `lattice setup` wizard — one-command onboarding                             | Phase 2B  |
| PDF ingest                                                                  | Phase 2B  |
| Prospective reminders (`trigger_at` atoms surfaced by daemon)               | Phase 2B  |
| Multi-device sync (mDNS discovery + Ed25519 pairing)                        | Phase 3   |
| Native mobile app (iOS / Android, on-device inference)                      | Phase 3   |
| Screenpipe integration — passive ambient capture                            | Phase 3   |
