# Lattice

**Lattice is your second brain — local, structured, private, and omnipresent.**

**[📖 Full documentation → amulyahwr.github.io/lattice](https://amulyahwr.github.io/lattice)**

Your personal memory OS — local, private, always running. Everything you tell it becomes a typed, timestamped fact stored as plain markdown on your own machine. Ask it anything; it answers in prose with citations.

---

## The pitch

### For everyone

**The problem**

Your life generates more than you can hold. Decisions, reminders, half-formed ideas, things you learned last Tuesday — most of it disappears. What if you could offload all of it to a [second brain](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) that breaks every thought into a small, typed, timestamped _memory_, and actually organizes it so you can find it again?

**The gap**

The right pieces exist — LLM agents that ingest, connect, and synthesize information. But every tool built on them stores your memories as flat blobs of text, with no structure and no connections. Worse, they live on someone else's server. You can't truly delete a memory. You can't see what's stored. Your second brain isn't yours.

**Lattice**

Memories become powerful when they connect — a decision linked to the facts that drove it, a preference linked to the experience that shaped it. Connect enough memories and you get a _lattice_: a structured graph of everything you know, living on your own device. Send a thought from your phone while commuting, find it waiting on your laptop at work, ask for it from your car on the way home — no vendor in the middle, no lock-in, no permission needed. Any device. Any OS. Any platform. Your second brain. Your memories. Your rules. The longer you use it, the smarter it gets — memories that prove useful rise to the top, and Lattice quietly notices connections between things you captured separately.

---

### For engineers

_This is what "local, structured, private" actually means in code. What you call a memory, Lattice calls an atom._

Every piece of text enters a pipeline that segments by source type, then runs an LLM extraction pass to decompose it into typed, timestamped atoms — stored as plain `.md` files with YAML frontmatter. Human-readable, git-trackable, hand-editable. After every write, a `LatticeGraph` (networkx `MultiDiGraph`) commits sidecars to disk linking atoms by subject, provenance, supersession, and episode.

The query path is deliberately LLM-free: BM25 seeds → optional dense semantic search (handles vocab mismatch and spelling tolerance) → graph BFS expands the evidence pack → a single streaming LLM call synthesizes a prose answer with citations. A persistent daemon owns all writes; MCP server, web UI, Telegram bot, `lc` CLI, and browser extension are all read-only clients over a Unix socket. PII round-trip redaction via `EntityRedactor` ensures sensitive names never reach cloud APIs — atoms on disk always contain real names.

→ **[Full architecture and module map](docs/contributing/architecture.md)**

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

## Quick start

```bash
git clone https://github.com/amulyahwr/lattice
cd lattice
uv sync --group full

export LLM_PROVIDER=ollama LLM_MODEL=gemma4 LATTICE_DIR=~/.lattice
uv run lattice-daemon        # web UI at http://localhost:7337
uv run lc "my first memory"  # capture from terminal
```

---

## Documentation

**→ [amulyahwr.github.io/lattice](https://amulyahwr.github.io/lattice)**

| | |
|---|---|
| [Quick Install](https://amulyahwr.github.io/lattice/getting-started/quick-install/) | Ollama, OpenRouter, Anthropic setup |
| [MCP Setup](https://amulyahwr.github.io/lattice/getting-started/mcp-setup/) | Wire into Claude Code |
| [Telegram Bot](https://amulyahwr.github.io/lattice/how-to/telegram-setup/) | Capture from your phone |
| [Config Reference](https://amulyahwr.github.io/lattice/reference/config/) | All environment variables |
| [HTTP API](https://amulyahwr.github.io/lattice/reference/api/) | All endpoints |
| [Architecture](https://amulyahwr.github.io/lattice/contributing/architecture/) | Module map, design invariants |
