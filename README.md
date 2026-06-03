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

Claude can now call `lattice_ingest`, `lattice_select`, and `lattice_answer` during your sessions.

**Capture sessions automatically** — add this to your `CLAUDE.md`:

> When the user says any of: "save", "done", "goodbye", "wrap up", "end session", "save session" — summarize decisions made, things built, and conclusions reached, then call `lattice_capture` with that summary. Always set `metadata.source_id="claude-code"` and `metadata.observed_at=<current ISO timestamp>`.

### 4. Tell Claude to use Lattice

Add this to your `CLAUDE.md` so Claude routes memory through Lattice instead of its own context:

> **Do not write user facts, preferences, or decisions to Claude's internal auto-memory system.** Lattice is the only memory store for this project.
>
> When the user shares a preference, decision, fact, or anything worth remembering, call `lattice_ingest` immediately. When answering a recall question ("what did I decide about X", "what do I prefer"), call `lattice_select` first and ground the answer in returned atoms.

### 5. Remove permission prompts

By default Claude Code asks for approval on every MCP tool call. Add to `.claude/settings.json` to allow Lattice tools automatically:

```json
{
  "autoMemoryEnabled": false,
  "allowedTools": [
    "mcp__lattice__lattice_ingest",
    "mcp__lattice__lattice_capture",
    "mcp__lattice__lattice_select",
    "mcp__lattice__lattice_answer"
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

---

## Features

### Recall via web UI

Open `http://localhost:7337`. Ask a natural language question; Lattice streams a prose answer with numbered source citations. Markdown rendering, dark mode, thumbs-up/down feedback.

### Ambient ingest via inbox

Drop any `.txt` or `.md` file into `~/.lattice/inbox/`. The daemon picks it up within seconds, extracts structured facts via LLM, and moves the file to `processed/`. No manual steps.

```bash
echo "Decided to use Postgres over SQLite for the new service" > ~/.lattice/inbox/note.txt
```

### MCP tools for AI assistants

Three tools exposed to Claude and any MCP-compatible client:

| Tool               | What it does                                                               |
| ------------------ | -------------------------------------------------------------------------- |
| `lattice_ingest`   | Decompose text into memory atoms and store them. Mode A: single fact — set `metadata.source='user'`. Mode B: conversation chunk — format as `user: ...\nassistant: ...` and omit `metadata.source`. |
| `lattice_capture`  | Persist a session summary at conversation end. Treats injected atoms as authoritative — do not re-verify with `lattice_select`. |
| `lattice_select`   | Return the most relevant atoms for a query (BM25 + graph BFS, 0 LLM calls) |
| `lattice_answer`   | Synthesize a prose answer from the atom store                              |

### Human-readable atom store

Every fact is a plain `.md` file in `LATTICE_DIR`. Hand-editable, git-trackable. Superseded facts stay on disk with history preserved.

---

## Roadmap

| What                                                            | Status   |
| --------------------------------------------------------------- | -------- |
| `lattice_capture` MCP tool — explicit session-end capture       | ✅ shipped |
| `lc` terminal command — `lc "decided X because Y"`              | Phase 2B |
| VS Code / Cursor extension — capture + recall from the IDE      | Phase 2B |
| Browser extension — right-click selected text → save to Lattice | Phase 2B |
| `lattice setup` wizard — one-command onboarding                 | Phase 2B |
| PDF ingest                                                      | Phase 2B |
| Prospective reminders (`trigger_at` atoms surfaced by daemon)   | Phase 2B |
| Multi-device sync (mDNS discovery + Ed25519 pairing)            | Phase 3  |
| Screenpipe integration — passive ambient capture                | Phase 3  |
| Mobile app                                                      | Phase 4  |
