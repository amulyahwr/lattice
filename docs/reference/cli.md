# CLI Reference

## `lc` — quick capture

```bash
uv run lc <text>
uv run lc <path/to/file>
uv run lc status
uv run lc clear
```

Requires daemon running. Fails fast if daemon is not reachable.

### `lc <text>`

Capture a one-liner to Lattice.

```bash
uv run lc "decided to use PostgreSQL with UUID primary keys"
```

Prints: `captured: 1 new` (or `1 updated`, `0 new — duplicate skipped`)

If `is_followup()` detects an anaphoric query (pronoun, short text, no proper noun), prints a tip: `Tip: this looks like a follow-up — use the web UI or Telegram for multi-turn context.`

### `lc <path/to/file>`

Ingest a file. Supported types: `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.md`, `.txt`.

```bash
uv run lc ~/Documents/meeting-notes.md
uv run lc ~/Downloads/report.pdf
```

### `lc status`

Print memory count, streak, and today's journey (grouped capture/recall branches).

```
Lattice status
  147 atoms  |  12 days deep
  Today: 3 captures, 2 recalls

  Journey
  └── coffee preference (09:12)
  └── project decisions (14:30)
      ├── what stack should I use?
      └── should I use TypeScript?
```

### `lc clear`

Remove today's chat turns from `chat.jsonl`. Same effect as the web UI "clear" button and Telegram `/reset`.

---

## `lattice-daemon` — daemon process

```bash
uv run lattice-daemon           # start daemon + web UI
uv run lattice-daemon status    # check health (JSON)
```

### `lattice-daemon` (no args)

Start the persistent daemon. Runs in foreground; use launchd or systemd for production. Logs to `LATTICE_DIR/daemon.log`.

Starts:
- Unix socket listener at `LATTICE_SOCK`
- Filesystem watcher on `LATTICE_INBOX`
- FastAPI web server at `http://LATTICE_WEB_HOST:LATTICE_WEB_PORT`

### `lattice-daemon status`

Query the running daemon. Returns JSON:

```json
{
  "ok": true,
  "atom_count": 147,
  "uptime_seconds": 3614,
  "inbox_pending": 0
}
```

Exits 1 if the daemon is not running.

---

## `lattice` — MCP stdio server

```bash
uv run lattice
```

Starts the MCP server in stdio mode. Used by Claude Code; not intended to be run directly.

---

## `lattice-telegram` — Telegram bot

```bash
uv run lattice-telegram
```

Starts the Telegram polling bot. Requires `LATTICE_TELEGRAM_TOKEN`. See [Telegram Setup](../how-to/telegram-setup.md).

---

## Future: `lattice graph` subcommands

These commands are planned (STORY-049) and not yet implemented:

```bash
uv run lattice graph rebuild    # rebuild graph sidecars from atoms
uv run lattice graph status     # schema version + node/edge counts
uv run lattice graph migrate    # run pending migrations
```
