"""Central configuration for the lattice daemon and web server.

All environment variables for daemon/web/client paths are read here.
Business logic receives a Config instance rather than calling os.environ inline.
LLM vars (LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL) remain in llm.py
pending a broader refactor of that seam (see ENGINEERING_GUIDE.md rule 2/8).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_path(key: str, default: Path) -> Path:
    val = os.environ.get(key)
    return Path(val) if val else default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        raise ValueError(f"Env var {key} must be an integer, got {val!r}")


@dataclass
class Config:
    lattice_dir: Path
    sock_path: Path
    inbox_dir: Path
    processed_dir: Path
    web_host: str
    web_port: int
    log_path: Path
    pid_path: Path

    @classmethod
    def from_env(cls) -> "Config":
        lattice_dir = _env_path("LATTICE_DIR", Path.home() / ".lattice")
        return cls(
            lattice_dir=lattice_dir,
            sock_path=_env_path("LATTICE_SOCK", lattice_dir / "daemon.sock"),
            inbox_dir=_env_path("LATTICE_INBOX", lattice_dir / "inbox"),
            processed_dir=lattice_dir / "processed",
            web_host=os.environ.get("LATTICE_WEB_HOST", "127.0.0.1"),
            web_port=_env_int("LATTICE_WEB_PORT", 7337),
            log_path=lattice_dir / "daemon.log",
            pid_path=lattice_dir / "daemon.pid",
        )
