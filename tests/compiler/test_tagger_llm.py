"""Tests for tag_atoms and suggest_domains — LLM mocked via mock_chat fixture."""

import json

import pytest

from backend.compiler.tagger import INTERNAL_BITS, tag_atoms


async def test_tag_atoms_happy_path_returns_correct_structure(mock_chat):
    mock_chat.return_value = json.dumps([["sales"], ["finance"]])
    result = await tag_atoms(
        contents=["Pipeline grew 15% this quarter.", "Budget approved for Q3."],
        kinds=["metric", "decision"],
    )
    assert len(result) == 2
    assert result[0]["kind"] == "metric"
    assert result[1]["kind"] == "decision"
    assert "access_mask" in result[0]
    assert "domain" in result[0]


async def test_tag_atoms_source_mask_identical_for_all_atoms(mock_chat):
    mock_chat.return_value = json.dumps([["sales"], ["engineering"], ["sales"]])
    result = await tag_atoms(
        contents=["c1", "c2", "c3"],
        kinds=["fact", "fact", "fact"],
    )
    masks = {r["access_mask"] for r in result}
    assert len(masks) == 1  # source-level: all atoms get the same mask


async def test_tag_atoms_all_general_yields_internal_bits(mock_chat):
    mock_chat.return_value = json.dumps([["general"], ["general"]])
    result = await tag_atoms(
        contents=["Random fact here.", "Another random fact."],
        kinds=["fact", "fact"],
    )
    assert result[0]["access_mask"] == INTERNAL_BITS


async def test_tag_atoms_per_atom_domain_field_set(mock_chat):
    mock_chat.return_value = json.dumps([["hr", "legal"]])
    result = await tag_atoms(contents=["HR policy update."], kinds=["fact"])
    assert "hr" in result[0]["domain"]
    assert "legal" in result[0]["domain"]


async def test_tag_atoms_single_dominant_domain_sets_single_bit(mock_chat):
    # All atoms tagged 'finance' → only finance bit set in source mask
    mock_chat.return_value = json.dumps([["finance"], ["finance"], ["finance"]])
    result = await tag_atoms(
        contents=["Budget A.", "Budget B.", "Budget C."],
        kinds=["metric", "metric", "metric"],
    )
    from backend.compiler.tagger import DOMAIN_BIT_MAP
    finance_bit = 1 << DOMAIN_BIT_MAP["finance"]
    assert result[0]["access_mask"] & finance_bit
    # Verify other bits not set (e.g. engineering)
    eng_bit = 1 << DOMAIN_BIT_MAP["engineering"]
    assert not (result[0]["access_mask"] & eng_bit)


async def test_tag_atoms_kind_preserved_from_input(mock_chat):
    mock_chat.return_value = json.dumps([["sales"], ["engineering"]])
    kinds = ["decision", "procedure"]
    result = await tag_atoms(contents=["content a", "content b"], kinds=kinds)
    assert result[0]["kind"] == "decision"
    assert result[1]["kind"] == "procedure"


async def test_tag_atoms_batches_above_50(mock_chat):
    async def _side(system, user, **kw):
        batch = json.loads(user)
        return json.dumps([["general"] for _ in batch])

    mock_chat.side_effect = _side
    contents = [f"Content sentence number {i}." for i in range(60)]
    kinds = ["fact"] * 60
    result = await tag_atoms(contents=contents, kinds=kinds)
    assert len(result) == 60
    assert mock_chat.call_count == 2  # batch_size=50 → ceil(60/50)=2 calls
