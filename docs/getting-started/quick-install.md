# Quick Install

## Prerequisites

- **macOS** (Linux works; Windows untested)
- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — Python package manager (`brew install uv`)
- **[Ollama](https://ollama.com)** (recommended) OR an OpenRouter/Anthropic API key

---

## 1. Clone and install

```bash
git clone https://github.com/amulyahwr/lattice
cd lattice
uv sync --group full
```

`--group full` installs all optional capability groups in one call: dense semantic search, PDF ingestion, Word/Excel/PowerPoint support, and the Telegram bot. Running groups separately can displace each other — always use `--group full` or combine them in a single command.

For docs tooling as well:

```bash
uv sync --group full --group docs
```

---

## 2. Set environment variables

Create a `.env` file or add to your shell profile. Minimum required:

```bash
export LLM_PROVIDER=ollama          # or: openai (for OpenRouter/Anthropic-compat)
export LLM_MODEL=gemma4             # any Ollama model; or openrouter model string
export LATTICE_DIR=~/.lattice       # where atoms and graph are stored
```

### Using Ollama (recommended — fully local)

```bash
# pull a model first
ollama pull gemma4

export LLM_PROVIDER=ollama
export LLM_MODEL=gemma4
export LATTICE_DIR=~/.lattice
```

### Using OpenRouter (cloud fallback)

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=google/gemini-2.0-flash-001
export LLM_BASE_URL=https://openrouter.ai/api/v1
export LLM_API_KEY=sk-or-...
export LATTICE_DIR=~/.lattice
```

### Using Anthropic directly

```bash
export LLM_PROVIDER=openai
export LLM_MODEL=claude-sonnet-4-6
export LLM_BASE_URL=https://api.anthropic.com/v1
export LLM_API_KEY=sk-ant-...
export LATTICE_DIR=~/.lattice
```

---

## 3. Start the daemon

```bash
uv run lattice-daemon
```

The daemon starts and prints:

```
Lattice daemon started — web UI at http://localhost:7337
```

Open [http://localhost:7337](http://localhost:7337) in your browser.

---

## 4. Capture your first memory

=== "Web UI"

    Type anything in the text box at [localhost:7337](http://localhost:7337) and press **Enter**.

=== "Terminal"

    ```bash
    uv run lc "I prefer dark roast coffee"
    ```

=== "MCP (Claude Code)"

    See [MCP Setup](mcp-setup.md).

---

## 5. Auto-start on login (optional)

To have the daemon start automatically when you log in, see [Auto-start on Login](../how-to/launchd-autostart.md).

---

## Verify it's working

```bash
uv run lattice-daemon status
```

Should return JSON like:

```json
{"ok": true, "atom_count": 1, "uptime_seconds": 42}
```

---

## Troubleshooting

**Daemon won't start — port in use**

```bash
lsof -i :7337
# kill the process using the port, then restart
```

**`lc` command not found**

```bash
# make sure you're using uv run
uv run lc "test"
# or add the venv to PATH:
source .venv/bin/activate
```

**Ollama model not responding**

```bash
ollama list        # confirm model is downloaded
ollama run gemma4  # test it directly
```

**"LATTICE_DIR not set" error**

Make sure `LATTICE_DIR` is exported in your current shell session or `.env` file.
