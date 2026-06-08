"""Tests for STORY-033 — PII round-trip redaction."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from lattice.privacy import EntityRedactor, is_active


# ── is_active ─────────────────────────────────────────────────────────────────

def test_inactive_on_ollama():
    with patch.dict(os.environ, {"LLM_PROVIDER": "ollama", "LATTICE_PII_SCRUB": "true"}):
        # reimport to pick up env
        import importlib
        import lattice.privacy as priv
        importlib.reload(priv)
        assert not priv.is_active()


def test_inactive_when_scrub_disabled():
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "LATTICE_PII_SCRUB": "false"}):
        import importlib
        import lattice.privacy as priv
        importlib.reload(priv)
        assert not priv.is_active()


def test_active_on_cloud_provider():
    with patch.dict(os.environ, {"LLM_PROVIDER": "openai", "LATTICE_PII_SCRUB": "true"}):
        import importlib
        import lattice.privacy as priv
        importlib.reload(priv)
        assert priv.is_active()


# ── EntityRedactor (no-op when inactive) ─────────────────────────────────────

def test_redact_noop_when_inactive():
    """When PII scrub is inactive, redact_batch returns originals unchanged."""
    redactor = EntityRedactor()
    with patch("lattice.privacy.is_active", return_value=False):
        texts = ["Alice has email alice@example.com", "Bob works at Acme Corp"]
        redacted, entity_map = redactor.redact_batch(texts)
    assert redacted == texts
    assert entity_map == {}


def test_restore_noop_on_empty_map():
    redactor = EntityRedactor()
    text = "John Smith called."
    assert redactor.restore(text, {}) == text


# ── regex-only redaction ──────────────────────────────────────────────────────

def test_email_redacted():
    redactor = EntityRedactor()
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        text = "Contact me at john.doe@example.com for details."
        redacted, entity_map = redactor.redact(text)
    assert "john.doe@example.com" not in redacted
    assert any(k.startswith("EMAIL_") for k in entity_map)
    restored = redactor.restore(redacted, entity_map)
    assert "john.doe@example.com" in restored


def test_phone_redacted():
    redactor = EntityRedactor()
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        text = "Call me at 415-555-1234 anytime."
        redacted, entity_map = redactor.redact(text)
    assert "415-555-1234" not in redacted
    assert any(k.startswith("PHONE_") for k in entity_map)
    restored = redactor.restore(redacted, entity_map)
    assert "415-555-1234" in restored


def test_no_pii_returns_empty_map():
    redactor = EntityRedactor()
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        text = "User prefers hiking over cycling."
        redacted, entity_map = redactor.redact(text)
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
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        redacted, entity_map = redactor.redact_batch(texts)

    # Both texts should have the same EMAIL_0 tag, not EMAIL_0 and EMAIL_1
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
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        redacted, entity_map = redactor.redact_batch(texts)

    restored = [redactor.restore(t, entity_map) for t in redacted]
    assert restored[0] == texts[0]
    assert restored[1] == texts[1]


# ── date not redacted ─────────────────────────────────────────────────────────

def test_date_not_redacted():
    """DATE values must never be redacted — would break temporal reasoning."""
    redactor = EntityRedactor()
    with patch("lattice.privacy.is_active", return_value=True), \
         patch("lattice.privacy._NER_MODEL", ""):
        text = "Event on 2024-03-15. Contact joe@corp.com."
        redacted, entity_map = redactor.redact(text)
    assert "2024-03-15" in redacted
