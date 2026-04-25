"""Knowledge Graph models — entities and relationships.

The graph lives in Postgres alongside vector storage.
Entities are the nouns (people, orgs, concepts, metrics, dates).
Relationships are the verbs connecting them (reported_by, references, part_of).
Both link back to their source for provenance and access control.
"""

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from backend.config import settings
from backend.models.database import Base


class Entity(Base):
    """A node in the knowledge graph — a person, org, concept, metric, date, etc."""

    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(512), nullable=False)
    entity_type = Column(String(100), nullable=False)  # person, org, concept, metric, date, location, project, etc.
    properties = Column(JSONB, default=dict)  # flexible key-value metadata
    embedding = Column(Vector(settings.embedding_dim), nullable=True)  # for semantic entity search

    # Provenance
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=True)

    # Evolution tracking
    mention_count = Column(Integer, default=1)  # how many times this entity appears across sources
    last_seen_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Relationships
    source = relationship("Source", foreign_keys=[source_id])
    chunk = relationship("Chunk", foreign_keys=[chunk_id])

    outgoing_relationships = relationship(
        "Relationship",
        foreign_keys="Relationship.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    incoming_relationships = relationship(
        "Relationship",
        foreign_keys="Relationship.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_entities_name", "name"),
        Index("ix_entities_type", "entity_type"),
        Index("ix_entities_source", "source_id"),
        Index("ix_entities_name_type", "name", "entity_type", unique=False),
    )

    def __repr__(self):
        return f"<Entity {self.entity_type}:{self.name}>"


class Relationship(Base):
    """An edge in the knowledge graph — connects two entities."""

    __tablename__ = "relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    to_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    relationship_type = Column(String(100), nullable=False)  # has_value, reported_by, references, part_of, etc.
    properties = Column(JSONB, default=dict)  # flexible metadata (confidence, context snippet, etc.)

    # Weight — strengthened by repeated mentions and positive feedback
    weight = Column(Float, default=1.0)

    # Provenance
    source_id = Column(UUID(as_uuid=True), ForeignKey("sources.id"), nullable=True)
    chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Navigation
    from_entity = relationship("Entity", foreign_keys=[from_entity_id], back_populates="outgoing_relationships")
    to_entity = relationship("Entity", foreign_keys=[to_entity_id], back_populates="incoming_relationships")
    source = relationship("Source", foreign_keys=[source_id])

    __table_args__ = (
        Index("ix_relationships_from", "from_entity_id"),
        Index("ix_relationships_to", "to_entity_id"),
        Index("ix_relationships_type", "relationship_type"),
        Index("ix_relationships_source", "source_id"),
    )

    def __repr__(self):
        return f"<Relationship {self.from_entity_id} -{self.relationship_type}-> {self.to_entity_id}>"
