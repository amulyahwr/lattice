"""S3 acceptance tests: DaemonClient sends/receives correct JSON over Unix socket."""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path

import pytest

from lattice.client import DaemonClient


# ---------------------------------------------------------------------------
# Helpers: in-process mock Unix socket server
# ---------------------------------------------------------------------------

def _make_mock_server(sock_path: Path, response: dict):
    """Bind a Unix socket at sock_path, accept one connection, respond with *response*."""
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(str(sock_path))
    srv.listen(1)
    srv.settimeout(5)

    received: list[dict] = []

    def _serve():
        try:
            conn, _ = srv.accept()
            with conn:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break
                if data.strip():
                    received.append(json.loads(data.strip()))
                conn.sendall((json.dumps(response) + "\n").encode())
        finally:
            srv.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t, received


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_ping_returns_true(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    t, _ = _make_mock_server(sock_path, {"ok": True, "pong": True})
    client = DaemonClient(sock_path=sock_path)
    result = client.ping()
    t.join(timeout=3)
    assert result is True


def test_ping_sends_correct_op(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    t, received = _make_mock_server(sock_path, {"ok": True, "pong": True})
    client = DaemonClient(sock_path=sock_path)
    client.ping()
    t.join(timeout=3)
    assert received == [{"op": "ping"}]


def test_ingest_returns_atom_ids(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    atom_ids = ["atom-abc", "atom-def"]
    t, _ = _make_mock_server(sock_path, {"ok": True, "atom_ids": atom_ids})
    client = DaemonClient(sock_path=sock_path)
    result = client.ingest("some text", source_id="test-src")
    t.join(timeout=3)
    assert result == atom_ids


def test_ingest_sends_correct_message(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    t, received = _make_mock_server(sock_path, {"ok": True, "atom_ids": []})
    client = DaemonClient(sock_path=sock_path)
    client.ingest("hello world", source_id="my-src")
    t.join(timeout=3)
    assert received == [{"op": "ingest", "text": "hello world", "source_id": "my-src"}]


def test_ingest_raises_on_error(tmp_path):
    sock_path = tmp_path / "daemon.sock"
    t, _ = _make_mock_server(sock_path, {"ok": False, "error": "boom"})
    client = DaemonClient(sock_path=sock_path)
    with pytest.raises(RuntimeError, match="boom"):
        client.ingest("text", source_id="src")
    t.join(timeout=3)


def test_ping_returns_false_when_socket_missing(tmp_path):
    sock_path = tmp_path / "no-such-daemon.sock"
    client = DaemonClient(sock_path=sock_path)
    assert client.ping() is False
