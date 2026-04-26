"""
Global test fixtures.

IMPORTANT: The os.environ.setdefault call below must execute before any
backend imports, because backend/models/database.py creates the SQLAlchemy
engine at import time using settings.database_url.
"""

from __future__ import annotations

import hashlib
import math
import os
import secrets
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

# ── Must be set before any backend imports ──────────────────────────────────
os.environ.setdefault(
    "LATTICE_DATABASE_URL",
    "postgresql+asyncpg://lattice:lattice@localhost:5432/lattice_test",
)

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from tests.helpers import make_vector

TEST_DB_URL = os.environ["LATTICE_DATABASE_URL"]


# ── DB Engine (session-scoped: create tables once per run) ───────────────────


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Create async engine for the test DB, install pgvector, create all tables."""
    from backend.models.database import Base

    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ── Per-test connection + session (SAVEPOINT isolation) ──────────────────────


@pytest_asyncio.fixture(scope="function")
async def db_conn(db_engine) -> AsyncGenerator[AsyncConnection, None]:
    """Open a connection and begin an outer transaction for each test."""
    async with db_engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()


@pytest_asyncio.fixture(scope="function")
async def db_session(db_conn) -> AsyncGenerator[AsyncSession, None]:
    """
    AsyncSession bound to the per-test connection.

    join_transaction_mode="create_savepoint" means that every session.commit()
    creates/releases a SAVEPOINT instead of committing the outer transaction.
    The outer transaction is always rolled back by db_conn after the test.
    """
    session_factory = async_sessionmaker(
        bind=db_conn,
        class_=AsyncSession,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    async with session_factory() as session:
        yield session


# ── Mock fixtures ────────────────────────────────────────────────────────────


class _MultiMock:
    """
    Proxy that synchronizes return_value and side_effect across multiple AsyncMocks.

    Each compiler module imports `chat` by name at module load time, so patching
    the source (llm_client.chat) has no effect on the local binding.  We must patch
    every module that does `from backend.compiler.llm_client import chat`.
    """

    def __init__(self, mocks: list[AsyncMock]):
        self.__dict__["_mocks"] = mocks

    @property
    def return_value(self):
        return self._mocks[0].return_value

    @return_value.setter
    def return_value(self, value: object) -> None:
        for m in self._mocks:
            m.return_value = value

    @property
    def side_effect(self):
        return self._mocks[0].side_effect

    @side_effect.setter
    def side_effect(self, value: object) -> None:
        for m in self._mocks:
            m.side_effect = value

    @property
    def call_count(self) -> int:
        return sum(m.call_count for m in self._mocks)

    def assert_not_called(self) -> None:
        for m in self._mocks:
            m.assert_not_called()

    def reset_mock(self) -> None:
        for m in self._mocks:
            m.reset_mock()


_CHAT_TARGETS = [
    "backend.compiler.atomizer.chat",
    "backend.compiler.distiller.chat",
    "backend.compiler.linker.chat",
    "backend.compiler.tagger.chat",
]


@pytest.fixture
def mock_chat():
    """
    Patch `chat` in every compiler module that imported it by name.
    Tests set .return_value or .side_effect on the returned proxy; all
    four mocks are kept in sync automatically.
    """
    patches = [patch(t, new_callable=AsyncMock) for t in _CHAT_TARGETS]
    mocks = [p.start() for p in patches]
    proxy = _MultiMock(mocks)
    proxy.return_value = "[]"
    yield proxy
    for p in patches:
        p.stop()


@pytest.fixture
def mock_embed_texts():
    """
    Patch embed_texts (plural) used by pipeline.py.
    Returns one deterministic 384-dim vector per input text.
    """
    with patch("backend.engine.embeddings.embed_texts") as m:
        m.side_effect = lambda texts: [make_vector(i) for i in range(len(texts))]
        yield m


@pytest.fixture
def mock_embed_text():
    """
    Patch embed_text (singular) used by l3_search.py for query embedding.
    Always returns make_vector(0).
    """
    with patch("backend.engine.embeddings.embed_text") as m:
        m.return_value = make_vector(0)
        yield m


@pytest.fixture(autouse=False)
def clear_l2_cache():
    """Deprecated fixture - L2 cache removed. Kept for backward compatibility."""
    yield


# ── FastAPI test client ───────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def http_client(db_session: AsyncSession):
    """
    AsyncClient for the FastAPI app.
    Overrides get_db to inject the per-test rolled-back session so all
    request-level DB writes stay within the test's SAVEPOINT.
    """
    from backend.main import app
    from backend.models.database import get_db

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


# ── Factory fixtures ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def make_agent(db_session: AsyncSession):
    """
    Factory: call make_agent(name=..., role_mask=...) to insert an AgentProfile.
    Returns the ORM object with api_key set.
    """
    from backend.models.atoms import AgentProfile

    async def _make(
        name: str = "test-agent",
        role_mask: int = 0xFF,
        domains: list[str] | None = None,
        max_tokens: int = 4000,
        purpose: str = "Test agent",
    ) -> AgentProfile:
        agent = AgentProfile(
            id=uuid.uuid4(),
            name=name,
            api_key=f"lat_{secrets.token_urlsafe(16)}",
            purpose=purpose,
            domains=domains or [],
            role_mask=role_mask,
            max_tokens=max_tokens,
        )
        db_session.add(agent)
        await db_session.flush()
        return agent

    yield _make


@pytest_asyncio.fixture
async def make_source(db_session: AsyncSession):
    """Factory: inserts a Source row and returns it."""
    from backend.models.atoms import Source

    async def _make(
        name: str = "test.txt",
        source_type: str = "text",
        domains: list[str] | None = None,
    ) -> Source:
        source = Source(
            id=uuid.uuid4(),
            name=name,
            source_type=source_type,
            domains=domains or [],
        )
        db_session.add(source)
        await db_session.flush()
        return source

    yield _make


@pytest_asyncio.fixture
async def make_atom(db_session: AsyncSession):
    """
    Factory: inserts an Atom row with optional overrides.
    Useful for serving/API tests that need atoms with specific access_masks and vectors.
    """
    from backend.models.atoms import Atom

    async def _make(
        content: str = "Revenue grew 20% in Q2.",
        kind: str = "metric",
        access_mask: int = 0xFF,
        domain: list[str] | None = None,
        dense_vec: list[float] | None = None,
    ) -> Atom:
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        atom = Atom(
            id=uuid.uuid4(),
            content=content,
            raw_content=content,
            content_hash=content_hash,
            kind=kind,
            domain=domain or ["general"],
            access_mask=access_mask,
            dense_vec=dense_vec or make_vector(0),
            freshness=datetime.now(timezone.utc),
            confidence=1.0,
            links=[],
            compiled_at=datetime.now(timezone.utc),
            version=1,
        )
        db_session.add(atom)
        await db_session.flush()
        return atom

    yield _make
