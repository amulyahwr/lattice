"""Tests for atomizer — LLM mocked via mock_chat fixture."""

import json

import pytest

from backend.compiler.atomizer import RawAtom, atomize_chunk, atomize_chunks


async def test_atomize_chunk_happy_path(mock_chat):
    mock_chat.return_value = json.dumps([
        {"kind": "metric", "content": "Revenue grew 20% in Q2 2025."},
        {"kind": "fact", "content": "The company operates in 12 countries."},
    ])
    atoms = await atomize_chunk("Some source text about the company.")
    assert len(atoms) == 2
    assert atoms[0].kind == "metric"
    assert atoms[0].content == "Revenue grew 20% in Q2 2025."
    assert atoms[1].kind == "fact"
    assert atoms[1].content == "The company operates in 12 countries."


async def test_atomize_chunk_all_valid_kinds(mock_chat):
    mock_chat.return_value = json.dumps([
        {"kind": "fact", "content": "The office is in San Francisco."},
        {"kind": "metric", "content": "Sales hit $5M this quarter."},
        {"kind": "decision", "content": "Board approved the acquisition."},
        {"kind": "event", "content": "Product was launched in March."},
        {"kind": "procedure", "content": "Step one is to configure the server."},
    ])
    atoms = await atomize_chunk("text")
    kinds = {a.kind for a in atoms}
    assert kinds == {"fact", "metric", "decision", "event", "procedure"}


async def test_atomize_chunk_filters_invalid_kind(mock_chat):
    mock_chat.return_value = json.dumps([
        {"kind": "unknown_kind", "content": "This has an invalid kind label."},
    ])
    atoms = await atomize_chunk("text")
    assert atoms == []


async def test_atomize_chunk_filters_short_content(mock_chat):
    # Content with fewer than 3 words is dropped
    mock_chat.return_value = json.dumps([
        {"kind": "fact", "content": "ok"},
        {"kind": "fact", "content": "This is valid content here."},
    ])
    atoms = await atomize_chunk("text")
    assert len(atoms) == 1
    assert atoms[0].content == "This is valid content here."


async def test_atomize_chunk_no_json_array_returns_empty(mock_chat):
    # LLM returns prose with no JSON array
    mock_chat.return_value = "No valid propositions found in the text."
    atoms = await atomize_chunk("text")
    assert atoms == []


async def test_atomize_chunk_empty_response_returns_empty(mock_chat):
    mock_chat.return_value = ""
    atoms = await atomize_chunk("text")
    assert atoms == []


async def test_atomize_chunk_calls_chat_once(mock_chat):
    mock_chat.return_value = json.dumps([{"kind": "fact", "content": "Some valid fact content here."}])
    await atomize_chunk("chunk text")
    assert mock_chat.call_count == 1


async def test_atomize_chunks_deduplicates_across_chunks(mock_chat):
    # Both chunks produce the same proposition — only one should remain
    mock_chat.return_value = json.dumps([
        {"kind": "fact", "content": "Revenue grew 20% in Q2 2025."},
    ])
    atoms = await atomize_chunks(["chunk one", "chunk two"])
    contents = [a.content for a in atoms]
    assert len(contents) == len(set(c.lower() for c in contents))


async def test_atomize_chunks_calls_chat_once_per_chunk(mock_chat):
    mock_chat.return_value = json.dumps([{"kind": "fact", "content": "Some valid fact content here."}])
    await atomize_chunks(["chunk one", "chunk two", "chunk three"])
    assert mock_chat.call_count == 3


async def test_atomize_chunks_empty_input_returns_empty(mock_chat):
    atoms = await atomize_chunks([])
    assert atoms == []
    mock_chat.assert_not_called()


async def test_atomize_chunks_multiple_atoms_per_chunk(mock_chat):
    mock_chat.return_value = json.dumps([
        {"kind": "fact", "content": "First unique fact about the company."},
        {"kind": "metric", "content": "Revenue was $10M in Q3 this year."},
    ])
    atoms = await atomize_chunks(["single chunk"])
    assert len(atoms) == 2


async def test_atomize_chunk_dedup_is_case_insensitive(mock_chat):
    # Same content, different case → deduplicated
    call_count = 0

    async def side_effect(system, user, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return json.dumps([{"kind": "fact", "content": "Revenue grew 20% in Q2 2025."}])
        return json.dumps([{"kind": "fact", "content": "revenue grew 20% in Q2 2025."}])

    mock_chat.side_effect = side_effect
    atoms = await atomize_chunks(["chunk one", "chunk two"])
    assert len(atoms) == 1
