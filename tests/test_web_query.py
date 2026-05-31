"""Tests for S7 (chat endpoint) and S9 (SSE streaming)."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from lattice.web.app import app

client = TestClient(app)

_MOCK_ATOMS = [
    {"atom_id": "abc123", "subject": "test subject", "kind": "fact", "content": "some content"},
]
_MOCK_ANSWER = "This is a synthesized answer."


def _mock_stream(answer: str = _MOCK_ANSWER, atoms: list | None = None):
    """Return a generator that yields the canonical SSE event sequence."""
    def _gen():
        yield f'data: {json.dumps({"type": "token", "text": answer})}\n\n'
        yield 'data: {"type": "done"}\n\n'
    return _gen()


def _parse_sse(body: str) -> list[dict]:
    events = []
    for chunk in body.split("\n\n"):
        chunk = chunk.strip()
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


def _patches(stream_gen=None):
    if stream_gen is None:
        stream_gen = _mock_stream()
    return (
        patch("lattice.web.app.select", return_value=_MOCK_ATOMS),
        patch("lattice.web.app.stream_synthesis", return_value=stream_gen),
        patch("lattice.web.app.LatticeDB", return_value=MagicMock()),
    )


# ---------------------------------------------------------------------------
# S7: endpoint contract (preserved — now SSE instead of JSON)
# ---------------------------------------------------------------------------

def test_api_query_returns_200():
    with _patches()[0], _patches()[1], _patches()[2]:
        with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
             patch("lattice.web.app.stream_synthesis", return_value=_mock_stream()), \
             patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
            resp = client.post("/api/query", json={"question": "test"})
    assert resp.status_code == 200


def test_api_query_content_type_is_event_stream():
    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_mock_stream()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "test"})
    assert "text/event-stream" in resp.headers["content-type"]


def test_api_query_atoms_event_present():
    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_mock_stream()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "test"})
    events = _parse_sse(resp.text)
    atoms_events = [e for e in events if e.get("type") == "atoms"]
    assert len(atoms_events) == 1
    assert atoms_events[0]["atoms"] == _MOCK_ATOMS


def test_api_query_empty_body_returns_422():
    resp = client.post("/api/query", json={})
    assert resp.status_code == 422


def test_index_returns_html_with_form_or_input():
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<form" in resp.text or "<input" in resp.text


# ---------------------------------------------------------------------------
# S9: streaming — token events, done event, error event
# ---------------------------------------------------------------------------

def test_stream_contains_token_events():
    def _gen():
        yield 'data: {"type": "token", "text": "Hello"}\n\n'
        yield 'data: {"type": "token", "text": " world"}\n\n'
        yield 'data: {"type": "done"}\n\n'

    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_gen()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "hi"})

    events = _parse_sse(resp.text)
    tokens = [e for e in events if e.get("type") == "token"]
    assert len(tokens) == 2
    assert tokens[0]["text"] == "Hello"
    assert tokens[1]["text"] == " world"


def test_stream_ends_with_done_event():
    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_mock_stream()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "hi"})

    events = _parse_sse(resp.text)
    assert events[-1]["type"] == "done"


def test_stream_error_event_visible():
    """Rule 6: error events must reach the client, not be swallowed."""
    def _gen():
        yield 'data: {"type": "error", "message": "Streaming failed: timeout"}\n\n'

    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_gen()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "hi"})

    events = _parse_sse(resp.text)
    error_events = [e for e in events if e.get("type") == "error"]
    assert len(error_events) == 1
    assert "timeout" in error_events[0]["message"]


def test_full_answer_reconstructed_from_tokens():
    words = ["The", " answer", " is", " 42."]

    def _gen():
        for w in words:
            yield f'data: {json.dumps({"type": "token", "text": w})}\n\n'
        yield 'data: {"type": "done"}\n\n'

    with patch("lattice.web.app.select", return_value=_MOCK_ATOMS), \
         patch("lattice.web.app.stream_synthesis", return_value=_gen()), \
         patch("lattice.web.app.LatticeDB", return_value=MagicMock()):
        resp = client.post("/api/query", json={"question": "what is the answer?"})

    events = _parse_sse(resp.text)
    answer = "".join(e["text"] for e in events if e.get("type") == "token")
    assert answer == "The answer is 42."
