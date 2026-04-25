"""Atomizer — break raw text into atomic facts.

Evolved from engine/extraction.py. Uses sentence splitting + regex entity
extraction to produce typed atoms (fact, decision, metric, relationship,
event, procedure).
"""

import re
from dataclasses import dataclass, field


@dataclass
class RawAtom:
    """A raw atom before distillation and embedding."""

    content: str
    kind: str = "fact"  # fact | decision | metric | relationship | event | procedure
    entities: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)


# ── Patterns (carried from extraction.py) ──

MONEY_PATTERN = re.compile(
    r"[\$€£¥][\d,]+(?:\.\d+)?(?:\s*(?:million|billion|trillion|[MBKTmkbt]))?"
    r"|[\d,]+(?:\.\d+)?\s*(?:million|billion|trillion)\s*(?:dollars|euros|pounds)?",
    re.IGNORECASE,
)

PERCENT_PATTERN = re.compile(
    r"[\d,]+(?:\.\d+)?(?:\s*%|\s+percent)",
    re.IGNORECASE,
)

DATE_PATTERN = re.compile(
    r"(?:Q[1-4]\s*\d{4})"
    r"|(?:FY\s*\d{4})"
    r"|(?:(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}?)"
    r"|(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s*\d{4}?)"
    r"|\d{4}[-/]\d{2}[-/]\d{2}",
    re.IGNORECASE,
)

DECISION_MARKERS = re.compile(
    r"\b(?:decided|approved|agreed|resolved|concluded|determined|chose|selected|adopted)\b",
    re.IGNORECASE,
)

EVENT_MARKERS = re.compile(
    r"\b(?:launched|released|announced|completed|started|finished|occurred|happened|held)\b",
    re.IGNORECASE,
)

PROCEDURE_MARKERS = re.compile(
    r"\b(?:step\s+\d|procedure|process|workflow|how\s+to|instructions|guide|follow)\b",
    re.IGNORECASE,
)

RELATIONSHIP_MARKERS = re.compile(
    r"\b(?:reports?\s+to|manages?|leads?|works?\s+with|part\s+of|belongs?\s+to|owns?|responsible\s+for)\b",
    re.IGNORECASE,
)


def _classify_sentence(sentence: str) -> str:
    """Classify a sentence into an atom kind."""
    if MONEY_PATTERN.search(sentence) or PERCENT_PATTERN.search(sentence):
        return "metric"
    if DECISION_MARKERS.search(sentence):
        return "decision"
    if EVENT_MARKERS.search(sentence):
        return "event"
    if PROCEDURE_MARKERS.search(sentence):
        return "procedure"
    if RELATIONSHIP_MARKERS.search(sentence):
        return "relationship"
    return "fact"


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, merging very short ones."""
    raw_sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    sentences: list[str] = []
    buffer = ""

    for s in raw_sentences:
        s = s.strip()
        if not s:
            continue
        if len(s) < 40 and buffer:
            buffer += " " + s
        elif buffer and len(buffer) < 40:
            buffer += " " + s
        else:
            if buffer:
                sentences.append(buffer.strip())
            buffer = s

    if buffer:
        sentences.append(buffer.strip())

    return sentences


def _extract_entities(text: str) -> list[str]:
    """Extract entity names from text using regex patterns."""
    entities: list[str] = []

    # Proper nouns (capitalized phrases, 2-4 words)
    skip_words = {
        "The", "This", "That", "These", "Those", "There", "Their", "They",
        "What", "When", "Where", "Which", "While", "With", "About", "After",
        "Before", "Between", "During", "Under", "Over", "Into", "Through",
        "However", "Therefore", "Furthermore", "Moreover", "Although",
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    }
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text):
        name = match.group().strip()
        if name.split()[0] not in skip_words:
            entities.append(name)

    # Organizations
    for match in re.finditer(
        r"\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*"
        r"\s+(?:Inc|Corp|Ltd|LLC|GmbH|Co|Group|Foundation|Institute|Association|Partners|Capital|Ventures)\b\.?",
        text,
    ):
        entities.append(match.group().strip().rstrip("."))

    return list(set(entities))


def atomize(text: str) -> list[RawAtom]:
    """Break raw text into atomic facts.

    Each sentence becomes an atom, classified by kind.
    Very short or meaningless fragments are dropped.
    """
    sentences = _split_sentences(text)
    atoms: list[RawAtom] = []

    for sentence in sentences:
        # Skip very short or meaningless text
        if len(sentence.split()) < 3:
            continue

        kind = _classify_sentence(sentence)
        entities = _extract_entities(sentence)

        atoms.append(
            RawAtom(
                content=sentence,
                kind=kind,
                entities=entities,
            )
        )

    return atoms


def atomize_chunks(chunks_text: list[str]) -> list[RawAtom]:
    """Atomize multiple text chunks, deduplicating by content."""
    seen: set[str] = set()
    all_atoms: list[RawAtom] = []

    for text in chunks_text:
        atoms = atomize(text)
        for atom in atoms:
            key = atom.content.lower().strip()
            if key not in seen:
                seen.add(key)
                all_atoms.append(atom)

    return all_atoms
