"""End-to-end smoke test: ingest → _retrieve → select → stream_synthesis.

All LLM calls are mocked. No daemon, no network, no real model required.
Verifies the full pipeline wiring after the litellm→openai refactor.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lattice.db import LatticeDB
from lattice.ingest import ingest
from lattice.selection import _retrieve, select
from lattice.synthesis import stream_synthesis


# ── LLM mock helpers ──────────────────────────────────────────────────────────

def _ingest_response(atoms: list[dict]) -> str:
    return json.dumps({"atoms": atoms})


def _supersession_null() -> str:
    return json.dumps({"superseded_atom_id": None})


def _make_stream_chunk(text: str) -> SimpleNamespace:
    delta = SimpleNamespace(content=text)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


def _make_tool_resp(content: str) -> MagicMock:
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = content
    resp = MagicMock()
    resp.choices = [SimpleNamespace(message=msg)]
    return resp


def _mock_synthesis_client(answer: str) -> MagicMock:
    client = MagicMock()
    tool_resp = _make_tool_resp(answer)
    stream_chunks = [_make_stream_chunk(w + " ") for w in answer.split()]
    client.chat.completions.create.side_effect = [tool_resp, iter(stream_chunks)]
    return client


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def db(tmp_path):
    return LatticeDB(lattice_dir=tmp_path)


@pytest.fixture()
def seeded_db(db):
    """DB with 3 atoms ingested via mocked LLM extraction."""
    sessions = [
        ("I drink dark roast coffee every morning.", "coffee preference", "preference"),
        ("I use Neovim as my primary editor.", "editor preference", "preference"),
        ("I am training for a half-marathon in June.", "fitness goal", "goal"),
    ]
    for text, subject, kind in sessions:
        atoms = [{"subject": subject, "kind": kind, "source": "user",
                  "content": text, "valid_from": None, "valid_until": None}]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(atoms)]):
            ingest(text, db=db)
    return db


# ── tests ─────────────────────────────────────────────────────────────────────

class TestRetrieve:
    def test_retrieve_returns_relevant_atoms(self, seeded_db):
        results = _retrieve("coffee", db=seeded_db)
        assert results, "expected at least one result"
        subjects = [r["subject"] for r in results]
        assert any("coffee" in s.lower() for s in subjects)

    def test_retrieve_no_llm_call(self, seeded_db):
        # _retrieve() is LLM-free — verify it returns results without any LLM patch
        results = _retrieve("coffee", db=seeded_db)
        assert results, "expected results without LLM"

    def test_retrieve_result_has_required_keys(self, seeded_db):
        results = _retrieve("editor", db=seeded_db)
        assert results
        required = {"atom_id", "subject", "kind", "content", "source_id", "observed_at"}
        assert required.issubset(results[0].keys())

    def test_retrieve_empty_db(self, db):
        assert _retrieve("anything", db=db) == []


class TestSelect:
    def test_select_returns_results(self, seeded_db):
        # select() = _retrieve() — no LLM calls
        results = select("editor", db=seeded_db)
        assert results

    def test_select_empty_db(self, db):
        assert select("anything", db=db) == []

    def test_select_result_shape_matches_retrieve(self, seeded_db):
        # select and _retrieve should return same shape
        r1 = select("coffee", db=seeded_db)
        r2 = _retrieve("coffee", db=seeded_db)
        assert {a["atom_id"] for a in r1} == {a["atom_id"] for a in r2}


class TestStreamSynthesis:
    def test_full_pipeline_produces_tokens(self, seeded_db):
        candidates = _retrieve("coffee", db=seeded_db)
        assert candidates

        client = _mock_synthesis_client("You like dark roast coffee.")
        events = []
        with patch("lattice.synthesis.make_llm_client", return_value=client):
            for chunk in stream_synthesis("What coffee do I like?", candidates):
                chunk = chunk.strip()
                if chunk.startswith("data: "):
                    events.append(json.loads(chunk[6:]))

        token_events = [e for e in events if e["type"] == "token"]
        assert token_events, "expected token events"
        assert events[-1]["type"] == "done"

    def test_full_pipeline_emits_citations_applied(self, seeded_db):
        candidates = _retrieve("coffee", db=seeded_db)
        client = _mock_synthesis_client("You like dark roast coffee.")
        events = []
        with patch("lattice.synthesis.make_llm_client", return_value=client):
            for chunk in stream_synthesis("What coffee do I like?", candidates):
                chunk = chunk.strip()
                if chunk.startswith("data: "):
                    events.append(json.loads(chunk[6:]))

        citation_events = [e for e in events if e["type"] == "citations_applied"]
        assert len(citation_events) == 1
        assert "answer" in citation_events[0]

    def test_ingest_to_synthesis_roundtrip(self, db):
        """Full ingest→retrieve→synthesize with all mocks."""
        raw = "My favourite programming language is Python."
        atoms_payload = [{"subject": "favourite language", "kind": "preference",
                          "source": "user", "content": raw,
                          "valid_from": None, "valid_until": None}]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(atoms_payload)]):
            result = ingest(raw, db=db)
        assert result["atoms_created"] == 1

        retrieved = _retrieve("programming language", db=db)
        assert retrieved

        client = _mock_synthesis_client("Your favourite language is Python.")
        events = []
        with patch("lattice.synthesis.make_llm_client", return_value=client):
            for chunk in stream_synthesis("What is my favourite language?", retrieved):
                chunk = chunk.strip()
                if chunk.startswith("data: "):
                    events.append(json.loads(chunk[6:]))

        assert events[-1]["type"] == "done"
        tokens = "".join(e["text"] for e in events if e["type"] == "token")
        assert tokens.strip()
