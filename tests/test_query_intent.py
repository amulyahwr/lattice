from __future__ import annotations

import pytest

from lattice.query import QueryShape, parse_query


@pytest.mark.parametrize("text", [
    "how many times did I go to the gym",
    "how many books did I read last year",
    "total number of meetings this month",
    "count of doctor visits",
    "what is the number of times I mentioned Sarah",
    "how much did I spend on coffee",
    "how many times did I travel",
])
def test_aggregation_detected(text):
    assert parse_query(text).shape == QueryShape.AGGREGATION


@pytest.mark.parametrize("text", [
    "what gym do I go to",
    "when did I last see the doctor",
    "what book am I reading",
    "who is Sarah",
    "what hotel did I book",
])
def test_no_false_positive_on_factual(text):
    assert parse_query(text).shape != QueryShape.AGGREGATION


def test_aggregation_case_insensitive():
    assert parse_query("HOW MANY times").shape == QueryShape.AGGREGATION


def test_aggregation_beats_recommendation():
    # "how many times did" has "did" which could match "did you" — aggregation wins
    assert parse_query("how many times did I mention this").shape == QueryShape.AGGREGATION


def test_aggregation_beats_temporal():
    # "how many days" has temporal token "days" — aggregation wins
    assert parse_query("how many days did I exercise last month").shape == QueryShape.AGGREGATION
