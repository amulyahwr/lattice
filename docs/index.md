# Lattice

**Your second brain — local, structured, private, and omnipresent.**

Lattice is a personal memory OS that runs entirely on your own machine. Every thought you capture becomes a typed, timestamped _atom_ stored as plain markdown. Ask anything; get a prose answer with citations. No cloud account required. No vendor in the middle. Your memories live on your device and nowhere else.

---

## The quick version

```bash
# install (--group full adds semantic search, PDF, Telegram, Office file support)
uv sync --group full

# set env vars
export LLM_PROVIDER=ollama
export LLM_MODEL=gemma4
export LATTICE_DIR=~/.lattice

# start the daemon (web UI at localhost:7337)
uv run lattice-daemon

# capture a thought from the terminal
uv run lc "I want to read Thinking, Fast and Slow"

# ask a question
# open http://localhost:7337 in your browser
```

---

## How it works

```
you type a thought
        ↓
  daemon segments it
        ↓
  LLM extracts atoms  ──→  stored as .md files in LATTICE_DIR
        ↓
  graph links them
        ↓
  you ask a question
        ↓
  BM25 + graph BFS finds relevant atoms
        ↓
  LLM synthesizes a prose answer with citations
```

---

## Where to go next

<div class="grid cards" markdown>

- :material-clock-fast: **[Quick Install](getting-started/quick-install.md)**

    Get Lattice running in 5 minutes.

- :material-lightbulb-outline: **[What is Lattice?](getting-started/what-is-lattice.md)**

    Understand the mental model before you start.

- :material-connection: **[MCP Setup](getting-started/mcp-setup.md)**

    Wire Lattice into Claude Code as a memory layer.

- :material-cog: **[Config Reference](reference/config.md)**

    All environment variables with defaults and examples.

</div>
