"""lattice-daemon: persistent daemon that owns all LatticeDB writes."""
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from watchdog.events import FileCreatedEvent, FileMovedEvent, FileSystemEventHandler
from watchdog.observers import Observer

from lattice.config import Config
from lattice.db import LatticeDB

_LATTICE_DIR = Path(os.environ.get("LATTICE_DIR", Path.home() / ".lattice"))
_PID_FILE = _LATTICE_DIR / "daemon.pid"
_SOCKET_PATH = _LATTICE_DIR / "daemon.sock"

_shutdown = threading.Event()
_db: LatticeDB | None = None

log = logging.getLogger("lattice.daemon")


# ---------------------------------------------------------------------------
# JSON-lines log formatter
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        obj: dict = {
            "ts": ts,
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        # Attach any extra fields stored on the record (skip standard attrs)
        _SKIP = {
            "name", "msg", "args", "levelname", "levelno", "pathname",
            "filename", "module", "exc_info", "exc_text", "stack_info",
            "lineno", "funcName", "created", "msecs", "relativeCreated",
            "thread", "threadName", "processName", "process", "taskName",
            "message",
        }
        for key, val in record.__dict__.items():
            if key not in _SKIP and not key.startswith("_"):
                obj[key] = val
        if record.exc_info:
            obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(obj)


# ---------------------------------------------------------------------------
# Signal handling
# ---------------------------------------------------------------------------

def _handle_signal(signum, frame):
    log.info("signal %s received — shutting down", signum)
    _shutdown.set()


# ---------------------------------------------------------------------------
# IPC connection handler
# ---------------------------------------------------------------------------

def _handle_conn(conn: socket.socket):
    with conn:
        try:
            data = b""
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            if not data.strip():
                return
            msg = json.loads(data.strip())
            response = _dispatch(msg)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        conn.sendall((json.dumps(response) + "\n").encode())


def _dispatch(msg: dict) -> dict:
    op = msg.get("op")
    if op == "ping":
        return {"ok": True, "pong": True}
    if op == "ingest":
        from lattice.ingest import ingest
        text = msg.get("text", "")
        source_id = msg.get("source_id", "ipc")
        metadata: dict = msg.get("metadata") or {}
        metadata["source_id"] = source_id  # source_id always wins (top-level field)
        log.info(
            "ingest job start",
            extra={"event": "ingest_start", "source_id": source_id, "text_len": len(text)},
        )
        t0 = time.monotonic()
        try:
            result = ingest(text, metadata=metadata, db=_db)
        except Exception as exc:
            log.error(
                "ingest job error",
                exc_info=True,
                extra={"event": "ingest_error", "source_id": source_id, "error": str(exc)},
            )
            raise
        duration_ms = int((time.monotonic() - t0) * 1000)
        atom_count = result.get("atoms_created", 0)
        log.info(
            "ingest job end",
            extra={
                "event": "ingest_end",
                "source_id": source_id,
                "atom_count": atom_count,
                "duration_ms": duration_ms,
            },
        )
        return {
            "ok": True,
            "atom_ids": result.get("atom_ids", []),
            "atoms_new": result.get("atoms_new", 0),
            "atoms_updated": result.get("atoms_updated", 0),
            "duplicates_skipped": result.get("duplicates_skipped", 0),
        }
    return {"ok": False, "error": f"unknown op: {op!r}"}


# ---------------------------------------------------------------------------
# Inbox watcher
# ---------------------------------------------------------------------------

# No extension whitelist — all files attempted; binary files rejected at read time

# Filename pattern for telegram inbox files: telegram-{chat_id}-{uuid}.txt
_TELEGRAM_INBOX_PREFIX = "telegram-"


def _notify_telegram(fname: str, atom_count: int) -> None:
    """If this inbox file came from the Telegram bot, send a follow-up reply."""
    if not fname.startswith(_TELEGRAM_INBOX_PREFIX):
        return
    token = os.environ.get("LATTICE_TELEGRAM_TOKEN", "").strip()
    if not token:
        return
    # Extract chat_id from filename: telegram-{chat_id}-{uuid}.txt
    try:
        chat_id = int(fname[len(_TELEGRAM_INBOX_PREFIX):].split("-")[0])
    except (ValueError, IndexError):
        return
    import urllib.request
    n = atom_count
    text = (
        f"Back online — processed what you sent earlier. {n} thing{'s' if n != 1 else ''} saved. ✓"
        if n > 0
        else "Back online — processed what you sent earlier. Nothing new to add this time."
    )
    payload = json.dumps({"chat_id": chat_id, "text": text}).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        log.info("telegram: sent inbox confirmation to chat_id=%d", chat_id)
    except Exception as exc:
        log.warning("telegram: failed to send inbox confirmation: %s", exc)


class InboxEventHandler(FileSystemEventHandler):
    """Ingest new text files dropped into the inbox dir, then move to processed/."""

    def __init__(self, db: LatticeDB, processed_dir: Path):
        self._db = db
        self._processed_dir = processed_dir

    def _handle_path(self, path: str) -> None:
        p = Path(path)
        try:
            from lattice.util import extract_file_text
            try:
                text, source_id = extract_file_text(p)
            except ImportError as exc:
                log.error("inbox: missing optional dep for %s — %s", p.name, exc)
                return
            except ValueError as exc:
                log.warning("inbox: skipping %s — %s", p.name, exc)
                dest = self._processed_dir / p.name
                shutil.move(str(p), str(dest))
                return
            from lattice.ingest import ingest
            result = ingest(text, metadata={"source_id": source_id}, db=self._db)
            atom_count = result.get("atoms_created", 0)
            log.info(
                "inbox: ingested %s atoms from %s",
                atom_count, p.name,
                extra={"event": "inbox_ingest", "source_id": p.name, "atom_count": atom_count},
            )
            dest = self._processed_dir / p.name
            shutil.move(str(p), str(dest))
            log.info("inbox: moved %s → processed/", p.name)
            _notify_telegram(p.name, atom_count)
        except Exception:
            log.exception("inbox: error processing %s", p.name)

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.src_path)

    def on_moved(self, event: FileMovedEvent) -> None:
        if not event.is_directory:
            self._handle_path(event.dest_path)


def _drain_inbox(handler: InboxEventHandler, cfg: Config) -> None:
    """Process any files already sitting in the inbox at startup."""
    existing = [p for p in cfg.inbox_dir.iterdir() if p.is_file()]
    if existing:
        log.info("inbox: draining %d pre-existing file(s) at startup", len(existing))
    for p in existing:
        handler._handle_path(str(p))


def _start_inbox_watcher(db: LatticeDB, cfg: Config) -> Observer:
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.processed_dir.mkdir(parents=True, exist_ok=True)

    handler = InboxEventHandler(db=db, processed_dir=cfg.processed_dir)
    _drain_inbox(handler, cfg)

    observer = Observer()
    observer.schedule(handler, str(cfg.inbox_dir), recursive=False)
    observer.start()
    log.info("inbox watcher started at %s", cfg.inbox_dir)
    return observer


# ---------------------------------------------------------------------------
# Socket server
# ---------------------------------------------------------------------------

def _serve(sock: socket.socket):
    sock.listen(8)
    while not _shutdown.is_set():
        sock.settimeout(1.0)
        try:
            conn, _ = sock.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        t = threading.Thread(target=_handle_conn, args=(conn,), daemon=True)
        t.start()


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def _write_pid(cfg: Config) -> None:
    cfg.lattice_dir.mkdir(parents=True, exist_ok=True)
    cfg.pid_path.write_text(str(os.getpid()))


def _cleanup(cfg: Config) -> None:
    cfg.pid_path.unlink(missing_ok=True)
    cfg.sock_path.unlink(missing_ok=True)


def run():
    global _db

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    cfg = Config.from_env()
    cfg.lattice_dir.mkdir(parents=True, exist_ok=True)

    fh = logging.FileHandler(cfg.log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(_JsonFormatter())
    log.addHandler(fh)

    _db = LatticeDB(cfg.lattice_dir)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    _write_pid(cfg)
    log.info("daemon started pid=%d lattice_dir=%s", os.getpid(), cfg.lattice_dir)

    cfg.sock_path.unlink(missing_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(cfg.sock_path))

    server_thread = threading.Thread(target=_serve, args=(sock,), daemon=True)
    server_thread.start()
    log.info("IPC socket listening at %s", cfg.sock_path)

    observer = _start_inbox_watcher(_db, cfg)

    import uvicorn
    from lattice.web.app import app as web_app
    uv_config = uvicorn.Config(web_app, host=cfg.web_host, port=cfg.web_port, log_level="warning")
    web_server = uvicorn.Server(uv_config)
    web_thread = threading.Thread(target=web_server.run, daemon=True)
    web_thread.start()
    log.info("web server started at http://%s:%d", cfg.web_host, cfg.web_port)

    _shutdown.wait()

    log.info("shutting down")
    web_server.should_exit = True
    observer.stop()
    observer.join(timeout=3)
    sock.close()
    server_thread.join(timeout=3)
    _cleanup(cfg)
    log.info("daemon stopped")


def _parse_last_ingest(log_path: Path) -> str | None:
    """Return ISO timestamp of the last ingest_end event in the log, or None."""
    if not log_path.exists():
        return None
    last_ts = None
    try:
        with log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("event") == "ingest_end":
                        last_ts = obj.get("ts")
                except (json.JSONDecodeError, ValueError):
                    continue
    except OSError:
        pass
    return last_ts


def status():
    """Print daemon status to stdout."""
    cfg = Config.from_env()

    if not cfg.pid_path.exists():
        result: dict = {"status": "stopped"}
        result["last_ingest"] = _parse_last_ingest(cfg.log_path)
        result["atom_count"] = _count_atoms(cfg.lattice_dir)
        print(json.dumps(result))
        return

    pid = int(cfg.pid_path.read_text().strip())
    try:
        os.kill(pid, 0)
        running = True
    except OSError:
        running = False

    result = {
        "status": "running" if running else "stopped",
        "pid": pid,
        "last_ingest": _parse_last_ingest(cfg.log_path),
        "atom_count": _count_atoms(cfg.lattice_dir),
    }
    print(json.dumps(result))


def _count_atoms(lattice_dir: Path) -> int:
    """Count non-superseded atoms in lattice_dir without importing heavy deps if dir missing."""
    if not lattice_dir.exists():
        return 0
    try:
        db = LatticeDB(lattice_dir)
        return len([a for a in db.all() if not a.is_superseded])
    except Exception:
        return 0


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        status()
    else:
        run()


if __name__ == "__main__":
    main()
