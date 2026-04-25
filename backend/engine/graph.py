"""Graph operations — store, query, and traverse the knowledge graph."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.embeddings import embed_text, embed_texts
from backend.engine.extraction import extract_from_chunks, ExtractedEntity, ExtractedRelationship
from backend.models.graph import Entity, Relationship


async def ingest_to_graph(
    db: AsyncSession,
    chunks_text: list[str],
    source_id: uuid.UUID,
    chunk_ids: list[uuid.UUID] | None = None,
) -> dict:
    """
    Extract entities and relationships from chunks and store in the graph.

    Returns summary of what was extracted.
    """
    # Extract
    result = extract_from_chunks(chunks_text)

    if not result.entities:
        return {"entities_created": 0, "relationships_created": 0}

    # Embed entity names for semantic search
    entity_names = [e.name for e in result.entities]
    entity_embeddings = embed_texts(entity_names)

    # Resolve or create entities (dedup against existing)
    entity_map: dict[str, uuid.UUID] = {}  # "type:name_lower" -> entity id
    entities_created = 0

    for extracted, embedding in zip(result.entities, entity_embeddings):
        key = f"{extracted.entity_type}:{extracted.name.lower()}"

        # Check if entity already exists
        existing = await db.execute(
            select(Entity).where(
                func.lower(Entity.name) == extracted.name.lower(),
                Entity.entity_type == extracted.entity_type,
            )
        )
        entity = existing.scalar_one_or_none()

        if entity:
            # Update existing — merge properties, bump mention count
            if extracted.properties:
                current_props = entity.properties or {}
                current_props.update(extracted.properties)
                entity.properties = current_props
            entity.mention_count = (entity.mention_count or 1) + 1
            entity.last_seen_at = datetime.now(timezone.utc)
            entity_map[key] = entity.id
        else:
            # Create new entity
            chunk_id = chunk_ids[0] if chunk_ids else None
            entity = Entity(
                id=uuid.uuid4(),
                name=extracted.name,
                entity_type=extracted.entity_type,
                properties=extracted.properties or {},
                embedding=embedding,
                source_id=source_id,
                chunk_id=chunk_id,
                mention_count=1,
            )
            db.add(entity)
            entity_map[key] = entity.id
            entities_created += 1

    await db.flush()  # Get IDs assigned

    # Create relationships
    relationships_created = 0
    for rel in result.relationships:
        from_key = _find_entity_key(rel.from_entity, result.entities)
        to_key = _find_entity_key(rel.to_entity, result.entities)

        if from_key not in entity_map or to_key not in entity_map:
            continue

        from_id = entity_map[from_key]
        to_id = entity_map[to_key]

        # Check if relationship already exists
        existing_rel = await db.execute(
            select(Relationship).where(
                Relationship.from_entity_id == from_id,
                Relationship.to_entity_id == to_id,
                Relationship.relationship_type == rel.relationship_type,
            )
        )
        existing = existing_rel.scalar_one_or_none()

        if existing:
            # Strengthen weight on repeated mention
            existing.weight = (existing.weight or 1.0) + 0.5
        else:
            relationship = Relationship(
                id=uuid.uuid4(),
                from_entity_id=from_id,
                to_entity_id=to_id,
                relationship_type=rel.relationship_type,
                properties=rel.properties or {},
                weight=1.0,
                source_id=source_id,
            )
            db.add(relationship)
            relationships_created += 1

    return {
        "entities_created": entities_created,
        "entities_updated": len(result.entities) - entities_created,
        "relationships_created": relationships_created,
        "total_entities": len(result.entities),
        "total_relationships": len(result.relationships),
    }


def _find_entity_key(name: str, entities: list[ExtractedEntity]) -> str:
    """Find the entity key (type:name_lower) for a name."""
    name_lower = name.lower()
    for e in entities:
        if e.name.lower() == name_lower:
            return f"{e.entity_type}:{name_lower}"
    # Fallback — try as concept
    return f"concept:{name_lower}"


async def get_entity_neighborhood(
    db: AsyncSession,
    entity_id: uuid.UUID,
    depth: int = 1,
) -> dict:
    """
    Get an entity and its neighborhood (connected entities up to N hops).

    Returns the entity, its direct relationships, and connected entities.
    """
    # Get the root entity
    result = await db.execute(select(Entity).where(Entity.id == entity_id))
    entity = result.scalar_one_or_none()
    if not entity:
        return {"entity": None, "relationships": [], "connected_entities": []}

    # Get outgoing relationships
    out_result = await db.execute(
        select(Relationship, Entity)
        .join(Entity, Relationship.to_entity_id == Entity.id)
        .where(Relationship.from_entity_id == entity_id)
        .order_by(Relationship.weight.desc())
    )
    outgoing = out_result.fetchall()

    # Get incoming relationships
    in_result = await db.execute(
        select(Relationship, Entity)
        .join(Entity, Relationship.from_entity_id == Entity.id)
        .where(Relationship.to_entity_id == entity_id)
        .order_by(Relationship.weight.desc())
    )
    incoming = in_result.fetchall()

    relationships = []
    connected_entities = {}

    for rel, connected in outgoing:
        relationships.append({
            "id": str(rel.id),
            "from_entity_id": str(rel.from_entity_id),
            "to_entity_id": str(rel.to_entity_id),
            "type": rel.relationship_type,
            "weight": rel.weight,
            "direction": "outgoing",
            "properties": rel.properties,
        })
        connected_entities[str(connected.id)] = {
            "id": str(connected.id),
            "name": connected.name,
            "type": connected.entity_type,
            "properties": connected.properties,
            "mention_count": connected.mention_count,
        }

    for rel, connected in incoming:
        relationships.append({
            "id": str(rel.id),
            "from_entity_id": str(rel.from_entity_id),
            "to_entity_id": str(rel.to_entity_id),
            "type": rel.relationship_type,
            "weight": rel.weight,
            "direction": "incoming",
            "properties": rel.properties,
        })
        connected_entities[str(connected.id)] = {
            "id": str(connected.id),
            "name": connected.name,
            "type": connected.entity_type,
            "properties": connected.properties,
            "mention_count": connected.mention_count,
        }

    return {
        "entity": {
            "id": str(entity.id),
            "name": entity.name,
            "type": entity.entity_type,
            "properties": entity.properties,
            "mention_count": entity.mention_count,
            "source_id": str(entity.source_id) if entity.source_id else None,
        },
        "relationships": relationships,
        "connected_entities": list(connected_entities.values()),
    }


async def search_entities(
    db: AsyncSession,
    query: str,
    entity_type: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Search entities by semantic similarity to the query."""
    query_embedding = embed_text(query)

    stmt = (
        select(
            Entity.id,
            Entity.name,
            Entity.entity_type,
            Entity.properties,
            Entity.mention_count,
            Entity.source_id,
            Entity.embedding.cosine_distance(query_embedding).label("distance"),
        )
        .order_by("distance")
        .limit(limit)
    )

    if entity_type:
        stmt = stmt.where(Entity.entity_type == entity_type)

    result = await db.execute(stmt)
    rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "name": row.name,
            "type": row.entity_type,
            "properties": row.properties,
            "mention_count": row.mention_count,
            "source_id": str(row.source_id) if row.source_id else None,
            "relevance_score": round(1 - row.distance, 4),
        }
        for row in rows
    ]


async def get_graph_stats(db: AsyncSession) -> dict:
    """Get high-level stats about the knowledge graph."""
    entity_count = await db.execute(select(func.count(Entity.id)))
    rel_count = await db.execute(select(func.count(Relationship.id)))

    # Count by type
    type_counts = await db.execute(
        select(Entity.entity_type, func.count(Entity.id))
        .group_by(Entity.entity_type)
    )

    rel_type_counts = await db.execute(
        select(Relationship.relationship_type, func.count(Relationship.id))
        .group_by(Relationship.relationship_type)
    )

    return {
        "total_entities": entity_count.scalar(),
        "total_relationships": rel_count.scalar(),
        "entities_by_type": {row[0]: row[1] for row in type_counts.fetchall()},
        "relationships_by_type": {row[0]: row[1] for row in rel_type_counts.fetchall()},
    }
