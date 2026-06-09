"""S9: unit tests for stream_synthesis() in lattice/synthesis.py."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from lattice.config import Config
from lattice.synthesis import stream_synthesis

_CFG = Config(llm_provider="ollama", llm_model="test-model")


def _parse_events(gen) -> list[dict]:
    events = []
    for chunk in gen:
        chunk = chunk.strip()
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:]))
    return events


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


def _mock_client(stream_texts: list[str], tool_resp_content: str = "Final answer.") -> MagicMock:
    mock_llm = MagicMock()
    tool_resp = _make_tool_resp(tool_resp_content)
    stream_chunks = [_make_stream_chunk(t) for t in stream_texts]
    mock_llm.create.side_effect = [tool_resp, iter(stream_chunks)]
    return mock_llm


# ---------------------------------------------------------------------------

def test_empty_atoms_yields_no_info():
    events = _parse_events(stream_synthesis("q", [], _CFG))
    assert events[0]["type"] == "token"
    assert "No relevant information" in events[0]["text"]
    assert events[-1]["type"] == "done"


def test_tokens_streamed_in_order():
    atoms = [{"subject": "s", "kind": "fact", "content": "c", "source": "doc"}]
    client = _mock_client(["Hello", " world"])

    with patch("lattice.synthesis.LLMClient", return_value=client):
        events = _parse_events(stream_synthesis("q", atoms, _CFG))

    tokens = [e for e in events if e["type"] == "token"]
    assert [t["text"] for t in tokens] == ["Hello", " world"]


def test_done_event_always_last():
    atoms = [{"subject": "s", "kind": "fact", "content": "c", "source": "doc"}]
    client = _mock_client(["ok"])

    with patch("lattice.synthesis.LLMClient", return_value=client):
        events = _parse_events(stream_synthesis("q", atoms, _CFG))

    assert events[-1]["type"] == "done"


def test_provider_error_yields_error_event():
    """Rule 6: EnvironmentError from make_llm_client must surface as error event."""
    atoms = [{"subject": "s", "kind": "fact", "content": "c", "source": "doc"}]

    with patch("lattice.synthesis.LLMClient", side_effect=EnvironmentError("unsupported provider")):
        events = _parse_events(stream_synthesis("q", atoms, _CFG))

    assert events[0]["type"] == "error"
    assert "unsupported provider" in events[0]["message"]


def test_streaming_exception_yields_error_event():
    """Rule 6: streaming failure must surface as error event, not silent truncation."""
    atoms = [{"subject": "s", "kind": "fact", "content": "c", "source": "doc"}]
    client = MagicMock()
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = "ready"
    tool_resp = MagicMock()
    tool_resp.choices = [SimpleNamespace(message=msg)]
    client.create.side_effect = [tool_resp, RuntimeError("network timeout")]

    with patch("lattice.synthesis.LLMClient", return_value=client):
        events = _parse_events(stream_synthesis("q", atoms, _CFG))

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert "network timeout" in error_events[0]["message"]


def test_no_token_events_for_empty_delta():
    """Chunks with empty/None delta.content must not emit token events."""
    atoms = [{"subject": "s", "kind": "fact", "content": "c", "source": "doc"}]
    client = MagicMock()
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = "ready"
    tool_resp = MagicMock()
    tool_resp.choices = [SimpleNamespace(message=msg)]
    empty_chunk = _make_stream_chunk("")
    real_chunk = _make_stream_chunk("answer")
    client.create.side_effect = [tool_resp, iter([empty_chunk, real_chunk])]

    with patch("lattice.synthesis.LLMClient", return_value=client):
        events = _parse_events(stream_synthesis("q", atoms, _CFG))

    tokens = [e for e in events if e["type"] == "token"]
    assert len(tokens) == 1
    assert tokens[0]["text"] == "answer"
