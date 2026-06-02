"""S10: source citation tests — replace_citations() and streaming citations_applied event."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from starlette.testclient import TestClient

from lattice.synthesis import replace_citations
from lattice.web.app import app

client = TestClient(app)

_ATOMS = [
    {
        "atom_id": "a1",
        "source_id": "src-abc",
        "source_title": "Meeting Notes",
        "subject": "project deadline",
        "kind": "fact",
        "content": "deadline is Q3",
    },
    {
        "atom_id": "a2",
        "source_id": "src-xyz",
        "source_title": None,
        "subject": "team size",
        "kind": "fact",
        "content": "team has 5 people",
    },
]


# ---------------------------------------------------------------------------
# replace_citations unit tests
# ---------------------------------------------------------------------------

def test_replaces_known_source_with_label():
    text = "Deadline is Q3 [src:src-abc]."
    result = replace_citations(text, _ATOMS)
    assert "[Meeting Notes][src:src-abc]" in result


def test_uses_subject_when_no_source_title():
    text = "Team has 5 people [src:src-xyz]."
    result = replace_citations(text, _ATOMS)
    assert "[team size][src:src-xyz]" in result


def test_unknown_source_id_left_intact():
    """Rule 6: unknown citations are never silently dropped."""
    text = "Something [src:unknown-id]."
    result = replace_citations(text, _ATOMS)
    assert "[src:unknown-id]" in result


def test_no_citations_unchanged():
    text = "Plain answer with no citations."
    assert replace_citations(text, _ATOMS) == text


def test_multiple_citations_in_one_text():
    text = "Q3 [src:src-abc] and five people [src:src-xyz]."
    result = replace_citations(text, _ATOMS)
    assert "[Meeting Notes][src:src-abc]" in result
    assert "[team size][src:src-xyz]" in result


def test_empty_atoms_leaves_text_unchanged():
    text = "Answer [src:src-abc]."
    result = replace_citations(text, [])
    assert result == text


def test_already_labelled_format_passthrough():
    """Pre-labelled [label][src:id] format — replace_citations should handle it."""
    text = "See [Meeting Notes][src:src-abc] for details."
    result = replace_citations(text, _ATOMS)
    # Should still resolve — just re-labels with the same title
    assert "src-abc" in result


# ---------------------------------------------------------------------------
# Streaming: citations_applied event
# ---------------------------------------------------------------------------

def _parse_sse(body: str) -> list[dict]:
    events = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def test_stream_emits_citations_applied_event():
    def _gen():
        yield 'data: {"type": "token", "text": "Deadline is Q3 [src:src-abc]."}\n\n'
        yield f'data: {json.dumps({"type": "citations_applied", "answer": "Deadline is Q3 [Meeting Notes][src:src-abc]."})}\n\n'
        yield 'data: {"type": "done"}\n\n'

    with patch("lattice.web.app.select", return_value=_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_gen()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "deadline?"})

    events = _parse_sse(resp.text)
    ca_events = [e for e in events if e.get("type") == "citations_applied"]
    assert len(ca_events) == 1
    assert "[Meeting Notes][src:src-abc]" in ca_events[0]["answer"]


def test_citations_applied_comes_before_done():
    def _gen():
        yield f'data: {json.dumps({"type": "citations_applied", "answer": "done answer"})}\n\n'
        yield 'data: {"type": "done"}\n\n'

    with patch("lattice.web.app.select", return_value=_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_gen()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "q"})

    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types.index("citations_applied") < types.index("done")


def test_index_contains_citation_css():
    resp = client.get("/")
    assert "citation" in resp.text


def test_index_contains_render_citations_js():
    resp = client.get("/static/app.js")
    assert resp.status_code == 200
    assert "renderCitations" in resp.text
