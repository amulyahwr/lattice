"""Central configuration for the lattice daemon and web server.

All environment variables are read here. Modules receive a Config instance
rather than calling os.environ inline. Construct with Config.from_env() in
entrypoints; construct directly (Config(lattice_dir=tmp_path)) in tests.
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
    # ── paths ──────────────────────────────────────────────────────────────────
    # Derived path fields default to None and are filled by __post_init__.
    lattice_dir: Path = field(default_factory=lambda: Path.home() / ".lattice")
    sock_path: Path = field(default=None)       # type: ignore[assignment]
    inbox_dir: Path = field(default=None)       # type: ignore[assignment]
    processed_dir: Path = field(default=None)   # type: ignore[assignment]
    web_host: str = "127.0.0.1"
    web_port: int = 7337
    log_path: Path = field(default=None)        # type: ignore[assignment]
    pid_path: Path = field(default=None)        # type: ignore[assignment]

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_provider: str = "ollama"
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    llm_num_ctx: int = 4096
    ingest_model: str | None = None
    synthesis_model: str | None = None

    # ── selection ─────────────────────────────────────────────────────────────
    recommendation_cap: int = 5
    seed_min_score: float = 0.0
    dense_seeds: bool = False
    dense_top_k: int = 10
    bfs_rescore: bool = False
    time_decay: bool = True

    # ── ingest ────────────────────────────────────────────────────────────────
    subject_fuzzy_threshold: int = 80
    ingest_workers: int = 1

    # ── PII ───────────────────────────────────────────────────────────────────
    pii_scrub: bool = True
    ner_model: str = ""

    # ── embed ─────────────────────────────────────────────────────────────────
    embed_model: str = "BAAI/bge-small-en-v1.5"

    def __post_init__(self) -> None:
        if self.sock_path is None:
            self.sock_path = self.lattice_dir / "daemon.sock"
        if self.inbox_dir is None:
            self.inbox_dir = self.lattice_dir / "inbox"
        if self.processed_dir is None:
            self.processed_dir = self.lattice_dir / "processed"
        if self.log_path is None:
            self.log_path = self.lattice_dir / "daemon.log"
        if self.pid_path is None:
            self.pid_path = self.lattice_dir / "daemon.pid"

    @classmethod
    def from_env(cls) -> "Config":
        lattice_dir = _env_path("LATTICE_DIR", Path.home() / ".lattice")
        return cls(
            lattice_dir=lattice_dir,
            sock_path=_env_path("LATTICE_SOCK", lattice_dir / "daemon.sock"),
            inbox_dir=_env_path("LATTICE_INBOX", lattice_dir / "inbox"),
            web_host=os.environ.get("LATTICE_WEB_HOST", "127.0.0.1"),
            web_port=_env_int("LATTICE_WEB_PORT", 7337),
            # LLM
            llm_provider=os.environ.get("LLM_PROVIDER", "ollama"),
            llm_model=os.environ.get("LLM_MODEL") or None,
            llm_api_key=os.environ.get("LLM_API_KEY") or None,
            llm_base_url=os.environ.get("LLM_BASE_URL") or None,
            llm_num_ctx=_env_int("LLM_NUM_CTX", 4096),
            ingest_model=os.environ.get("INGEST_MODEL") or None,
            synthesis_model=os.environ.get("SYNTHESIS_MODEL") or None,
            # selection
            recommendation_cap=_env_int("LATTICE_RECOMMENDATION_CAP", 5),
            seed_min_score=float(os.environ.get("LATTICE_SEED_MIN_SCORE", "0.0")),
            dense_seeds=os.environ.get("LATTICE_DENSE_SEEDS", "").lower() in ("1", "true"),
            dense_top_k=_env_int("LATTICE_DENSE_TOP_K", 10),
            bfs_rescore=os.environ.get("LATTICE_BFS_RESCORE", "").lower() in ("1", "true"),
            time_decay=os.environ.get("LATTICE_TIME_DECAY", "1").lower() not in ("0", "false"),
            # ingest
            subject_fuzzy_threshold=_env_int("LATTICE_SUBJECT_FUZZY_THRESHOLD", 80),
            ingest_workers=max(1, _env_int("LATTICE_INGEST_WORKERS", 1)),
            # PII
            pii_scrub=os.environ.get("LATTICE_PII_SCRUB", "true").lower() not in ("0", "false", "no"),
            ner_model=os.environ.get("LATTICE_NER_MODEL", ""),
            # embed
            embed_model=os.environ.get("LATTICE_EMBED_MODEL", "BAAI/bge-small-en-v1.5"),
        )
