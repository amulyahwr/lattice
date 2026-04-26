"""Tests for distiller — LLM mocked via mock_chat fixture."""

import json

import pytest

from backend.compiler.atomizer import RawAtom
from backend.compiler.distiller import distill_atoms


def _atoms(n: int) -> list[RawAtom]:
    return [RawAtom(content=f"Proposition number {i} about revenue.", kind="fact") for i in range(n)]


async def test_distill_atoms_happy_path(mock_chat):
    mock_chat.return_value = json.dumps([
        {"content": "Prop 0 about revenue.", "canonical": None},
        {"content": "Prop 1 about revenue.", "canonical": None},
    ])
    result = await distill_atoms(_atoms(2))
    assert len(result) == 2
    assert result[0]["content"] == "Prop 0 about revenue."
    assert result[0]["canonical"] is None


async def test_distill_atoms_returns_canonical_when_present(mock_chat):
    canonical = {
        "subject": "revenue", "predicate": "grew",
        "object": "20%", "value": 20, "unit": "%", "period": "Q2-2025",
    }
    mock_chat.return_value = json.dumps([
        {"content": "Revenue grew 20% in Q2 2025.", "canonical": canonical},
    ])
    result = await distill_atoms(_atoms(1))
    assert result[0]["canonical"] == canonical


async def test_distill_atoms_extracts_json_from_prose(mock_chat):
    # LLM wraps JSON in prose — distiller should still extract the array
    inner = json.dumps([{"content": "Result.", "canonical": None}])
    mock_chat.return_value = f"Here is the distilled output: {inner} Hope it helps."
    result = await distill_atoms(_atoms(1))
    assert result[0]["content"] == "Result."


async def test_distill_atoms_raises_on_no_json_array(mock_chat):
    mock_chat.return_value = "I cannot process this request right now."
    with pytest.raises(ValueError):
        await distill_atoms(_atoms(1))


async def test_distill_atoms_raises_on_batch_size_mismatch(mock_chat):
    # LLM returns only 1 item but batch has 3
    mock_chat.return_value = json.dumps([{"content": "Only one.", "canonical": None}])
    with pytest.raises(ValueError, match="items for"):
        await distill_atoms(_atoms(3))


async def test_distill_atoms_batches_above_25(mock_chat):
    def side_effect(system, user, **kw):
        import asyncio
        batch = json.loads(user)
        return asyncio.coroutine(lambda: json.dumps(
            [{"content": f"c{i}", "canonical": None} for i in range(len(batch))]
        ))()

    # Use a simpler approach
    call_responses = []

    async def _side(system, user, **kw):
        batch = json.loads(user)
        return json.dumps([{"content": f"c{i}", "canonical": None} for i in range(len(batch))])

    mock_chat.side_effect = _side
    result = await distill_atoms(_atoms(30))
    assert len(result) == 30
    assert mock_chat.call_count == 2  # batch_size=25 → ceil(30/25)=2 calls


async def test_distill_atoms_single_atom(mock_chat):
    mock_chat.return_value = json.dumps([{"content": "Single atom.", "canonical": None}])
    result = await distill_atoms(_atoms(1))
    assert len(result) == 1


async def test_distill_atoms_preserves_order(mock_chat):
    mock_chat.return_value = json.dumps([
        {"content": "First.", "canonical": None},
        {"content": "Second.", "canonical": None},
        {"content": "Third.", "canonical": None},
    ])
    result = await distill_atoms(_atoms(3))
    assert [r["content"] for r in result] == ["First.", "Second.", "Third."]
