from __future__ import annotations

import json
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import mcp.server.stdio
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.types import TextContent, Tool
from pydantic import BaseModel, Field, model_validator

from lattice.client import DaemonClient
from lattice.config import Config
from lattice.db import AtomNotFound, LatticeDB
from lattice.parsers import infer_source_type
from lattice.selection import _atom_to_dict, select
from lattice.synthesis import synthesize

# ── input models ─────────────────────────────────────────────────────────────

# One session ID for the lifetime of this MCP server process.
# MCP server is 1-to-1 with a Claude Code session — restart = new session = new ID.
_MCP_SESSION_ID: str = str(uuid.uuid4())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _IngestMetadata(BaseModel):
    # "user"/"assistant" for AI callers; "document"/"web"/"code" etc. for others — all valid.
    source: str | None = None
    source_id: str = "mcp"
    # Always overwritten at validation time with server clock — caller value ignored.
    # Claude rounds to midnight; server time is the only reliable source of truth.
    observed_at: str = Field(default_factory=_now_iso)
    # Always overwritten with the process-level session ID — caller value ignored.
    # Ensures all atoms from one Claude Code session share a session_id for graph linking.
    session_id: str = Field(default_factory=lambda: _MCP_SESSION_ID)
    title: str | None = None
    url: str | None = None
    model_config = {"extra": "allow"}


class _IngestArgs(BaseModel):
    source: str
    metadata: _IngestMetadata = Field(default_factory=_IngestMetadata)
    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def normalize(self) -> "_IngestArgs":
        # Always use server clock and process session — never trust caller for these.
        self.metadata.observed_at = _now_iso()
        self.metadata.session_id = _MCP_SESSION_ID
        # Mode B: strip source override for chat-formatted input.
        if self.metadata.source is not None:
            if infer_source_type(self.source, {}) == "chat":
                self.metadata.source = None
        return self


class _CaptureMetadata(BaseModel):
    source: Literal["assistant"] = "assistant"
    source_id: str = "mcp"
    observed_at: str = Field(default_factory=_now_iso)
    session_id: str = Field(default_factory=lambda: _MCP_SESSION_ID)
    title: str | None = None
    model_config = {"extra": "allow"}


class _CaptureArgs(BaseModel):
    source: str
    metadata: _CaptureMetadata = Field(default_factory=_CaptureMetadata)
    model_config = {"extra": "ignore"}

    @model_validator(mode="after")
    def normalize(self) -> "_CaptureArgs":
        self.metadata.observed_at = _now_iso()
        self.metadata.session_id = _MCP_SESSION_ID
        return self


# ── app + db ──────────────────────────────────────────────────────────────────

app = Server("lattice")
_db = LatticeDB()
_db.preload()


def _lattice_dir() -> Path:
    return Config.from_env().lattice_dir


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="lattice_ingest",
            description=(
                "Decompose raw text into discrete knowledge atoms and store them in the lattice. "
                "Returns the number of atoms created and their IDs. "
                "Two usage modes depending on what is being captured:\n"
                "MODE A — single isolated fact or preference from the user: pass the fact as source "
                "and set metadata.source='user'. Example: source='Amulya dislikes mountains', "
                "metadata.source='user'.\n"
                "MODE B — a conversation chunk with multiple turns: format source as role-tagged text "
                "('user: ...\nassistant: ...') and OMIT metadata.source. The pipeline detects the "
                "chat format automatically and attributes each atom to the correct speaker. "
                "Passing metadata.source in mode B would wrongly label all atoms with the same source.\n"
                "Always set metadata.source_id (e.g. 'claude-code') and metadata.observed_at "
                "(current ISO timestamp) regardless of mode."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": (
                            "Raw text to ingest. Either a single fact (mode A) or "
                            "role-tagged conversation turns (mode B): "
                            "'user: <text>\\nassistant: <text>'."
                        ),
                    },
                    "metadata": {
                        "type": "object",
                        "description": (
                            "Provenance metadata. "
                            "source: 'user' or 'assistant' — set only for mode A (single fact), omit for mode B (conversation). "
                            "source_id: surface name e.g. 'claude-code' — always set. "
                            "observed_at: ISO timestamp — always set. "
                            "Optional: session_id, title, url."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["source"],
            },
        ),
        Tool(
            name="lattice_select",
            description=(
                "Select the most relevant knowledge atoms for a natural language query. "
                "Returns a ranked list of atoms."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question or topic.",
                    },
                    "as_of": {
                        "type": "string",
                        "description": "Optional ISO date (YYYY-MM-DD). Filters atoms valid at that date.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="lattice_capture",
            description=(
                "Call this at the end of a session to persist what was discussed as memory. "
                "Do not call lattice_select or lattice_answer to verify atoms already injected "
                "into context — treat injected lattice atoms as authoritative. "
                "Summarize decisions made, things built, and conclusions reached this session. "
                "Do not re-state fine-grained facts or preferences already sent via lattice_ingest "
                "during the session — focus on session-level outcomes. "
                "Always set metadata.source='assistant', metadata.source_id='claude-code', "
                "metadata.observed_at=<current ISO timestamp>."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Session summary text: decisions, outcomes, and conclusions.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": (
                            "Provenance metadata. Required: source_id, observed_at. "
                            "Optional: session_id, title."
                        ),
                        "additionalProperties": True,
                    },
                },
                "required": ["source"],
            },
        ),
        Tool(
            name="lattice_answer",
            description=(
                "Answer a natural language query using the lattice. "
                "Optionally restrict to specific atom IDs; otherwise auto-selects relevant atoms first."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question.",
                    },
                    "atom_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of atom IDs to use. If empty, auto-selects.",
                    },
                    "as_of": {
                        "type": "string",
                        "description": "Optional ISO date passed to selection when atom_ids not provided.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="lattice_status",
            description="Return the number of memories (non-superseded atoms) currently stored in the lattice.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "lattice_ingest":
        args = _IngestArgs.model_validate(arguments)
        meta = args.metadata.model_dump(exclude_none=False)
        client = DaemonClient()
        if client.ping():
            atom_ids = client.ingest(args.source, source_id=args.metadata.source_id, metadata=meta)
            return [TextContent(type="text", text=json.dumps({"atom_ids": atom_ids}))]
        else:
            inbox_dir = _lattice_dir() / "inbox"
            inbox_dir.mkdir(parents=True, exist_ok=True)
            inbox_file = inbox_dir / f"{uuid.uuid4()}.md"
            inbox_file.write_text(args.source, encoding="utf-8")
            return [TextContent(type="text", text=f"queued to inbox: {inbox_file.name}")]

    if name == "lattice_capture":
        args = _CaptureArgs.model_validate(arguments)
        meta = args.metadata.model_dump(exclude_none=False)
        client = DaemonClient()
        if client.ping():
            atom_ids = client.ingest(args.source, source_id=args.metadata.source_id, metadata=meta)
            return [TextContent(type="text", text=json.dumps({"atom_ids": atom_ids, "count": len(atom_ids)}))]
        else:
            inbox_dir = _lattice_dir() / "inbox"
            inbox_dir.mkdir(parents=True, exist_ok=True)
            inbox_file = inbox_dir / f"{uuid.uuid4()}.md"
            inbox_file.write_text(args.source, encoding="utf-8")
            return [TextContent(type="text", text=f"queued to inbox: {inbox_file.name}")]

    if name == "lattice_select":
        _db.preload_if_stale()
        as_of_str: str | None = arguments.get("as_of")
        as_of = date.fromisoformat(as_of_str) if as_of_str else None
        atoms = select(query=arguments["query"], as_of=as_of, db=_db)
        return [TextContent(type="text", text=json.dumps(atoms, indent=2))]

    if name == "lattice_answer":
        _db.preload_if_stale()
        as_of_str = arguments.get("as_of")
        as_of = date.fromisoformat(as_of_str) if as_of_str else None
        atom_ids: list[str] = arguments.get("atom_ids", [])

        t0 = time.monotonic()
        if atom_ids:
            atoms = []
            for aid in atom_ids:
                try:
                    atoms.append(_atom_to_dict(_db.read(aid)))
                except AtomNotFound:
                    pass
        else:
            atoms = select(query=arguments["query"], as_of=as_of, db=_db)
        sel_ms = int((time.monotonic() - t0) * 1000)

        t1 = time.monotonic()
        result = synthesize(query=arguments["query"], atoms=atoms)
        syn_ms = int((time.monotonic() - t1) * 1000)

        try:
            from lattice.web.app import _record_usage
            _record_usage(arguments["query"], sel_ms, syn_ms, len(atoms), channel="mcp")
        except Exception:
            pass

        return [TextContent(type="text", text=result.answer)]

    if name == "lattice_status":
        _db.preload_if_stale()
        count = len([a for a in _db.all() if not a.is_superseded])
        return [TextContent(type="text", text=json.dumps({"count": count}))]

    raise ValueError(f"Unknown tool: {name}")


def main() -> None:
    import asyncio

    async def _run() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="lattice",
                    server_version="0.1.0",
                    capabilities=app.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )

    asyncio.run(_run())


if __name__ == "__main__":
    main()
