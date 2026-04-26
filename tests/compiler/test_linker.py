"""Tests for linker — LLM mocked via mock_chat fixture."""

import json

import pytest

from backend.compiler.linker import cross_link_atoms, expand_domains, link_atoms


# ── expand_domains ────────────────────────────────────────────────────────────


def test_expand_domains_sales():
    assert expand_domains(["sales"]) == {"sales", "finance", "product"}


def test_expand_domains_finance():
    assert expand_domains(["finance"]) == {"finance", "sales", "legal"}


def test_expand_domains_engineering():
    assert expand_domains(["engineering"]) == {"engineering", "product"}


def test_expand_domains_product():
    assert expand_domains(["product"]) == {"product", "sales", "engineering"}


def test_expand_domains_hr():
    assert expand_domains(["hr"]) == {"hr", "legal"}


def test_expand_domains_legal():
    assert expand_domains(["legal"]) == {"legal", "hr", "finance"}


def test_expand_domains_empty_returns_empty_set():
    assert expand_domains([]) == set()


def test_expand_domains_no_chaining():
    # "sales" expands to include "product", but "product"'s group partner
    # "engineering" should NOT be pulled in — expansion is one-hop only.
    result = expand_domains(["sales"])
    assert "engineering" not in result


def test_expand_domains_multi_domain_unions_groups():
    # ["sales", "hr"] → {sales, finance, product} ∪ {hr, legal}
    result = expand_domains(["sales", "hr"])
    assert result == {"sales", "finance", "product", "hr", "legal"}


def test_expand_domains_unknown_domain_passthrough():
    # Unknown domains are kept in the set (they just match no groups)
    result = expand_domains(["unknown"])
    assert result == {"unknown"}


def test_expand_domains_preserves_input_domain():
    result = expand_domains(["engineering"])
    assert "engineering" in result


# ── link_atoms ────────────────────────────────────────────────────────────────


async def test_link_atoms_happy_path(mock_chat):
    mock_chat.return_value = json.dumps([
        {"from": 0, "to": 1, "relation": "causal"},
    ])
    contents = ["A caused B to happen here.", "B happened because of A indeed."]
    links = await link_atoms(contents)
    assert len(links) == 2
    assert links[0] == [{"target_index": 1, "relation": "causal"}]
    assert links[1] == []


async def test_link_atoms_empty_response_returns_empty_lists(mock_chat):
    mock_chat.return_value = "[]"
    links = await link_atoms(["Fact one.", "Fact two."])
    assert links == [[], []]


async def test_link_atoms_no_json_array_returns_empty(mock_chat):
    mock_chat.return_value = "No relationships found between these propositions."
    links = await link_atoms(["A.", "B."])
    assert links == [[], []]


async def test_link_atoms_out_of_range_target_filtered(mock_chat):
    # to=99 is out of range for a 2-atom list
    mock_chat.return_value = json.dumps([{"from": 0, "to": 99, "relation": "topical"}])
    links = await link_atoms(["A here.", "B here."])
    assert all(l == [] for l in links)


async def test_link_atoms_self_loop_filtered(mock_chat):
    # from == to → excluded
    mock_chat.return_value = json.dumps([{"from": 0, "to": 0, "relation": "topical"}])
    links = await link_atoms(["A sentence here."])
    assert links[0] == []


async def test_link_atoms_both_directions(mock_chat):
    mock_chat.return_value = json.dumps([
        {"from": 0, "to": 1, "relation": "causal"},
        {"from": 1, "to": 0, "relation": "causal"},
    ])
    links = await link_atoms(["Cause content here.", "Effect content here."])
    assert len(links[0]) == 1
    assert len(links[1]) == 1


async def test_link_atoms_all_valid_relations(mock_chat):
    relations = ["causal", "temporal", "hierarchical", "topical", "contradicts"]
    raw = [{"from": 0, "to": 1, "relation": r} for r in relations]
    mock_chat.return_value = json.dumps(raw)
    links = await link_atoms(["Atom zero content here.", "Atom one content here."])
    assert len(links[0]) == len(relations)


async def test_link_atoms_missing_from_or_to_skipped(mock_chat):
    mock_chat.return_value = json.dumps([
        {"from": 0, "relation": "causal"},   # missing 'to'
        {"to": 1, "relation": "topical"},    # missing 'from'
    ])
    links = await link_atoms(["Atom A sentence.", "Atom B sentence."])
    assert all(l == [] for l in links)


async def test_link_atoms_single_atom_returns_single_empty_list(mock_chat):
    mock_chat.return_value = "[]"
    links = await link_atoms(["Only one atom here."])
    assert links == [[]]


async def test_link_atoms_empty_input_returns_empty(mock_chat):
    links = await link_atoms([])
    assert links == []
    mock_chat.assert_not_called()


# ── cross_link_atoms ──────────────────────────────────────────────────────────


async def test_cross_link_atoms_happy_path(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"}
    ])
    links = await cross_link_atoms(
        new_contents=["Sales pipeline hit record Q2."],
        existing_contents=["Revenue grew 20% in Q2."],
    )
    assert len(links) == 1
    assert links[0] == [{"existing_index": 0, "relation": "topical"}]


async def test_cross_link_atoms_empty_new_returns_empty_without_llm_call(mock_chat):
    links = await cross_link_atoms([], ["Existing content here."])
    assert links == []
    mock_chat.assert_not_called()


async def test_cross_link_atoms_empty_existing_returns_empty_without_llm_call(mock_chat):
    links = await cross_link_atoms(["New content here."], [])
    assert links == [[]]
    mock_chat.assert_not_called()


async def test_cross_link_atoms_no_relations_found(mock_chat):
    mock_chat.return_value = "[]"
    links = await cross_link_atoms(["New content."], ["Existing content."])
    assert links == [[]]


async def test_cross_link_atoms_out_of_range_new_index_filtered(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 99, "existing_index": 0, "relation": "topical"},
    ])
    links = await cross_link_atoms(["New content."], ["Existing content."])
    assert links == [[]]


async def test_cross_link_atoms_out_of_range_existing_index_filtered(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 99, "relation": "causal"},
    ])
    links = await cross_link_atoms(["New content."], ["Existing content."])
    assert links == [[]]


async def test_cross_link_atoms_missing_indices_skipped(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "relation": "topical"},       # missing existing_index
        {"existing_index": 0, "relation": "causal"},   # missing new_index
    ])
    links = await cross_link_atoms(["New content."], ["Existing content."])
    assert links == [[]]


async def test_cross_link_atoms_multiple_new_atoms(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"},
        {"new_index": 1, "existing_index": 0, "relation": "causal"},
    ])
    links = await cross_link_atoms(
        new_contents=["New atom one content.", "New atom two content."],
        existing_contents=["Existing atom one content."],
    )
    assert len(links) == 2
    assert links[0] == [{"existing_index": 0, "relation": "topical"}]
    assert links[1] == [{"existing_index": 0, "relation": "causal"}]


async def test_cross_link_atoms_multiple_links_per_new_atom(mock_chat):
    mock_chat.return_value = json.dumps([
        {"new_index": 0, "existing_index": 0, "relation": "topical"},
        {"new_index": 0, "existing_index": 1, "relation": "causal"},
    ])
    links = await cross_link_atoms(
        new_contents=["New atom content here."],
        existing_contents=["Existing one content.", "Existing two content."],
    )
    assert len(links[0]) == 2
    assert links[0][0]["existing_index"] == 0
    assert links[0][1]["existing_index"] == 1


async def test_cross_link_atoms_no_json_in_response(mock_chat):
    mock_chat.return_value = "No cross-source relationships were found."
    links = await cross_link_atoms(["New content."], ["Existing content."])
    assert links == [[]]
