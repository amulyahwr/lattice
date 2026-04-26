"""SQLAlchemy models for Lattice — Atom-based architecture.

Replaces the old Chunk/Entity/Relationship/Agent/AgentPermission models
with Atom, Frame, AgentProfile, Source, and AccessLog.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

from backend.config import settings
from backend.models.database import Base


class Source(Base):
    """A data source — identity, classification, and domain tags."""

    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # "pdf", "text", "markdown", etc.
    domains = Column(ARRAY(String), default=list)
    metadata_ = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Atom(Base):
    """A Context Atom — the smallest meaningful piece of context.

    Every piece of knowledge in Lattice is an atom: a discrete fact, decision,
    relationship, metric, event, or procedure with full metadata.
    """

    __tablename__ = "atoms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content = Column(Text, nullable=False)  # Distilled, token-efficient text
    raw_content = Column(Text, nullable=True)  # Original text before distillation
    content_hash = Column(String(64), nullable=True, unique=True)   # SHA-256 of distilled content — exact dedup
    canonical = Column(JSONB, nullable=True)                        # Structured form: {subject, predicate, object, value, unit, period}
    canonical_hash = Column(String(64), nullable=True, unique=True) # SHA-256 of canonical JSON — cross-source structural dedup
    kind = Column(
        String(50), nullable=False, default="fact"
    )  # fact | decision | metric | relationship | event | procedure
    dense_vec = Column(Vector(settings.embedding_dim), nullable=True)
    domain = Column(ARRAY(String), default=list)
    freshness = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confidence = Column(Float, default=1.0)
    access_mask = Column(BigInteger, default=0)  # 64-bit bitmask — OR of all source masks
    links = Column(JSONB, default=list)  # [{target_id: str, relation: str}, ...]
    compiled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    version = Column(Integer, default=1)

    __table_args__ = (
        Index("ix_atoms_kind", "kind"),
        Index("ix_atoms_domain", "domain", postgresql_using="gin"),
    )


class AtomSource(Base):
    """Join table — one atom can come from many sources.

    is_primary marks the first source that produced this atom.
    Subsequent sources that contain the same fact add rows with is_primary=False
    and cause the atom's access_mask to be OR-widened.
    """

    __tablename__ = "atom_sources"

    atom_id = Column(
        UUID(as_uuid=True), ForeignKey("atoms.id", ondelete="CASCADE"), primary_key=True
    )
    source_id = Column(
        UUID(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary = Column(Boolean, default=True, nullable=False)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_atom_sources_source", "source_id"),
        Index("ix_atom_sources_atom", "atom_id"),
    )


class Frame(Base):
    """A pre-assembled bundle of atoms for fast serving.

    Frames group atoms by domain and are cached in L2 for low-latency delivery.
    """

    __tablename__ = "frames"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    domain = Column(String(100), nullable=False)
    atom_ids = Column(ARRAY(UUID(as_uuid=True)), default=list)
    token_count = Column(Integer, default=0)
    access_mask = Column(BigInteger, default=0)  # Union of all atom access masks
    last_accessed = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    access_count = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_frames_domain", "domain"),
    )


class AgentProfile(Base):
    """An agent's identity — purpose, role mask, domains, and token budget."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    api_key = Column(String(255), nullable=False, unique=True)
    purpose = Column(Text, nullable=True)
    domains = Column(ARRAY(String), default=list)
    role_mask = Column(BigInteger, default=0)  # 64-bit bitmask for access control
    max_tokens = Column(Integer, default=4000)
    freshness_req = Column(String(20), default="24h")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class AccessLog(Base):
    """Audit trail — every context delivery is logged."""

    __tablename__ = "access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    query = Column(Text, nullable=True)
    decision = Column(String(20), nullable=False)  # "granted" | "denied" | "filtered"
    atoms_served = Column(Integer, default=0)
    atoms_filtered = Column(Integer, default=0)
    cache_tier = Column(String(10), nullable=True)  # "L2" | "L3"
    latency_ms = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_access_logs_agent", "agent_id"),
        Index("ix_access_logs_timestamp", "timestamp"),
    )
