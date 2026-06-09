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


def test_aggregation_primary_kind_is_count():
    intent = parse_query("how many times did I go to the gym")
    assert intent.primary_kind == "count"


def test_recommendation_primary_kind():
    intent = parse_query("what did you recommend for breakfast")
    assert intent.primary_kind == "recommendation"


def test_preference_primary_kind():
    intent = parse_query("what do I prefer to drink")
    assert intent.primary_kind == "preference"


def test_factual_primary_kind_is_none():
    intent = parse_query("what is the capital of France")
    assert intent.primary_kind is None


def test_is_on_topic_match():
    from lattice.models import Atom
    intent = parse_query("what do I prefer about coffee")
    coffee_atom = Atom(kind="preference", source="user", subject="coffee", content="Likes dark roast.")
    assert intent.is_on_topic(coffee_atom) is True


def test_is_on_topic_no_match():
    from lattice.models import Atom
    intent = parse_query("what do I prefer about coffee")
    hiking_atom = Atom(kind="preference", source="user", subject="hiking trails", content="Likes long hikes.")
    assert intent.is_on_topic(hiking_atom) is False


def test_is_on_topic_empty_tokens():
    from lattice.models import Atom
    # Query entirely stopwords → tokens empty → always on topic
    intent = parse_query("what is the")
    atom = Atom(kind="fact", source="user", subject="anything", content="x")
    assert intent.is_on_topic(atom) is True
