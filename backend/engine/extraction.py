"""Entity and relationship extraction from text.

Extracts structured knowledge (entities + relationships) from unstructured text.
Uses rule-based + regex patterns. No external LLM dependency for the base layer.

Entity types: person, org, date, metric, location, project, concept
Relationship types: has_value, has_role, part_of, references, occurred_on, located_in, reported_by
"""

import re
from dataclasses import dataclass, field


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    name: str
    entity_type: str  # person, org, date, metric, location, project, concept
    properties: dict = field(default_factory=dict)
    span: tuple[int, int] | None = None  # character offset in source text


@dataclass
class ExtractedRelationship:
    """A relationship between two extracted entities."""
    from_entity: str  # entity name
    to_entity: str  # entity name
    relationship_type: str
    properties: dict = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Complete extraction result from a chunk of text."""
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]


# ── Patterns ──

# Money: $12M, $1.5 billion, €500K, etc.
MONEY_PATTERN = re.compile(
    r'[\$€£¥][\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion|[MBKTmkbt]))?'
    r'|[\d,]+(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:dollars|euros|pounds)?',
    re.IGNORECASE,
)

# Percentages: 15%, 2.5 percent
PERCENT_PATTERN = re.compile(
    r'[\d,]+(?:\.\d+)?(?:\s*%|\s+percent)',
    re.IGNORECASE,
)

# Dates: January 2026, Q3 2025, Oct 3rd, 2026-01-15, FY2025
DATE_PATTERN = re.compile(
    r'(?:Q[1-4]\s*\d{4})'
    r'|(?:FY\s*\d{4})'
    r'|(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}?)'
    r'|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
    r'\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}?)'
    r'|\d{4}[-/]\d{2}[-/]\d{2}',
    re.IGNORECASE,
)

# Email addresses
EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')

# Capitalized phrases (potential names, orgs, projects) — 2-4 consecutive capitalized words
PROPER_NOUN_PATTERN = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b')

# Role patterns: CEO, CFO, CTO, VP of X, Director of X, Head of X
ROLE_PATTERN = re.compile(
    r'\b(CEO|CFO|CTO|COO|CIO|CISO|VP|SVP|EVP|Director|Head|Manager|Lead|President|Chairman|Partner)'
    r'(?:\s+of\s+[A-Za-z\s]+?(?=,|\.|;|\band\b|\n|$))?',
    re.IGNORECASE,
)

# Common org suffixes
ORG_PATTERN = re.compile(
    r'\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*'
    r'\s+(?:Inc|Corp|Ltd|LLC|GmbH|Co|Group|Foundation|Institute|Association|Partners|Capital|Ventures)\b\.?',
)

# Project references: Project X, Operation X
PROJECT_PATTERN = re.compile(
    r'\b(?:Project|Operation|Initiative|Program)\s+[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)?',
    re.IGNORECASE,
)


def extract_from_text(text: str) -> ExtractionResult:
    """
    Extract entities and relationships from a chunk of text.

    Returns entities and relationships found via pattern matching.
    """
    entities: dict[str, ExtractedEntity] = {}  # name -> entity (deduped)
    relationships: list[ExtractedRelationship] = []

    def add_entity(name: str, entity_type: str, properties: dict | None = None, span: tuple | None = None):
        name = name.strip()
        if len(name) < 2 or len(name) > 200:
            return
        key = f"{entity_type}:{name.lower()}"
        if key not in entities:
            entities[key] = ExtractedEntity(
                name=name,
                entity_type=entity_type,
                properties=properties or {},
                span=span,
            )
        elif properties:
            entities[key].properties.update(properties)

    # ── Extract metrics (money) ──
    for match in MONEY_PATTERN.finditer(text):
        value = match.group().strip()
        add_entity(value, "metric", {"metric_type": "monetary"}, (match.start(), match.end()))

    # ── Extract percentages ──
    for match in PERCENT_PATTERN.finditer(text):
        value = match.group().strip()
        add_entity(value, "metric", {"metric_type": "percentage"}, (match.start(), match.end()))

    # ── Extract dates ──
    for match in DATE_PATTERN.finditer(text):
        value = match.group().strip()
        add_entity(value, "date", {}, (match.start(), match.end()))

    # ── Extract emails ──
    for match in EMAIL_PATTERN.finditer(text):
        email = match.group()
        add_entity(email, "person", {"email": email}, (match.start(), match.end()))

    # ── Extract organizations ──
    for match in ORG_PATTERN.finditer(text):
        org = match.group().strip().rstrip(".")
        add_entity(org, "org", {}, (match.start(), match.end()))

    # ── Extract projects ──
    for match in PROJECT_PATTERN.finditer(text):
        project = match.group().strip()
        add_entity(project, "project", {}, (match.start(), match.end()))

    # ── Extract proper nouns (potential people, orgs, concepts) ──
    # Skip common false positives
    skip_words = {
        "The", "This", "That", "These", "Those", "There", "Their", "They",
        "What", "When", "Where", "Which", "While", "With", "About", "After",
        "Before", "Between", "During", "Under", "Over", "Into", "Through",
        "However", "Therefore", "Furthermore", "Moreover", "Although",
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    }
    for match in PROPER_NOUN_PATTERN.finditer(text):
        name = match.group().strip()
        first_word = name.split()[0]
        if first_word in skip_words:
            continue
        # Heuristic: if it looks like a person name (2-3 words, no org suffix)
        words = name.split()
        if len(words) <= 3 and not any(w in name for w in ["Inc", "Corp", "Ltd", "LLC"]):
            add_entity(name, "person", {}, (match.start(), match.end()))

    # ── Extract role-person relationships ──
    for match in ROLE_PATTERN.finditer(text):
        role = match.group().strip()
        start = match.start()

        # Look for a person name near this role (within ~50 chars before or after)
        context_before = text[max(0, start - 60):start]
        context_after = text[match.end():match.end() + 60]

        person_match = PROPER_NOUN_PATTERN.search(context_before)
        if not person_match:
            person_match = PROPER_NOUN_PATTERN.search(context_after)

        if person_match:
            person_name = person_match.group().strip()
            first_word = person_name.split()[0]
            if first_word not in skip_words:
                add_entity(person_name, "person", {"role": role})
                relationships.append(ExtractedRelationship(
                    from_entity=person_name,
                    to_entity=role,
                    relationship_type="has_role",
                    properties={"context": text[max(0, start - 30):match.end() + 30].strip()},
                ))

    # ── Extract value relationships ──
    # Look for patterns like "revenue was $12M" or "growth of 15%"
    sentences = re.split(r'[.!?;\n]', text)
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        metrics_in_sentence = []
        for match in MONEY_PATTERN.finditer(sentence):
            metrics_in_sentence.append(("monetary", match.group().strip()))
        for match in PERCENT_PATTERN.finditer(sentence):
            metrics_in_sentence.append(("percentage", match.group().strip()))

        if metrics_in_sentence:
            # Find a concept this metric relates to
            concepts = PROPER_NOUN_PATTERN.findall(sentence)
            concepts = [c for c in concepts if c.split()[0] not in skip_words]

            for metric_type, metric_value in metrics_in_sentence:
                for concept in concepts[:1]:  # link to first concept found
                    relationships.append(ExtractedRelationship(
                        from_entity=concept,
                        to_entity=metric_value,
                        relationship_type="has_value",
                        properties={"context": sentence[:200]},
                    ))

        # Date relationships — link dates to nearby entities
        dates_in_sentence = DATE_PATTERN.findall(sentence)
        if dates_in_sentence:
            concepts = PROPER_NOUN_PATTERN.findall(sentence)
            concepts = [c for c in concepts if c.split()[0] not in skip_words]
            for date_val in dates_in_sentence:
                for concept in concepts[:1]:
                    relationships.append(ExtractedRelationship(
                        from_entity=concept,
                        to_entity=date_val.strip(),
                        relationship_type="occurred_on",
                        properties={"context": sentence[:200]},
                    ))

    return ExtractionResult(
        entities=list(entities.values()),
        relationships=relationships,
    )


def extract_from_chunks(chunks_text: list[str]) -> ExtractionResult:
    """Extract entities and relationships from multiple chunks, deduplicating."""
    all_entities: dict[str, ExtractedEntity] = {}
    all_relationships: list[ExtractedRelationship] = []

    for text in chunks_text:
        result = extract_from_text(text)

        for entity in result.entities:
            key = f"{entity.entity_type}:{entity.name.lower()}"
            if key in all_entities:
                # Merge properties
                all_entities[key].properties.update(entity.properties)
            else:
                all_entities[key] = entity

        all_relationships.extend(result.relationships)

    # Deduplicate relationships
    seen_rels = set()
    unique_rels = []
    for rel in all_relationships:
        key = f"{rel.from_entity.lower()}|{rel.relationship_type}|{rel.to_entity.lower()}"
        if key not in seen_rels:
            seen_rels.add(key)
            unique_rels.append(rel)

    return ExtractionResult(
        entities=list(all_entities.values()),
        relationships=unique_rels,
    )
