"""Lattice backend configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://lattice:lattice@localhost:5432/lattice",
    )

    # Embedding model
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8001

    # CORS
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # LM Studio (OpenAI-compatible local server)
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "google/gemma-4-e2b"
    lm_studio_timeout: int = 120  # seconds — local inference can be slow

    # Access control
    atom_access_bits: int = 64  # 64-bit bitmask for MVP

    class Config:
        env_prefix = "LATTICE_"


settings = Settings()

# ── Cross-source linking ──
# Each group defines domains that can have meaningful cross-source relationships.
# Expansion is one-hop only: a "sales" atom gets candidates from {sales, finance, product}.
DOMAIN_GROUPS: list[frozenset[str]] = [
    frozenset({"sales", "finance"}),
    frozenset({"sales", "product"}),
    frozenset({"engineering", "product"}),
    frozenset({"legal", "hr"}),
    frozenset({"legal", "finance"}),
]

# Top-K existing atom candidates to fetch per new atom (deduplicated across all new atoms).
CROSS_LINK_TOP_K: int = 5

# Minimum cosine similarity for a candidate to be considered (0 = any, 1 = identical).
CROSS_LINK_SIMILARITY_THRESHOLD: float = 0.5
