# lattice

A local-first personal memory OS. Everything you tell it becomes a typed, timestamped **atom** — one fact per file, stored as human-readable markdown in a directory you control. A persistent daemon watches an inbox folder for new content, ingests it automatically, and serves a local web UI for recall.

MCP integration lets any MCP-compatible AI assistant (Claude Code, Cursor, Cline) read from and write to the same atom store.

---

## Quick start

```bash
# Install
uvx lattice

# Start the daemon (inbox watcher + web UI + MCP server)
lattice-daemon

# Open the web UI
open http://localhost:7337

# Drop a file into the inbox — atoms appear within seconds
echo "I prefer dark roast coffee" > ~/.lattice/inbox/note.txt
```

---

## How it works

```
inbox/          ← drop .txt or .md files here
    │
    ▼
lattice-daemon  ← watches inbox, owns all writes to atom store
    │
    ├── lattice/           ← atom store (~/.lattice/*.md)
    ├── web UI             ← http://localhost:7337 (chat + recent atoms)
    └── daemon.sock        ← IPC socket for MCP server writes
            │
            ▼
    MCP server (lattice_ingest / lattice_select / lattice_answer)
```

The daemon is the only writer. The web UI and MCP server read atoms directly from disk (atomic writes make reads safe without locking).

---

## Daemon

```bash
lattice-daemon          # start daemon (inbox watcher + web UI on :7337)
lattice-daemon status   # print running status, atom count, last ingest time
```

The daemon:
- Watches `LATTICE_INBOX` (default `~/.lattice/inbox/`) for `.txt` and `.md` files
- Ingests each file via LLM extraction, moves it to `~/.lattice/processed/`
- Serves the web UI at `http://LATTICE_WEB_HOST:LATTICE_WEB_PORT`
- Exposes a Unix domain socket at `LATTICE_SOCK` for MCP server write requests
- Writes a PID file to `~/.lattice/daemon.pid`

### Auto-start on login (macOS)

A launchd plist is included at `extras/dev.lattice.daemon.plist`. Fill in the env vars before loading:

| Key | What to set |
|---|---|
| `LATTICE_DIR` | Path to your atom store, e.g. `/Users/you/.lattice` |
| `LLM_PROVIDER` | `openai` (for OpenRouter) or `ollama` (local) |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` for OpenRouter; remove for Ollama |
| `LLM_MODEL` | `openai/gpt-4o-mini` for OpenRouter; `qwen3:4b` for Ollama |
| `LLM_API_KEY` | Your OpenRouter key from [openrouter.ai/keys](https://openrouter.ai/keys); remove for Ollama |

Then:

```bash
cp extras/dev.lattice.daemon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/dev.lattice.daemon.plist
```

The daemon will start automatically on every login.

---

## Web UI

Open `http://localhost:7337` in any browser.

- **Chat** — ask a natural language question; answer streams with numbered source citations and markdown rendering
- **Recent atoms** — see what was ingested recently; memory count and kind icons at a glance
- **Feedback** — rate each answer (👍 / 👎 + reason); written to `~/.lattice/feedback.jsonl`
- **Dark mode** — manual toggle (☾/☀); persists across sessions

---

## MCP integration

**Claude Code (recommended):**

```bash
claude mcp add lattice -- uv run --directory /path/to/lattice-mcp lattice
```

**Other MCP clients (Cursor, Cline) — add to `.mcp.json`:**

```json
{
  "mcpServers": {
    "lattice": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/lattice-mcp", "lattice"],
      "env": {
        "LLM_PROVIDER": "openai",
        "LLM_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_MODEL": "openai/gpt-4o-mini",
        "LLM_API_KEY": "sk-or-...",
        "LATTICE_DIR": "/Users/you/.lattice"
      }
    }
  }
}
```

When the daemon is running, `lattice_ingest` drops content to the inbox folder (daemon ingests it asynchronously). When the daemon is not running, `lattice_ingest` falls back to direct write.

---

## Configuration

All configuration is via environment variables.

### LLM

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `ollama` | `ollama` \| `openai` \| `anthropic` |
| `LLM_MODEL` | _(required)_ | Model name — raises error if unset |
| `LLM_API_KEY` | — | API key (not required for Ollama) |
| `LLM_BASE_URL` | — | Override API base URL (e.g. OpenRouter, Anthropic compat) |
| `INGEST_MODEL` | _(LLM_MODEL)_ | Override model for ingest only |
| `SYNTHESIS_MODEL` | _(LLM_MODEL)_ | Override model for synthesis only |

**Provider quick reference:**

| Use case | `LLM_PROVIDER` | `LLM_BASE_URL` | `LLM_MODEL` (suggestions) | `LLM_API_KEY` |
|---|---|---|---|---|
| Local / fully private | `ollama` | _(unset)_ | `qwen3:4b` | _(not needed)_ |
| OpenRouter | `openai` | `https://openrouter.ai/api/v1` | `openai/gpt-4o-mini` | `sk-or-...` from [openrouter.ai/keys](https://openrouter.ai/keys) |

> **`INGEST_MODEL` / `SYNTHESIS_MODEL`:** use a cheap fast model for ingest (`gpt-4o-mini`, `qwen3:4b`) and a stronger one for synthesis (`claude-sonnet-4-6`, `gpt-4o`) to balance cost vs. quality.

### Paths

| Variable | Default | Description |
|---|---|---|
| `LATTICE_DIR` | `~/.lattice` | Root directory for atom store |
| `LATTICE_INBOX` | `~/.lattice/inbox` | Drop files here for ambient ingest |
| `LATTICE_SOCK` | `~/.lattice/daemon.sock` | Unix domain socket for IPC |
| `LATTICE_WEB_HOST` | `127.0.0.1` | Web UI bind address |
| `LATTICE_WEB_PORT` | `7337` | Web UI port |

---

## MCP tools

### `lattice_ingest(source, metadata?)`

Ingests raw text as atoms. When the daemon is running, drops to the inbox (async). Otherwise writes directly.

```
source    — raw text string
metadata  — optional dict (title, url, author, date, …)

→ { atom_ids: [...] }   (direct mode)
→ { queued: true, inbox_file: "..." }      (daemon mode)
```

### `lattice_select(query, as_of?)`

Returns the most relevant atoms for a natural language query.

```
query   — natural language question
as_of   — optional ISO date (YYYY-MM-DD)

→ [ { atom_id, subject, content, kind, source, valid_from, valid_until }, ... ]
```

BM25 seeds candidate atoms; bounded BFS through the graph index expands context via segment, source, subject, supersession, and duplicate edges. 0 LLM calls — results are BFS-expanded and BM25-rescored.

### `lattice_answer(query, atom_ids?, as_of?)`

Synthesizes a prose answer from the atom store.

```
query     — natural language question
atom_ids  — optional list; auto-selects if empty
as_of     — optional ISO date

→ answer string
```

Tool-calling agent loop with `date_diff(date1, date2)` and `sum_numbers(numbers[])` for exact date arithmetic and numeric aggregation.

---

## Atom format

```markdown
---
atom_id: 3f2e1a...
kind: preference
source: user
subject: coffee preference
observed_at: 2025-01-15
valid_from: null
valid_until: null
is_superseded: false
superseded_by: null
supersedes: null
metadata: {}
---
Prefers dark roast coffee.
```

One `.md` file per atom in `LATTICE_DIR`. Human-readable, hand-editable, git-trackable. Superseded atoms stay on disk with `is_superseded: true` — history is preserved, not deleted.

---

## Development

```bash
git clone https://github.com/amulyahwr/lattice
cd lattice
uv sync
uv run pytest

# Run daemon in dev (uses LATTICE_DIR env var)
LATTICE_DIR=/tmp/lattice-dev uv run lattice-daemon

# Iterate on the web UI without GPU — canned SSE responses, no LLM
uv run lattice-mock   # http://localhost:7337
```

Run `scripts/e2e.py` for a full pipeline smoke test (ingest → select → synthesize) against a fixed personal memory corpus — requires `LLM_MODEL` and provider env vars set.
