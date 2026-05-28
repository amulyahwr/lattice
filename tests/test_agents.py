"""
Agent integration tests — all LLM calls are mocked via patch("lattice.llm.complete").
Tests verify external behavior: atoms created, supersession links, selection results, synthesis output.
"""

import json
from datetime import date
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from lattice.db import LatticeDB
from lattice.ingest import ingest
from lattice.selection import select
from lattice.synthesis import synthesize


@pytest.fixture()
def db(tmp_path):
    return LatticeDB(lattice_dir=tmp_path)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ingest_response(atoms: list[dict]) -> str:
    return json.dumps({"atoms": atoms})


def _supersession_response(atom_id: str | None) -> str:
    return json.dumps({"superseded_atom_id": atom_id})


# ── ingest ────────────────────────────────────────────────────────────────────

class TestIngest:
    def test_creates_atoms_in_db(self, db):
        llm_atoms = [
            {"subject": "lattice-mcp", "kind": "fact", "source": "user",
             "content": "lattice-mcp is a local MCP server.", "valid_from": None, "valid_until": None},
        ]
        # extract_atoms (no supersession: first atom for this subject)
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest("lattice-mcp is a local MCP server.", db=db)

        assert result["atoms_created"] == 1
        assert len(result["atom_ids"]) == 1
        atom = db.read(result["atom_ids"][0])
        assert atom.subject == "lattice-mcp"
        assert "local MCP server" in atom.content

    def test_metadata_stored_on_atom(self, db):
        llm_atoms = [
            {"subject": "Project", "kind": "doc", "source": "document",
             "content": "Project readme.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest("Project readme.", metadata={"title": "README"}, db=db)

        atom = db.read(result["atom_ids"][0])
        assert atom.metadata.get("title") == "README"
        assert atom.source_title == "README"
        assert atom.source_id == result["source_id"]
        assert atom.ingested_at is not None
        assert atom.content_hash
        assert atom.normalized_content_hash

    def test_multiple_atoms_from_one_ingest(self, db):
        llm_atoms = [
            {"subject": "A", "kind": "fact", "source": "user", "content": "A is true.", "valid_from": None, "valid_until": None},
            {"subject": "B", "kind": "fact", "source": "user", "content": "B is false.", "valid_from": None, "valid_until": None},
        ]
        # no supersession calls: first atoms on each subject → db.by_subject() returns []
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest("A is true. B is false.", db=db)

        assert result["atoms_created"] == 2
        all_ids = {a.atom_id for a in db.all()}
        for aid in result["atom_ids"]:
            assert aid in all_ids

    def test_supersession_links_atoms(self, db):
        # First ingest: create old atom (no supersession: no existing atoms for "API")
        old_atoms = [
            {"subject": "API", "kind": "fact", "source": "user",
             "content": "The API uses REST.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(old_atoms)]):
            old_result = ingest("The API uses REST.", db=db)

        old_id = old_result["atom_ids"][0]

        # Second ingest: supersedes old atom (fast path: subject in registry → LLM call)
        new_atoms = [
            {"subject": "API", "kind": "fact", "source": "user",
             "content": "The API now uses GraphQL.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[
            _ingest_response(new_atoms),
            _supersession_response(old_id),
        ]):
            new_result = ingest("The API now uses GraphQL.", db=db)

        new_id = new_result["atom_ids"][0]
        old_atom = db.read(old_id)
        new_atom = db.read(new_id)

        assert old_atom.is_superseded is True
        assert old_atom.superseded_by == new_id
        assert new_atom.supersedes == old_id

    def test_date_fields_parsed(self, db):
        llm_atoms = [
            {"subject": "Offer", "kind": "event", "source": "user",
             "content": "Special offer.", "valid_from": "2024-06-01", "valid_until": "2024-06-30"},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest("Special offer valid June 2024.", db=db)

        atom = db.read(result["atom_ids"][0])
        assert atom.valid_from == date(2024, 6, 1)
        assert atom.valid_until == date(2024, 6, 30)

    def test_exact_duplicate_skipped(self, db):
        llm_atoms = [
            {"subject": "Project", "kind": "fact", "source": "user",
             "content": "Project uses Python.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            first = ingest("Project uses Python.", db=db)
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            second = ingest("Project uses Python.", db=db)

        assert first["atoms_created"] == 1
        assert second["atoms_created"] == 0
        assert second["duplicates_skipped"] == 1
        assert second["duplicate_atom_ids"] == first["atom_ids"]

    def test_source_type_and_observed_at_from_metadata(self, db):
        llm_atoms = [
            {"subject": "Roadmap", "kind": "doc", "source": "document",
             "content": "Roadmap has three phases.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest(
                "# Roadmap\n\nRoadmap has three phases.",
                metadata={
                    "source_id": "src-roadmap",
                    "source_type": "markdown",
                    "observed_at": "2024-06-01T00:00:00+00:00",
                },
                db=db,
            )

        atom = db.read(result["atom_ids"][0])
        assert atom.source_id == "src-roadmap"
        assert atom.source_type == "markdown"
        assert atom.observed_at is not None
        assert atom.source_span == {"start": 0, "end": len("# Roadmap\n\nRoadmap has three phases.")}

    def test_observed_at_parses_eval_date_format(self, db):
        llm_atoms = [
            {"subject": "Festival", "kind": "event", "source": "conversation",
             "content": "Festival details were discussed.", "valid_from": None, "valid_until": None},
        ]
        with patch("lattice.ingest.complete", side_effect=[_ingest_response(llm_atoms)]):
            result = ingest(
                "Festival details were discussed.",
                metadata={"source": "conversation", "date": "2023/05/25 (Thu) 06:05"},
                db=db,
            )

        atom = db.read(result["atom_ids"][0])
        assert atom.observed_at is not None
        assert atom.observed_at.year == 2023
        assert atom.observed_at.month == 5
        assert atom.observed_at.day == 25


# ── selection ─────────────────────────────────────────────────────────────────

class TestSelect:
    def _seed(self, db):
        from lattice.models import Atom
        atoms = [
            Atom(kind="fact", source="user", subject="Python", content="Python is a high-level language."),
            Atom(kind="fact", source="user", subject="Rust", content="Rust is a systems language."),
            Atom(kind="fact", source="user", subject="Cooking", content="Pasta is boiled in water."),
        ]
        for a in atoms:
            db.write(a)
        return atoms

    def test_returns_relevant_atoms(self, db):
        atoms = self._seed(db)
        python_id = atoms[0].atom_id
        result = select("tell me about Python", db=db)
        assert result[0]["atom_id"] == python_id

    def test_result_has_required_fields(self, db):
        atoms = self._seed(db)
        result = select("Python", db=db)
        keys = set(result[0].keys())
        assert {"atom_id", "subject", "content", "kind", "source"}.issubset(keys)
        assert {"source_id", "source_title", "segment_id", "observed_at"}.issubset(keys)

    def test_empty_db_returns_empty(self, db):
        result = select("anything", db=db)
        assert result == []

    def test_uses_bm25_without_llm_selector(self, db):
        self._seed(db)
        result = select("programming language", db=db)
        assert isinstance(result, list)
        assert result

    def test_as_of_filters_before_llm(self, db):
        from lattice.models import Atom
        expired = Atom(
            kind="fact", source="user", subject="Price",
            content="Price is $10.", valid_until=date(2023, 12, 31),
        )
        db.write(expired)
        result = select("price", as_of=date(2024, 6, 1), db=db)
        assert all(r["atom_id"] != expired.atom_id for r in result)

    def test_expands_via_semantic_and_segment_edges(self, db):
        """Hybrid BFS: same-segment siblings included (structural depth 2);
        cross-segment atoms included via same_subject_as (semantic);
        cross-source atoms excluded unless connected by semantic edge."""
        from lattice.models import Atom
        # "xyzdecorator" appears only in seed — guarantees BM25 top_k=1 always returns seed
        seed = Atom(
            kind="fact", source="user", subject="Python",
            content="Python supports xyzdecorators.",
            source_id="src-1", session_id="sess-1", segment_id="seg-1",
            source_span={"start": 100, "end": 130},
        )
        # Same segment — included via structural depth-2 expansion
        same_segment = Atom(
            kind="fact", source="user", subject="Python testing",
            content="Pytest fixtures help test Python code.",
            source_id="src-1", session_id="sess-1", segment_id="seg-1",
            source_span={"start": 131, "end": 180},
        )
        # Same subject, different segment — included via same_subject_as
        same_subject = Atom(
            kind="fact", source="user", subject="Python",
            content="Python wraps functions at definition time.",
            source_id="src-1", session_id="sess-1", segment_id="seg-2",
            source_span={"start": 200, "end": 250},
        )
        # Different source, no semantic connection — excluded
        unrelated = Atom(
            kind="fact", source="user", subject="JavaScript",
            content="JavaScript uses arrow functions.",
            source_id="src-2", session_id="sess-2", segment_id="seg-3",
            source_span={"start": 0, "end": 50},
        )
        db.write(seed)
        db.write(same_segment)
        db.write(same_subject)
        db.write(unrelated)

        result = select("xyzdecorators", db=db, top_k=1)
        ids = [row["atom_id"] for row in result]
        assert seed.atom_id in ids
        assert same_segment.atom_id in ids    # co-located in same segment — included
        assert same_subject.atom_id in ids    # semantic neighbor — included
        assert unrelated.atom_id not in ids   # different source, no connection — excluded

    def test_single_session_triggers_pointed_path(self, db):
        """All probe seeds from one session → pointed path → atom count ≤ _POINTED_MAX."""
        from lattice.models import Atom
        from lattice.selection import _POINTED_MAX
        for i in range(20):
            db.write(Atom(
                kind="fact", source="user", subject=f"widget {i}",
                content=f"Widget {i} is a component.",
                session_id="sess-single",
            ))
        result = select("widget component", db=db)
        assert len(result) <= _POINTED_MAX

    def test_multi_session_triggers_expansion_path(self, db):
        """Probe seeds from multiple sessions → expansion path → atoms from all sessions returned."""
        from lattice.models import Atom
        # 3 atoms in sess-A + 4 in sess-B = 7 total, all match query → probe has both sessions
        ids_a, ids_b = [], []
        for i in range(3):
            a = Atom(kind="fact", source="user", subject=f"gadget {i}",
                     content=f"Gadget {i} is a device.", session_id="sess-A")
            db.write(a)
            ids_a.append(a.atom_id)
        for i in range(4):
            b = Atom(kind="fact", source="user", subject=f"gadget {i} alt",
                     content=f"Gadget {i} alt is a device.", session_id="sess-B")
            db.write(b)
            ids_b.append(b.atom_id)

        result = select("gadget device", db=db)
        result_ids = {r["atom_id"] for r in result}
        assert any(aid in result_ids for aid in ids_a)
        assert any(aid in result_ids for aid in ids_b)


# ── synthesis ─────────────────────────────────────────────────────────────────

def _mock_completion(answer: str):
    """Return a mock openai ChatCompletion with no tool calls."""
    msg = MagicMock()
    msg.tool_calls = None
    msg.content = answer
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestSynthesize:
    def test_returns_string(self):
        atoms = [{"subject": "Python", "kind": "fact", "content": "Python is dynamically typed."}]
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_API_KEY": "test"}), \
             patch("lattice.synthesis.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _mock_completion("Python is dynamically typed.")
            result = synthesize("What is Python?", atoms)
        assert isinstance(result.answer, str)
        assert len(result.answer) > 0

    def test_empty_atoms_returns_no_info_message(self):
        result = synthesize("What is Python?", [])
        assert "no relevant" in result.answer.lower() or "not found" in result.answer.lower() or "no" in result.answer.lower()

    def test_empty_atoms_has_empty_raw_response(self):
        result = synthesize("What is Python?", [])
        assert result.raw_response == ""

    def test_raw_response_captured(self):
        atoms = [{"subject": "Python", "kind": "fact", "content": "Python is dynamically typed."}]
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_API_KEY": "test"}), \
             patch("lattice.synthesis.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _mock_completion("Python is dynamically typed.")
            result = synthesize("What is Python?", atoms)
        assert result.raw_response == result.answer

    def test_passes_query_and_atoms_to_llm(self):
        atoms = [{"subject": "X", "kind": "fact", "content": "X is true."}]
        with patch.dict("os.environ", {"LLM_PROVIDER": "openai", "LLM_API_KEY": "test"}), \
             patch("lattice.synthesis.OpenAI") as mock_cls:
            mock_cls.return_value.chat.completions.create.return_value = _mock_completion("X is true.")
            synthesize("Tell me about X.", atoms)
        create_call = mock_cls.return_value.chat.completions.create.call_args
        messages = create_call.kwargs.get("messages") or create_call.args[0]
        combined = " ".join(m["content"] for m in messages if isinstance(m.get("content"), str))
        assert "Tell me about X." in combined
        assert "X is true." in combined
