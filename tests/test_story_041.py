"""STORY-041 — End-to-end query trace tests."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lattice.config import Config
from lattice.trace import QueryTrace, TraceWriter, _sha1


# ── QueryTrace ────────────────────────────────────────────────────────────────

def test_trace_create_hashes_query():
    trace = QueryTrace.create("what is my favourite coffee?")
    assert trace.query_hash == _sha1("what is my favourite coffee?")
    assert trace.channel == "web"
    assert trace.trace_id  # non-empty UUID

def test_trace_reformulated_hash():
    trace = QueryTrace.create("that one")
    trace.set_reformulated("what is my favourite coffee?")
    assert trace.reformulated_hash == _sha1("what is my favourite coffee?")

def test_trace_defaults():
    trace = QueryTrace()
    assert trace.bm25_seeds == []
    assert trace.dense_hits == []
    assert trace.bfs_expanded == []
    assert trace.final_atoms == []
    assert trace.cited_atoms == []
    assert trace.no_answer is False
    assert trace.pii_protected is False
    assert trace.stage_ms == {"selection": 0, "reformulation": 0, "synthesis": 0}


# ── TraceWriter ───────────────────────────────────────────────────────────────

def test_trace_writer_write_and_read(tmp_path):
    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    trace = QueryTrace.create("tell me about Postgres", channel="web")
    trace.bm25_seeds = [{"atom_id": "abc", "score": 0.9}]
    trace.final_atoms = ["abc"]
    trace.cited_atoms = ["abc"]
    trace.stage_ms = {"selection": 42, "reformulation": 0, "synthesis": 800}

    writer = TraceWriter(cfg)
    writer.write(trace)

    result = writer.read(trace.trace_id)
    assert result is not None
    assert result["trace_id"] == trace.trace_id
    assert result["bm25_seeds"] == [{"atom_id": "abc", "score": 0.9}]
    assert result["final_atoms"] == ["abc"]
    assert result["stage_ms"]["selection"] == 42

def test_trace_writer_read_unknown(tmp_path):
    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    result = TraceWriter(cfg).read("nonexistent-id")
    assert result is None

def test_trace_writer_no_file_returns_none(tmp_path):
    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    assert not (tmp_path / "traces.jsonl").exists()
    assert TraceWriter(cfg).read("any-id") is None

def test_trace_writer_multiple_writes(tmp_path):
    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    writer = TraceWriter(cfg)
    t1 = QueryTrace.create("query one")
    t2 = QueryTrace.create("query two")
    writer.write(t1)
    writer.write(t2)

    assert writer.read(t1.trace_id)["query_hash"] == _sha1("query one")
    assert writer.read(t2.trace_id)["query_hash"] == _sha1("query two")

    lines = (tmp_path / "traces.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2


# ── selection integration ─────────────────────────────────────────────────────

def test_select_populates_trace(tmp_path):
    from datetime import datetime, timezone
    from lattice.db import LatticeDB
    from lattice.models import Atom
    from lattice.selection import select

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    db = LatticeDB(tmp_path)

    atom = Atom(
        atom_id="test-atom-001",
        subject="Postgres",
        kind="fact",
        content="Postgres is a relational database",
        source="user",
        ingested_at=datetime.now(timezone.utc),
        observed_at=datetime.now(timezone.utc),
    )
    db.write(atom)

    trace = QueryTrace.create("tell me about Postgres")
    select("tell me about Postgres", db=db, cfg=cfg, trace=trace)

    assert len(trace.bm25_seeds) > 0
    assert len(trace.final_atoms) > 0
    assert all("atom_id" in s and "score" in s for s in trace.bm25_seeds)

def test_select_no_trace_no_overhead(tmp_path):
    from lattice.db import LatticeDB
    from lattice.selection import select

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    db = LatticeDB(tmp_path)
    # Should not raise even with trace=None (default)
    result = select("anything", db=db, cfg=cfg, trace=None)
    assert isinstance(result, list)


# ── synthesis integration ─────────────────────────────────────────────────────

def _make_tool_resp() -> MagicMock:
    """First create() call — tool loop round with no tool calls (exits immediately)."""
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(tool_calls=None))]
    return resp


def _make_stream(text: str) -> list:
    """Second create() call — streaming response."""
    chunk = MagicMock()
    chunk.choices = [MagicMock(delta=MagicMock(content=text))]
    end = MagicMock()
    end.choices = [MagicMock(delta=MagicMock(content=None))]
    return [chunk, end]


def test_stream_synthesis_populates_trace(tmp_path):
    from lattice.synthesis import stream_synthesis

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model",
                 pii_scrub=False)
    atoms = [{"atom_id": "abc123", "subject": "Postgres", "kind": "fact",
               "content": "Postgres is fast", "src_key": "1",
               "observed_at": "2024-01-01T00:00:00+00:00",
               "valid_from": None, "valid_until": None, "source": "user",
               "source_id": None, "source_title": None, "session_id": None,
               "segment_id": None, "source_type": None, "source_span": None,
               "is_superseded": False, "supersedes": [], "superseded_by": None,
               "ingested_at": None, "provenance": {}}]

    fake_client = MagicMock()
    fake_client.create.side_effect = [
        _make_tool_resp(),
        iter(_make_stream("Postgres is fast [src:abc123].")),
    ]

    trace = QueryTrace.create("tell me about Postgres")
    with patch("lattice.synthesis.LLMClient", return_value=fake_client):
        list(stream_synthesis("tell me about Postgres", atoms, cfg, trace=trace))

    assert "abc123" in trace.cited_atoms
    assert trace.no_answer is False
    assert trace.pii_protected is False

def test_stream_synthesis_no_answer_flag(tmp_path):
    from lattice.synthesis import stream_synthesis

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model",
                 pii_scrub=False)
    atoms = [{"atom_id": "xyz", "subject": "Unrelated", "kind": "fact",
               "content": "Something else", "src_key": "1",
               "observed_at": "2024-01-01T00:00:00+00:00",
               "valid_from": None, "valid_until": None, "source": "user",
               "source_id": None, "source_title": None, "session_id": None,
               "segment_id": None, "source_type": None, "source_span": None,
               "is_superseded": False, "supersedes": [], "superseded_by": None,
               "ingested_at": None, "provenance": {}}]

    fake_client = MagicMock()
    fake_client.create.side_effect = [
        _make_tool_resp(),
        iter(_make_stream("<<NO_INFO>>")),
    ]

    trace = QueryTrace.create("unrelated query")
    with patch("lattice.synthesis.LLMClient", return_value=fake_client):
        list(stream_synthesis("unrelated query", atoms, cfg, trace=trace))

    assert trace.no_answer is True


# ── config ────────────────────────────────────────────────────────────────────

def test_config_lattice_trace_default(tmp_path):
    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model")
    assert cfg.lattice_trace is False

def test_config_lattice_trace_from_env(monkeypatch):
    monkeypatch.setenv("LATTICE_TRACE", "true")
    monkeypatch.setenv("LATTICE_DIR", "/tmp")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    cfg = Config.from_env()
    assert cfg.lattice_trace is True


# ── web endpoint ──────────────────────────────────────────────────────────────

def test_api_trace_disabled_returns_404(tmp_path):
    from fastapi.testclient import TestClient
    import lattice.web.app as _web
    from lattice.db import LatticeDB

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model",
                 lattice_trace=False)
    db = LatticeDB(tmp_path)
    _web.set_config(cfg, db)

    client = TestClient(_web.app)
    resp = client.get("/api/trace/some-id")
    assert resp.status_code == 404

def test_api_trace_enabled_not_found(tmp_path):
    from fastapi.testclient import TestClient
    import lattice.web.app as _web
    from lattice.db import LatticeDB

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model",
                 lattice_trace=True)
    db = LatticeDB(tmp_path)
    _web.set_config(cfg, db)

    client = TestClient(_web.app)
    resp = client.get("/api/trace/nonexistent-id")
    assert resp.status_code == 404

def test_api_trace_returns_record(tmp_path):
    from fastapi.testclient import TestClient
    import lattice.web.app as _web
    from lattice.db import LatticeDB

    cfg = Config(lattice_dir=tmp_path, llm_provider="ollama", llm_model="test-model",
                 lattice_trace=True)
    db = LatticeDB(tmp_path)
    _web.set_config(cfg, db)

    trace = QueryTrace.create("what do I know?")
    trace.final_atoms = ["atom1"]
    TraceWriter(cfg).write(trace)

    client = TestClient(_web.app)
    resp = client.get(f"/api/trace/{trace.trace_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == trace.trace_id
    assert data["final_atoms"] == ["atom1"]
