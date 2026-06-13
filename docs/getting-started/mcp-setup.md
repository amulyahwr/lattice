# MCP Setup (Claude Code)

Lattice exposes an MCP server so Claude Code can read and write your memory atoms during any conversation.

## What this gives you

- Claude Code **remembers** decisions, preferences, and facts across sessions
- You can ask Claude "what did I decide about X?" and get a grounded answer
- Captures made during a coding session are persisted to Lattice automatically

## Prerequisites

- Lattice daemon running (`uv run lattice-daemon`)
- Claude Code installed

## Configure the MCP server

Add Lattice to your Claude Code MCP config. Claude Code reads from `~/.claude/mcp_servers.json` (global) or `.mcp.json` in the project directory (project-local).

### Option A: Project-local (recommended for this repo)

Create `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "lattice": {
      "command": "uv",
      "args": ["run", "lattice"],
      "cwd": "/path/to/your/lattice-repo",
      "env": {
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "gemma4",
        "LATTICE_DIR": "/Users/yourname/.lattice"
      }
    }
  }
}
```

### Option B: Global (available in all projects)

```bash
claude mcp add lattice -- uv run --directory /path/to/lattice-repo lattice
```

Then set env vars in your shell profile so `uv run lattice` picks them up.

## Verify

In Claude Code, run:

```
/mcp
```

You should see `lattice` listed as a connected server with tools: `lattice_ingest`, `lattice_capture`, `lattice_select`, `lattice_answer`, `lattice_status`.

## Available MCP tools

| Tool | What it does |
|------|-------------|
| `lattice_ingest` | Save a fact or chunk of conversation to memory |
| `lattice_capture` | Save a session summary (use at end of conversation) |
| `lattice_select` | Find relevant atoms for a query (no synthesis) |
| `lattice_answer` | Find atoms + synthesize a prose answer |
| `lattice_status` | Atom count, streak, today's activity |

## Usage in conversation

Claude Code will call these tools automatically based on your instructions. You can also invoke them explicitly:

```
What did I decide about the database schema?
```

Claude Code will call `lattice_answer` with your question and return a cited answer from your atoms.

```
Save this decision: we're using PostgreSQL with UUID primary keys
```

Claude Code will call `lattice_ingest` with the fact.

```
Wrap up
```

At end-of-session, Claude Code will call `lattice_capture` with a summary of decisions made.

## How the MCP server connects to the daemon

`server.py` is the MCP stdio entrypoint. It holds one shared `LatticeDB` instance. Write operations (ingest, capture) are delegated over the Unix socket to the daemon — the daemon is the sole writer. Read operations (select, answer) run directly against the local DB cache.

This means:

- The MCP server does **not** need to be restarted when the daemon restarts
- Writes from Claude Code and writes from the web UI land in the same atom store
- The daemon must be running for writes to succeed; reads work even if the daemon is down

## Troubleshooting

**"Connection refused" on ingest**

The daemon is not running. Start it with `uv run lattice-daemon`.

**Tools visible but `lattice_answer` returns empty results**

No atoms in the store yet. Capture a few facts first, then ask.

**MCP server not appearing in `/mcp`**

Check that `cwd` and `LATTICE_DIR` in `.mcp.json` point to the correct paths. Use absolute paths.
