"""S1 acceptance tests: daemon lifecycle, PID file, socket, graceful shutdown."""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

TIMEOUT = 10  # seconds to wait for daemon to come up


def _wait_for_pid(pid_path: Path, timeout: float = TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pid_path.exists():
            return True
        time.sleep(0.1)
    return False


def _wait_for_sock(sock_path: Path, timeout: float = TIMEOUT) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if sock_path.exists():
            return True
        time.sleep(0.1)
    return False


def _ping(sock_path: Path) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(sock_path))
        s.sendall(json.dumps({"op": "ping"}).encode() + b"\n")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
    return json.loads(data.strip())


@pytest.fixture()
def lattice_tmp(tmp_path):
    return tmp_path / "lattice"


@pytest.fixture()
def daemon_proc(lattice_tmp):
    env = os.environ.copy()
    env["LATTICE_DIR"] = str(lattice_tmp)
    env["LATTICE_SOCK"] = str(lattice_tmp / "daemon.sock")
    proc = subprocess.Popen(
        [sys.executable, "-m", "lattice.daemon"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pid_path = lattice_tmp / "daemon.pid"
    assert _wait_for_pid(pid_path), "daemon did not write PID file in time"
    assert _wait_for_sock(lattice_tmp / "daemon.sock"), "daemon socket not ready"
    yield proc, lattice_tmp
    if proc.poll() is None:
        proc.terminate()
        proc.wait(timeout=15)


def test_daemon_writes_pid(daemon_proc):
    proc, lattice_tmp = daemon_proc
    pid_path = lattice_tmp / "daemon.pid"
    assert pid_path.exists()
    pid = int(pid_path.read_text().strip())
    assert pid == proc.pid


def test_daemon_stays_alive(daemon_proc):
    proc, _ = daemon_proc
    time.sleep(0.5)
    assert proc.poll() is None, "daemon exited unexpectedly"


def test_daemon_socket_responds(daemon_proc):
    proc, lattice_tmp = daemon_proc
    resp = _ping(lattice_tmp / "daemon.sock")
    assert resp == {"ok": True, "pong": True}


def test_daemon_graceful_shutdown_sigterm(daemon_proc):
    proc, lattice_tmp = daemon_proc
    pid_path = lattice_tmp / "daemon.pid"
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=TIMEOUT)
    assert proc.returncode == 0
    assert not pid_path.exists(), "PID file should be cleaned up"


def test_daemon_graceful_shutdown_sigint(daemon_proc):
    proc, lattice_tmp = daemon_proc
    pid_path = lattice_tmp / "daemon.pid"
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=TIMEOUT)
    assert proc.returncode == 0
    assert not pid_path.exists(), "PID file should be cleaned up"


def test_status_stopped(tmp_path, monkeypatch):
    """status subcommand reports stopped when no pid file."""
    monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
    result = subprocess.run(
        [sys.executable, "-m", "lattice.daemon", "status"],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout.strip())
    assert data["status"] == "stopped"


def test_status_running(daemon_proc):
    proc, lattice_tmp = daemon_proc
    result = subprocess.run(
        [sys.executable, "-m", "lattice.daemon", "status"],
        env={**os.environ, "LATTICE_DIR": str(lattice_tmp)},
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout.strip())
    assert data["status"] == "running"
    assert data["pid"] == proc.pid
