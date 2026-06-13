# The Daemon

The Lattice daemon is a persistent background process that owns all writes to the atom store. It is the only process that writes `.md` files to `LATTICE_DIR`.

## Why a daemon?

**Single writer, many readers.** The MCP server, web UI, `lc` CLI, Telegram bot, and browser extension are all clients. They delegate writes over a Unix socket to the daemon. This prevents concurrent write conflicts and ensures the graph and BM25 index are always consistent.

**Always-on capture.** The daemon watches `LATTICE_DIR/inbox/` via a filesystem watcher. Drop any `.md` or `.txt` file into the inbox and it's ingested within seconds, then moved to `processed/`. This is the primary file-drop capture path.

**Background work.** The daemon runs the auto-save sweep (every 30 minutes), which promotes completed chat threads to persistent atoms. It also spawns the FastAPI web server on startup.

## Starting the daemon

```bash
uv run lattice-daemon
```

```
Lattice daemon started — web UI at http://localhost:7337
```

## Checking status

```bash
uv run lattice-daemon status
```

Returns JSON:

```json
{
  "ok": true,
  "atom_count": 147,
  "uptime_seconds": 3614,
  "inbox_pending": 0
}
```

## IPC over Unix socket

The daemon listens on a Unix domain socket at `LATTICE_SOCK` (default: `LATTICE_DIR/lattice.sock`).

Clients send JSON messages:

```json
{"op": "ingest", "text": "I prefer vim over emacs", "source_id": "lc-cli"}
```

The daemon responds with:

```json
{"ok": true, "atoms_new": 1, "atoms_updated": 0, "duplicates_skipped": 0, "atom_ids": ["a1b2c3"]}
```

`DaemonClient` in `lattice/client.py` wraps this protocol. You don't need to call the socket directly.

## Inbox file drop

Drop a file into `LATTICE_DIR/inbox/`:

```bash
cp ~/notes/meeting.md ~/.lattice/inbox/
```

The daemon picks it up within seconds:
- Runs `ingest()` on the file content
- Moves the file to `~/.lattice/processed/meeting.md`
- Atoms appear in the web UI and graph immediately

Supported file types for the inbox: `.md`, `.txt`. For PDF/docx/xlsx, use the web UI file upload or `lc path/to/file.pdf`.

## Logs

The daemon writes JSON-lines to `LATTICE_DIR/daemon.log`:

```json
{"ts": "2025-11-14T09:12:00Z", "level": "INFO", "msg": "ingested 3 atoms", "source_id": "inbox/meeting.md"}
```

Tail the log:

```bash
tail -f ~/.lattice/daemon.log | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=2)) for l in sys.stdin]"
```

## Web UI

The daemon starts a FastAPI server on port `7337` (tunable via `LATTICE_WEB_PORT`). The web UI is served from `lattice/web/`. The daemon passes its own `LatticeDB` instance to the web app — they share one cache, so there are no stale reads across the write/query boundary.

## Auto-save sweep

Every 30 minutes, the daemon looks for completed chat threads in `chat.jsonl` — threads with ≥2 turns where the last turn is >10 minutes old. It runs `ingest()` on those threads with `channel=auto_save`, converting conversational captures into persistent atoms. Atoms with `channel=auto_save` skip the supersession check — they don't overwrite manually captured facts.

## What happens when the daemon is down

- **Writes fail** — `lc`, MCP ingest, and Telegram bot writes will error
- **Reads still work** — `lattice_select`, `lattice_answer`, and the web UI read path all work off the local `LatticeDB` cache
- The Telegram bot has a fallback: it writes an inbox file instead of calling the socket, and the daemon drains the inbox on restart
