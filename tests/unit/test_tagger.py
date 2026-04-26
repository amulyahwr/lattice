"""Unit tests for tagger bitmask logic — zero I/O, no fixtures needed."""

import pytest

from backend.compiler.tagger import (
    DOMAIN_BIT_MAP,
    INTERNAL_BITS,
    _domains_to_mask,
    _parse_domain_response,
    _source_level_mask,
    mask_to_domains,
)

# ── _domains_to_mask ─────────────────────────────────────────────────────────


def test_domains_to_mask_single_domain():
    assert _domains_to_mask(["sales"]) == 1 << DOMAIN_BIT_MAP["sales"]


def test_domains_to_mask_multi_domain():
    mask = _domains_to_mask(["finance", "engineering"])
    assert mask == (1 << DOMAIN_BIT_MAP["finance"]) | (
        1 << DOMAIN_BIT_MAP["engineering"]
    )


def test_domains_to_mask_all_known_domains():
    all_domains = list(DOMAIN_BIT_MAP.keys())
    mask = _domains_to_mask(all_domains)
    expected = 0
    for d in all_domains:
        expected |= 1 << DOMAIN_BIT_MAP[d]
    assert mask == expected


def test_domains_to_mask_general_falls_back_to_internal_bits():
    # 'general' is not in DOMAIN_BIT_MAP → no bits set → returns INTERNAL_BITS
    assert _domains_to_mask(["general"]) == INTERNAL_BITS


def test_domains_to_mask_empty_falls_back_to_internal_bits():
    assert _domains_to_mask([]) == INTERNAL_BITS


def test_domains_to_mask_unknown_domain_ignored():
    # Unknown domain contributes no bits; if all unknown → INTERNAL_BITS
    assert _domains_to_mask(["superpowers", "magic"]) == INTERNAL_BITS


def test_domains_to_mask_mixed_known_and_unknown():
    # Unknown domains are ignored; known ones contribute their bits
    mask = _domains_to_mask(["sales", "unknown_dept"])
    assert mask == 1 << DOMAIN_BIT_MAP["sales"]


# ── mask_to_domains ──────────────────────────────────────────────────────────


def test_mask_to_domains_single_bit():
    mask = 1 << DOMAIN_BIT_MAP["hr"]
    assert mask_to_domains(mask) == ["hr"]


def test_mask_to_domains_multi_bit():
    mask = (1 << DOMAIN_BIT_MAP["sales"]) | (1 << DOMAIN_BIT_MAP["finance"])
    result = mask_to_domains(mask)
    assert sorted(result) == ["finance", "sales"]


def test_mask_to_domains_returns_sorted():
    mask = (
        (1 << DOMAIN_BIT_MAP["product"])
        | (1 << DOMAIN_BIT_MAP["engineering"])
        | (1 << DOMAIN_BIT_MAP["sales"])
    )
    result = mask_to_domains(mask)
    assert result == sorted(result)


def test_mask_to_domains_zero_returns_empty():
    assert mask_to_domains(0) == []


def test_mask_to_domains_round_trip():
    for domains in [["sales"], ["finance", "hr"], ["engineering", "legal", "product"]]:
        mask = _domains_to_mask(domains)
        assert mask_to_domains(mask) == sorted(domains)


def test_mask_to_domains_all_six_domains():
    all_domains = sorted(DOMAIN_BIT_MAP.keys())
    mask = _domains_to_mask(all_domains)
    assert mask_to_domains(mask) == all_domains


# ── _parse_domain_response ───────────────────────────────────────────────────


def test_parse_domain_response_happy_path():
    raw = '[["sales"], ["engineering", "finance"]]'
    result = _parse_domain_response(raw, expected=2)
    assert result == [["sales"], ["engineering", "finance"]]


def test_parse_domain_response_string_items_wrapped_in_list():
    # LLM sometimes returns a flat string per item instead of a list
    raw = '["sales", "engineering"]'
    result = _parse_domain_response(raw, expected=2)
    assert result == [["sales"], ["engineering"]]


def test_parse_domain_response_no_json_array_raises():
    with pytest.raises(ValueError, match="no JSON array"):
        _parse_domain_response("I cannot classify these.", expected=1)


def test_parse_domain_response_size_mismatch_pads_with_empty():
    # LLM sometimes returns fewer items than expected; we pad with empty lists
    raw = '[["sales"]]'
    result = _parse_domain_response(raw, expected=3)
    assert result == [["sales"], [], []]


def test_parse_domain_response_size_mismatch_truncates():
    # LLM sometimes returns more items than expected; we truncate
    raw = '[["sales"], ["finance"], ["engineering"]]'
    result = _parse_domain_response(raw, expected=2)
    assert result == [["sales"], ["finance"]]


def test_parse_domain_response_invalid_domains_return_empty_list():
    # Invalid domain names are filtered out; result is an empty list per atom
    raw = '[["superpowers", "magic"]]'
    result = _parse_domain_response(raw, expected=1)
    assert result == [[]]


def test_parse_domain_response_mixed_valid_invalid_keeps_valid():
    raw = '[["sales", "unicorn"]]'
    result = _parse_domain_response(raw, expected=1)
    assert result == [["sales"]]


def test_parse_domain_response_general_not_a_valid_domain():
    # 'general' is used in serving-layer filters but is not produced by the tagger
    raw = '[["general"]]'
    result = _parse_domain_response(raw, expected=1)
    assert result == [[]]


def test_parse_domain_response_extracts_from_prose():
    # LLM wraps array in prose
    raw = 'Here is the classification: [["hr"]] Hope that helps.'
    result = _parse_domain_response(raw, expected=1)
    assert result == [["hr"]]


# ── _source_level_mask ───────────────────────────────────────────────────────


def test_source_level_mask_majority_single_domain():
    domain_lists = [["sales"], ["sales"], ["sales"]]
    mask = _source_level_mask(domain_lists)
    assert mask == _domains_to_mask(["sales"])


def test_source_level_mask_majority_vote_excludes_minority():
    # 3× sales, 1× finance → finance is 1/3 of top (33%), below 80% threshold
    domain_lists = [["sales"], ["sales"], ["sales"], ["finance"]]
    mask = _source_level_mask(domain_lists)
    assert mask == _domains_to_mask(["sales"])
    assert not (mask & (1 << DOMAIN_BIT_MAP["finance"]))


def test_source_level_mask_includes_close_second():
    # 3× sales, 3× finance → both at 100% of top, both included
    domain_lists = [
        ["sales"],
        ["sales"],
        ["sales"],
        ["finance"],
        ["finance"],
        ["finance"],
    ]
    mask = _source_level_mask(domain_lists)
    assert mask & (1 << DOMAIN_BIT_MAP["sales"])
    assert mask & (1 << DOMAIN_BIT_MAP["finance"])


def test_source_level_mask_all_general_returns_internal_bits():
    domain_lists = [["general"], ["general"], ["general"]]
    assert _source_level_mask(domain_lists) == INTERNAL_BITS


def test_source_level_mask_empty_list_returns_internal_bits():
    assert _source_level_mask([]) == INTERNAL_BITS


def test_source_level_mask_ignores_general_in_tally():
    # Mixed: some 'general', some 'sales' — only 'sales' should influence the mask
    domain_lists = [["sales"], ["general"], ["sales"], ["general"]]
    mask = _source_level_mask(domain_lists)
    assert mask == _domains_to_mask(["sales"])
