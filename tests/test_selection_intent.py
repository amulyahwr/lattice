"""Tests: QueryIntent drives selection — recommendation cap bypass and kind-fallback topic filter."""
from __future__ import annotations

import pytest

from pathlib import Path

from lattice.config import Config
from lattice.db import LatticeDB
from lattice.models import Atom
from lattice.selection import select


@pytest.fixture()
def db(tmp_path):
    return LatticeDB(lattice_dir=tmp_path)


def _cfg(tmp_path, **kw):
    return Config(lattice_dir=Path(tmp_path), llm_provider="ollama", llm_model="test-model", **kw)


class TestRecommendationCapBypass:
    def test_cap_applied_for_factual_query(self, db, tmp_path):
        cfg = _cfg(tmp_path, recommendation_cap=2)
        for i in range(5):
            db.write(Atom(kind="recommendation", source="user",
                          subject=f"rec {i}", content=f"Try thing {i}."))
        result = select("what are things", db=db, cfg=cfg)
        rec_atoms = [a for a in result if a["kind"] == "recommendation"]
        assert len(rec_atoms) <= 2

    def test_cap_bypassed_for_recommendation_query(self, db, tmp_path):
        cfg = _cfg(tmp_path, recommendation_cap=2)
        for i in range(5):
            db.write(Atom(kind="recommendation", source="user",
                          subject=f"rec {i}", content=f"Try thing {i}."))
        result = select("what did you recommend or suggest", db=db, cfg=cfg)
        rec_atoms = [a for a in result if a["kind"] == "recommendation"]
        assert len(rec_atoms) > 2


class TestKindFallbackAddsKindAtoms:
    def test_kind_fallback_appends_preference_atoms_when_absent(self, db, tmp_path):
        """Kind-fallback appends all atoms of target kind when none appear in BFS result.

        Needs ≥10 corpus atoms so BM25Okapi IDF for "xyzqjj" (df=1) is non-zero:
        IDF = log((N-1+0.5)/(1+0.5)); N=2 → log(1)=0; N=10 → log(6)≈1.8 > 0.
        """
        cfg = _cfg(tmp_path, seed_min_score=0.05)
        # Padding atoms give the corpus enough size for BM25 IDF to be non-zero
        for i in range(8):
            db.write(Atom(kind="event", source="user", subject=f"pad {i}", content=f"padding {i}"))
        # Unique token "xyzqjj" only in fact_atom → scores > 0 after padding; pref_atom scores 0
        fact_atom = Atom(kind="fact", source="user",
                         subject="xyzqjj fact", content="xyzqjj is a unique system token.")
        pref_atom = Atom(kind="preference", source="user",
                         subject="coffee", content="Likes dark roast.")
        db.write(fact_atom)
        db.write(pref_atom)

        # PREFERENCE query + unique token → fact_atom is the only seed scoring > 0.05
        # → result has no preference atoms → kind-fallback fires → pref_atom appended
        result = select("prefer xyzqjj", db=db, cfg=cfg)
        atom_ids = {a["atom_id"] for a in result}
        assert pref_atom.atom_id in atom_ids


class TestAggregationPrimaryKind:
    def test_aggregation_query_retrieves_count_atoms(self, db, tmp_path):
        cfg = _cfg(tmp_path)
        count_atom = Atom(kind="count", source="user",
                          subject="gym visits", content="Went to the gym 12 times this month.")
        fact_atom = Atom(kind="fact", source="user",
                         subject="gym equipment", content="The gym has free weights.")
        db.write(count_atom)
        db.write(fact_atom)

        result = select("how many times did I go to the gym", db=db, cfg=cfg)
        atom_ids = {a["atom_id"] for a in result}
        assert count_atom.atom_id in atom_ids
