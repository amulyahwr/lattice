from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import mcp.server.stdio
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.types import TextContent, Tool

from lattice.client import DaemonClient
from lattice.config import Config
from lattice.db import AtomNotFound, LatticeDB
from lattice.selection import _atom_to_dict, select
from lattice.synthesis import synthesize

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
                "Returns the number of atoms created and their IDs."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Raw text content to ingest.",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Optional passthrough metadata (title, url, author, date, etc.).",
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
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "lattice_ingest":
        text = arguments["source"]
        metadata = arguments.get("metadata", {})
        source_id = metadata.get("source_id", "mcp")

        client = DaemonClient()
        if client.ping():
            atom_ids = client.ingest(text, source_id=source_id)
            return [TextContent(type="text", text=json.dumps({"atom_ids": atom_ids}))]
        else:
            inbox_dir = _lattice_dir() / "inbox"
            inbox_dir.mkdir(parents=True, exist_ok=True)
            inbox_file = inbox_dir / f"{uuid.uuid4()}.md"
            inbox_file.write_text(text, encoding="utf-8")
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

        if atom_ids:
            atoms = []
            for aid in atom_ids:
                try:
                    atoms.append(_atom_to_dict(_db.read(aid)))
                except AtomNotFound:
                    pass
        else:
            atoms = select(query=arguments["query"], as_of=as_of, db=_db)

        result = synthesize(query=arguments["query"], atoms=atoms)
        return [TextContent(type="text", text=result.answer)]

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
