"""SQLAlchemy models for Lattice."""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from backend.config import settings
from backend.models.database import Base


class Source(Base):
    """A data source with its DNA — identity, classification, and semantic profile."""

    __tablename__ = "sources"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)  # "pdf", "postgres", etc.

    # Source DNA
    summary = Column(Text, nullable=True)
    summary_embedding = Column(Vector(settings.embedding_dim), nullable=True)
    classification = Column(String(50), default="internal")  # public | internal | confidential | restricted
    domains = Column(ARRAY(String), default=list)
    owner = Column(String(255), nullable=True)
    org_scope = Column(ARRAY(String), default=list)

    metadata_ = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    chunks = relationship("Chunk", back_populates="source", cascade="all, delete-orphan")


class Chunk(Base):
    """A chunk of content with its embedding."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    embedding = Column(Vector(settings.embedding_dim))
    metadata_ = Column("metadata", Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    source = relationship("Source", back_populates="chunks")


class Agent(Base):
    """An agent with its identity profile — purpose, clearance, and scope."""

    __tablename__ = "agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, unique=True)
    api_key = Column(String(255), nullable=False, unique=True)

    # Agent Identity Profile
    purpose = Column(Text, nullable=True)
    purpose_embedding = Column(Vector(settings.embedding_dim), nullable=True)
    deployed_by = Column(String(255), nullable=True)
    clearance = Column(String(50), default="internal")  # public | internal | confidential | restricted
    domains = Column(ARRAY(String), default=list)
    org_scope = Column(ARRAY(String), default=list)
    auto_grant_threshold = Column(Float, default=0.75)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    permissions = relationship("AgentPermission", back_populates="agent", cascade="all, delete-orphan")


class AgentPermission(Base):
    """Manual override — explicit grant or deny for an agent-source pair."""

    __tablename__ = "agent_permissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    permission_type = Column(String(10), default="grant")  # "grant" | "deny"

    agent = relationship("Agent", back_populates="permissions")
    source = relationship("Source")


class AccessLog(Base):
    """Audit trail — every access decision logged."""

    __tablename__ = "access_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False)
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=False)
    query = Column(Text, nullable=True)
    decision = Column(String(20), nullable=False)  # "granted" | "denied" | "irrelevant"
    reason = Column(Text, nullable=True)
    relevance_score = Column(Float, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    agent = relationship("Agent")
    source = relationship("Source")
