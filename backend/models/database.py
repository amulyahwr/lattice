"""Database setup and session management."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    """Dependency that yields a database session."""
    async with async_session() as session:
        yield session


async def init_db():
    """Create all tables and install pgvector extension."""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations for columns added after initial schema creation
        await conn.execute(text(
            "ALTER TABLE atoms ADD COLUMN IF NOT EXISTS valid_from TIMESTAMPTZ DEFAULT NOW()"
        ))
        await conn.execute(text(
            "ALTER TABLE atoms ADD COLUMN IF NOT EXISTS valid_until TIMESTAMPTZ"
        ))
        await conn.execute(text(
            "ALTER TABLE atoms ADD COLUMN IF NOT EXISTS is_superseded BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE atoms ADD COLUMN IF NOT EXISTS superseded_by UUID REFERENCES atoms(id)"
        ))
        # Drop unique constraint on canonical_hash — no longer used as a dedup gate
        await conn.execute(text(
            "ALTER TABLE atoms DROP CONSTRAINT IF EXISTS atoms_canonical_hash_key"
        ))
