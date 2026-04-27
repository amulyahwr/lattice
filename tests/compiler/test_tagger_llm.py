"""Tests for tag_atoms and suggest_domains — LLM mocked via mock_chat fixture."""

import json

import pytest

from backend.compiler.tagger import INTERNAL_BITS, tag_atoms


async def test_tag_atoms_happy_path_returns_correct_structure(mock_chat):
    mock_chat.return_value = json.dumps({"0": ["sales"], "1": ["finance"]})
    result = await tag_atoms(
        contents=["Pipeline grew 15% this quarter.", "Budget approved for Q3."],
        kinds=["metric", "decision"],
    )
    assert len(result) == 2
    assert result[0]["kind"] == "metric"
    assert result[1]["kind"] == "decision"
    assert "access_mask" in result[0]
    assert "domain" in result[0]


async def test_tag_atoms_per_atom_masks_reflect_own_domains(mock_chat):
    # Each atom gets a mask derived from its own domains, not the source majority.
    mock_chat.return_value = json.dumps({"0": ["sales"], "1": ["engineering"], "2": ["sales"]})
    result = await tag_atoms(
        contents=["c1", "c2", "c3"],
        kinds=["fact", "fact", "fact"],
    )
    from backend.compiler.tagger import DOMAIN_BIT_MAP
    sales_bit = 1 << DOMAIN_BIT_MAP["sales"]
    eng_bit = 1 << DOMAIN_BIT_MAP["engineering"]
    assert result[0]["access_mask"] == sales_bit
    assert result[1]["access_mask"] == eng_bit
    assert result[2]["access_mask"] == sales_bit


async def test_tag_atoms_no_domain_falls_back_to_source_mask(mock_chat):
    # Atom with no valid domains inherits the source-level majority-vote mask.
    # Source has 2× sales, 1× no-domain → source mask = sales_bit; no-domain atom gets it.
    mock_chat.return_value = json.dumps({"0": ["sales"], "1": ["sales"], "2": []})
    result = await tag_atoms(
        contents=["c1", "c2", "c3"],
        kinds=["fact", "fact", "fact"],
    )
    from backend.compiler.tagger import DOMAIN_BIT_MAP
    sales_bit = 1 << DOMAIN_BIT_MAP["sales"]
    assert result[2]["access_mask"] == sales_bit  # fallback to source mask
    assert result[2]["domain"] == ["sales"]  # back-derived from fallback mask to stay consistent


async def test_tag_atoms_missing_index_maps_to_correct_atom(mock_chat):
    # LLM dropped index "1" entirely — atom 1 gets [] → source mask fallback.
    # Crucially, atom 2's classification must NOT shift into atom 1's slot.
    # Source has 1× sales + 1× engineering (equal count) → source mask = sales | eng.
    mock_chat.return_value = json.dumps({"0": ["sales"], "2": ["engineering"]})
    result = await tag_atoms(
        contents=["c1", "c2", "c3"],
        kinds=["fact", "fact", "fact"],
    )
    from backend.compiler.tagger import DOMAIN_BIT_MAP
    sales_bit = 1 << DOMAIN_BIT_MAP["sales"]
    eng_bit = 1 << DOMAIN_BIT_MAP["engineering"]
    source_mask = sales_bit | eng_bit
    assert result[0]["access_mask"] == sales_bit    # index 0 → own domain: sales only
    assert result[1]["access_mask"] == source_mask  # falls back to source majority mask
    assert set(result[1]["domain"]) == {"sales", "engineering"}  # back-derived from source mask
    assert result[2]["access_mask"] == eng_bit      # index 2 → own domain: engineering, not shifted


async def test_tag_atoms_all_general_yields_internal_bits(mock_chat):
    mock_chat.return_value = json.dumps({"0": ["general"], "1": ["general"]})
    result = await tag_atoms(
        contents=["Random fact here.", "Another random fact."],
        kinds=["fact", "fact"],
    )
    assert result[0]["access_mask"] == INTERNAL_BITS


async def test_tag_atoms_per_atom_domain_field_set(mock_chat):
    mock_chat.return_value = json.dumps({"0": ["hr", "legal"]})
    result = await tag_atoms(contents=["HR policy update."], kinds=["fact"])
    assert "hr" in result[0]["domain"]
    assert "legal" in result[0]["domain"]


async def test_tag_atoms_single_dominant_domain_sets_single_bit(mock_chat):
    mock_chat.return_value = json.dumps({"0": ["finance"], "1": ["finance"], "2": ["finance"]})
    result = await tag_atoms(
        contents=["Budget A.", "Budget B.", "Budget C."],
        kinds=["metric", "metric", "metric"],
    )
    from backend.compiler.tagger import DOMAIN_BIT_MAP
    finance_bit = 1 << DOMAIN_BIT_MAP["finance"]
    assert result[0]["access_mask"] & finance_bit
    eng_bit = 1 << DOMAIN_BIT_MAP["engineering"]
    assert not (result[0]["access_mask"] & eng_bit)


async def test_tag_atoms_kind_preserved_from_input(mock_chat):
    mock_chat.return_value = json.dumps({"0": ["sales"], "1": ["engineering"]})
    kinds = ["decision", "procedure"]
    result = await tag_atoms(contents=["content a", "content b"], kinds=kinds)
    assert result[0]["kind"] == "decision"
    assert result[1]["kind"] == "procedure"


async def test_tag_atoms_batches_above_50(mock_chat):
    async def _side(system, user, **kw):
        batch = json.loads(user)
        return json.dumps({str(i): ["general"] for i in range(len(batch))})

    mock_chat.side_effect = _side
    contents = [f"Content sentence number {i}." for i in range(60)]
    kinds = ["fact"] * 60
    result = await tag_atoms(contents=contents, kinds=kinds)
    assert len(result) == 60
    assert mock_chat.call_count == 2  # batch_size=50 → ceil(60/50)=2 calls
