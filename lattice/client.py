"""lattice.client: thin IPC client for the lattice daemon."""
from __future__ import annotations

import json
import socket
from pathlib import Path

from lattice.config import Config


def _default_sock_path() -> Path:
    return Config.from_env().sock_path


class DaemonClient:
    def __init__(self, sock_path: str | Path | None = None):
        self.sock_path = Path(sock_path) if sock_path is not None else _default_sock_path()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Return True if the daemon is alive, False if socket not found."""
        try:
            resp = self._send({"op": "ping"})
            return bool(resp.get("pong"))
        except (FileNotFoundError, ConnectionRefusedError, OSError):
            return False

    def ingest(self, text: str, source_id: str = "client", metadata: dict | None = None) -> list[str]:
        """Send an ingest request; return atom_ids. Raise RuntimeError on error response."""
        msg: dict = {"op": "ingest", "text": text, "source_id": source_id}
        if metadata:
            msg["metadata"] = metadata
        resp = self._send(msg)
        if not resp.get("ok"):
            raise RuntimeError(resp.get("error", "ingest failed"))
        return resp["atom_ids"]

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _send(self, msg: dict) -> dict:
        """Open a fresh Unix socket connection, send *msg* as a JSON newline, read reply."""
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.connect(str(self.sock_path))
            s.sendall((json.dumps(msg) + "\n").encode())
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
        return json.loads(data.strip())
