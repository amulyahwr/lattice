"""STORY-002: lattice_capture MCP tool + lattice_ingest mode A/B guidance."""
from __future__ import annotations

import asyncio
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def patched_server(tmp_path, monkeypatch):
    monkeypatch.setenv("LATTICE_DIR", str(tmp_path))
    with patch("lattice.db.LatticeDB") as mock_db_cls:
        mock_db = MagicMock()
        mock_db_cls.return_value = mock_db
        sys.modules.pop("server", None)
        import server as srv
        yield srv, mock_db, tmp_path


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestToolRegistration:
    def test_lattice_capture_in_list_tools(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        names = [t.name for t in tools]
        assert "lattice_capture" in names

    def test_all_tools_present(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        names = {t.name for t in tools}
        assert {"lattice_ingest", "lattice_capture", "lattice_select", "lattice_answer", "lattice_status"} <= names

    def test_lattice_capture_description_contains_required_text(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        capture = next(t for t in tools if t.name == "lattice_capture")
        assert "Call this at the end of a session to persist what was discussed as memory." in capture.description

    def test_lattice_capture_description_no_redundant_verify(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        capture = next(t for t in tools if t.name == "lattice_capture")
        assert "Do not call lattice_select or lattice_answer to verify" in capture.description

    def test_lattice_ingest_description_mentions_metadata_fields(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        ingest = next(t for t in tools if t.name == "lattice_ingest")
        assert "source_id" in ingest.description
        assert "observed_at" in ingest.description

    def test_lattice_ingest_description_has_two_modes(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        ingest = next(t for t in tools if t.name == "lattice_ingest")
        assert "MODE A" in ingest.description
        assert "MODE B" in ingest.description

    def test_lattice_ingest_description_warns_against_source_override_in_chat(self, patched_server):
        srv, _, _ = patched_server
        tools = _run(srv.list_tools())
        ingest = next(t for t in tools if t.name == "lattice_ingest")
        # Must warn that metadata.source should be omitted for conversation chunks
        assert "OMIT metadata.source" in ingest.description


# ---------------------------------------------------------------------------
# lattice_capture handler — daemon running
# ---------------------------------------------------------------------------

class TestFullMetadataFlow:
    """Verify observed_at, session_id, source etc. survive the IPC boundary."""

    def test_ingest_passes_full_metadata_to_daemon(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["id1"]

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_ingest", {
                "source": "John Doe dislikes mountains.",
                "metadata": {
                    "source": "user",
                    "source_id": "claude-code",
                    "observed_at": "2026-06-03T10:00:00Z",
                    "session_id": "sess-abc",
                },
            }))

        _, kwargs = mock_client.ingest.call_args
        meta = kwargs["metadata"]
        assert meta["source"] == "user"
        assert meta["source_id"] == "claude-code"
        # observed_at and session_id are server-enforced — caller values are overridden
        assert meta["observed_at"] != "2026-06-03T10:00:00Z"  # server replaced it
        assert meta["session_id"] == srv._MCP_SESSION_ID       # process-level ID

    def test_ingest_auto_metadata_reaches_daemon(self, patched_server):
        """Auto-populated observed_at and session_id must reach the daemon, not be dropped."""
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = []

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_ingest", {"source": "some fact"}))

        _, kwargs = mock_client.ingest.call_args
        meta = kwargs["metadata"]
        assert meta.get("observed_at") is not None
        assert meta.get("session_id") is not None

    def test_capture_passes_full_metadata_to_daemon(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["id1"]

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_capture", {
                "source": "Decided to use BM25.",
                "metadata": {"source_id": "claude-code", "session_id": "sess-xyz"},
            }))

        _, kwargs = mock_client.ingest.call_args
        meta = kwargs["metadata"]
        assert meta["source"] == "assistant"
        assert meta["source_id"] == "claude-code"
        assert meta["session_id"] == srv._MCP_SESSION_ID  # server-enforced, not "sess-xyz"
        assert meta.get("observed_at") is not None


class TestCaptureWithDaemon:
    def test_returns_atom_ids_and_count(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["id1", "id2", "id3"]

        with patch("server.DaemonClient", return_value=mock_client):
            result = _run(srv.call_tool("lattice_capture", {"source": "Decided to use BM25 for retrieval."}))

        body = json.loads(result[0].text)
        assert body["atom_ids"] == ["id1", "id2", "id3"]
        assert body["count"] == 3

    def test_uses_source_id_from_metadata(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["id1"]

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool(
                "lattice_capture",
                {"source": "summary", "metadata": {"source_id": "claude-code"}}
            ))

        args, kwargs = mock_client.ingest.call_args
        assert args[0] == "summary"
        assert kwargs["source_id"] == "claude-code"

    def test_defaults_source_id_to_mcp_when_missing(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = []

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_capture", {"source": "summary"}))

        args, kwargs = mock_client.ingest.call_args
        assert args[0] == "summary"
        assert kwargs["source_id"] == "mcp"


# ---------------------------------------------------------------------------
# lattice_capture handler — daemon down (inbox fallback)
# ---------------------------------------------------------------------------

class TestCaptureWithoutDaemon:
    def test_queues_to_inbox_when_daemon_down(self, patched_server):
        srv, _, tmp_path = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = False

        with patch("server.DaemonClient", return_value=mock_client):
            result = _run(srv.call_tool("lattice_capture", {"source": "session summary text"}))

        assert "queued" in result[0].text
        inbox_files = list((tmp_path / "inbox").glob("*.md"))
        assert len(inbox_files) == 1
        assert inbox_files[0].read_text(encoding="utf-8") == "session summary text"

    def test_inbox_files_unique_across_captures(self, patched_server):
        srv, _, tmp_path = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = False

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_capture", {"source": "first session"}))
            _run(srv.call_tool("lattice_capture", {"source": "second session"}))

        files = list((tmp_path / "inbox").glob("*.md"))
        assert len(files) == 2
        assert len({f.name for f in files}) == 2


# ---------------------------------------------------------------------------
# Behavioural parity with lattice_ingest
# ---------------------------------------------------------------------------

class TestCaptureParityWithIngest:
    def test_capture_and_ingest_both_delegate_to_daemon(self, patched_server):
        srv, _, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = ["x1"]

        with patch("server.DaemonClient", return_value=mock_client):
            r_ingest = _run(srv.call_tool("lattice_ingest", {"source": "fact"}))
            r_capture = _run(srv.call_tool("lattice_capture", {"source": "summary"}))

        assert json.loads(r_ingest[0].text)["atom_ids"] == ["x1"]
        assert json.loads(r_capture[0].text)["atom_ids"] == ["x1"]

    def test_capture_does_not_call_preload_if_stale(self, patched_server):
        """lattice_capture is a write path — no need to preload."""
        srv, mock_db, _ = patched_server
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.ingest.return_value = []

        with patch("server.DaemonClient", return_value=mock_client):
            _run(srv.call_tool("lattice_capture", {"source": "summary"}))

        mock_db.preload_if_stale.assert_not_called()


# ---------------------------------------------------------------------------
# Pipeline: chat format detection and source attribution (mode A vs mode B)
# ---------------------------------------------------------------------------

class TestChatFormatDetection:
    """Parser-level and pipeline-level tests — no LLM mocking needed except extract_atoms."""

    def test_role_tagged_text_inferred_as_chat(self):
        from lattice.parsers import infer_source_type
        text = "user: I hate TypeScript\nassistant: Noted, what do you prefer?"
        assert infer_source_type(text, {}) == "chat"

    def test_plain_fact_inferred_as_plain(self):
        from lattice.parsers import infer_source_type
        text = "John Doe dislikes mountains."
        assert infer_source_type(text, {}) == "plain"

    def test_metadata_source_override_applies_to_plain_atoms(self):
        """Mode A: metadata.source overrides every atom for plain segments."""
        from lattice.config import Config
        from lattice.ingest import extract_atoms
        from lattice.parsers import Segment
        from datetime import datetime, timezone

        segment = Segment("s0", "John Doe dislikes mountains.", "plain", 0, 26)
        ref = datetime(2026, 6, 3, tzinfo=timezone.utc)
        cfg = Config(llm_provider="ollama", llm_model="test-model")

        mock_response = '{"atoms": [{"subject": "mountains", "kind": "preference", "source": "document", "content": "John Doe dislikes mountains.", "valid_from": null, "valid_until": null}]}'
        with patch("lattice.ingest.complete", return_value=mock_response):
            atoms = extract_atoms([segment], {"source": "user"}, ref, cfg)

        assert all(a["source"] == "user" for a in atoms)

    def test_metadata_source_override_ignored_for_chat_segments(self):
        """Pipeline guard: metadata.source is NOT applied for chat segments even if caller passes it."""
        from lattice.config import Config
        from lattice.ingest import extract_atoms
        from lattice.parsers import Segment
        from datetime import datetime, timezone

        segment = Segment("s0", "user: I hate TypeScript\nassistant: Noted.", "chat", 0, 40)
        ref = datetime(2026, 6, 3, tzinfo=timezone.utc)
        cfg = Config(llm_provider="ollama", llm_model="test-model")

        mock_response = '{"atoms": [{"subject": "TypeScript", "kind": "preference", "source": "user", "content": "User hates TypeScript.", "valid_from": null, "valid_until": null}]}'
        with patch("lattice.ingest.complete", return_value=mock_response):
            atoms = extract_atoms([segment], {"source": "assistant"}, ref, cfg)

        assert atoms[0]["source"] == "user"

    def test_no_metadata_source_preserves_llm_attribution(self):
        """Without metadata.source, LLM-assigned source survives intact."""
        from lattice.config import Config
        from lattice.ingest import extract_atoms
        from lattice.parsers import Segment
        from datetime import datetime, timezone

        segment = Segment("s0", "user: I hate TypeScript\nassistant: Noted.", "chat", 0, 40)
        ref = datetime(2026, 6, 3, tzinfo=timezone.utc)
        cfg = Config(llm_provider="ollama", llm_model="test-model")

        mock_response = '{"atoms": [{"subject": "TypeScript", "kind": "preference", "source": "user", "content": "User hates TypeScript.", "valid_from": null, "valid_until": null}]}'
        with patch("lattice.ingest.complete", return_value=mock_response):
            atoms = extract_atoms([segment], {}, ref, cfg)

        assert atoms[0]["source"] == "user"


class TestPydanticModels:
    """Pydantic validation at the MCP boundary."""

    def test_ingest_args_strips_source_for_chat_input(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({
            "source": "user: I dislike mountains\nassistant: Noted.",
            "metadata": {"source": "user", "source_id": "claude-code"},
        })
        assert args.metadata.source is None  # stripped by model_validator

    def test_ingest_args_keeps_source_for_plain_input(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({
            "source": "John Doe dislikes mountains.",
            "metadata": {"source": "user", "source_id": "claude-code"},
        })
        assert args.metadata.source == "user"

    def test_ingest_args_accepts_any_source_value(self):
        """Non-AI callers may pass 'document', 'web', 'code', etc. — all accepted."""
        import sys; sys.modules.pop("server", None)
        import server as srv
        for val in ("document", "web", "code", "user", "assistant", "lc"):
            args = srv._IngestArgs.model_validate({
                "source": "some text",
                "metadata": {"source": val},
            })
            assert args.metadata.source == val

    def test_capture_args_defaults_source_to_assistant(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._CaptureArgs.model_validate({"source": "We decided to use BM25."})
        assert args.metadata.source == "assistant"

    def test_capture_args_rejects_non_assistant_source(self):
        from pydantic import ValidationError
        import sys; sys.modules.pop("server", None)
        import server as srv
        with pytest.raises(ValidationError):
            srv._CaptureArgs.model_validate({
                "source": "summary",
                "metadata": {"source": "user"},  # capture is always assistant
            })

    def test_ingest_args_defaults_source_id_to_mcp(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({"source": "some fact"})
        assert args.metadata.source_id == "mcp"

    def test_ingest_args_auto_populates_observed_at(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({"source": "some fact"})
        assert args.metadata.observed_at is not None
        # Must be a valid ISO timestamp
        from datetime import datetime
        datetime.fromisoformat(args.metadata.observed_at)

    def test_ingest_args_auto_populates_session_id(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({"source": "some fact"})
        assert args.metadata.session_id is not None
        import uuid
        uuid.UUID(args.metadata.session_id)  # valid UUID

    def test_caller_observed_at_overridden_by_server(self):
        """Caller-supplied observed_at is ignored — server clock is authoritative."""
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({
            "source": "some fact",
            "metadata": {"observed_at": "2026-01-15T00:00:00Z"},  # rounded midnight
        })
        # Server replaces with precise timestamp — not the caller's rounded value
        assert args.metadata.observed_at != "2026-01-15T00:00:00Z"
        from datetime import datetime
        datetime.fromisoformat(args.metadata.observed_at)  # valid ISO

    def test_caller_session_id_overridden_by_server(self):
        """Caller-supplied session_id is ignored — process-level ID is authoritative."""
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._IngestArgs.model_validate({
            "source": "some fact",
            "metadata": {"session_id": "caller-invented-id"},
        })
        assert args.metadata.session_id == srv._MCP_SESSION_ID
        assert args.metadata.session_id != "caller-invented-id"

    def test_all_calls_share_same_session_id(self):
        """Multiple ingest calls in the same process get the same session_id."""
        import sys; sys.modules.pop("server", None)
        import server as srv
        a1 = srv._IngestArgs.model_validate({"source": "fact one"})
        a2 = srv._IngestArgs.model_validate({"source": "fact two"})
        a3 = srv._IngestArgs.model_validate({"source": "fact three"})
        assert a1.metadata.session_id == a2.metadata.session_id == a3.metadata.session_id == srv._MCP_SESSION_ID

    def test_capture_args_auto_populates_observed_at(self):
        import sys; sys.modules.pop("server", None)
        import server as srv
        args = srv._CaptureArgs.model_validate({"source": "summary"})
        assert args.metadata.observed_at is not None
        from datetime import datetime
        datetime.fromisoformat(args.metadata.observed_at)
