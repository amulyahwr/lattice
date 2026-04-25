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

    # Compiler
    compiler_llm_model: str = ""  # Empty = extractive only (no LLM for MVP)

    # Access control
    atom_access_bits: int = 64  # 64-bit bitmask for MVP

    # Cache
    cache_backend: str = "memory"  # "memory" for MVP, "redis" later

    class Config:
        env_prefix = "LATTICE_"


settings = Settings()
