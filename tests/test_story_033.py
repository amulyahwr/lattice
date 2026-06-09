"""Tests for STORY-033 — PII round-trip redaction."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from lattice.config import Config
from lattice.privacy import EntityRedactor, is_active


def _cfg(**kwargs) -> Config:
    return Config(**kwargs)


_OLLAMA = _cfg(llm_provider="ollama", pii_scrub=True)
_CLOUD  = _cfg(llm_provider="openai", pii_scrub=True)
_DISABLED = _cfg(llm_provider="openai", pii_scrub=False)


# ── is_active ─────────────────────────────────────────────────────────────────

def test_inactive_on_ollama():
    assert not is_active(_OLLAMA)


def test_inactive_when_scrub_disabled():
    assert not is_active(_DISABLED)


def test_active_on_cloud_provider():
    assert is_active(_CLOUD)


# ── EntityRedactor (no-op when inactive) ─────────────────────────────────────

def test_redact_noop_when_inactive():
    """When PII scrub is inactive, redact_batch returns originals unchanged."""
    redactor = EntityRedactor()
    texts = ["Alice has email alice@example.com", "Bob works at Acme Corp"]
    redacted, entity_map = redactor.redact_batch(texts, _OLLAMA)
    assert redacted == texts
    assert entity_map == {}


def test_restore_noop_on_empty_map():
    redactor = EntityRedactor()
    text = "John Smith called."
    assert redactor.restore(text, {}) == text


# ── regex-only redaction ──────────────────────────────────────────────────────

_REGEX_CFG = _cfg(llm_provider="openai", pii_scrub=True, ner_model="")


def test_email_redacted():
    redactor = EntityRedactor()
    text = "Contact me at john.doe@example.com for details."
    redacted, entity_map = redactor.redact(text, _REGEX_CFG)
    assert "john.doe@example.com" not in redacted
    assert any(k.startswith("EMAIL_") for k in entity_map)
    restored = redactor.restore(redacted, entity_map)
    assert "john.doe@example.com" in restored


def test_phone_redacted():
    redactor = EntityRedactor()
    text = "Call me at 415-555-1234 anytime."
    redacted, entity_map = redactor.redact(text, _REGEX_CFG)
    assert "415-555-1234" not in redacted
    assert any(k.startswith("PHONE_") for k in entity_map)
    restored = redactor.restore(redacted, entity_map)
    assert "415-555-1234" in restored


def test_no_pii_returns_empty_map():
    redactor = EntityRedactor()
    text = "User prefers hiking over cycling."
    redacted, entity_map = redactor.redact(text, _REGEX_CFG)
    assert entity_map == {}
    assert redacted == text


# ── batch redaction ───────────────────────────────────────────────────────────

def test_batch_shared_entity_map():
    """Same email across multiple texts gets same tag."""
    redactor = EntityRedactor()
    texts = [
        "First email: alice@corp.com",
        "Second mention: alice@corp.com for follow-up",
    ]
    redacted, entity_map = redactor.redact_batch(texts, _REGEX_CFG)
    assert redacted[0].count("EMAIL_0") == 1
    assert redacted[1].count("EMAIL_0") == 1
    assert sum(1 for k in entity_map if k.startswith("EMAIL_")) == 1


def test_round_trip_multiple_entities():
    """Redact then restore returns original text."""
    redactor = EntityRedactor()
    texts = [
        "Contact alice@example.com or call 212-555-9876.",
        "Bob at bob@example.org handles billing.",
    ]
    redacted, entity_map = redactor.redact_batch(texts, _REGEX_CFG)
    restored = [redactor.restore(t, entity_map) for t in redacted]
    assert restored[0] == texts[0]
    assert restored[1] == texts[1]


# ── date not redacted ─────────────────────────────────────────────────────────

def test_date_not_redacted():
    """DATE values must never be redacted — would break temporal reasoning."""
    redactor = EntityRedactor()
    text = "Event on 2024-03-15. Contact joe@corp.com."
    redacted, entity_map = redactor.redact(text, _REGEX_CFG)
    assert "2024-03-15" in redacted
