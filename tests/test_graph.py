import pytest

from lattice.db import LatticeDB
from lattice.graph import LatticeGraph
from lattice.models import Atom


def make_atom(subject="Alpha", content="Alpha does X.", **kwargs) -> Atom:
    return Atom(kind="fact", source="user", subject=subject, content=content, **kwargs)


@pytest.fixture()
def db(tmp_path):
    return LatticeDB(lattice_dir=tmp_path)


class TestAddAtomNodes:
    def test_atom_node_created(self):
        lg = LatticeGraph()
        a = make_atom()
        lg.add_atom(a)
        assert f"atom:{a.atom_id}" in lg.graph.nodes

    def test_subject_node_created(self):
        lg = LatticeGraph()
        a = make_atom(subject="Auth Module")
        lg.add_atom(a)
        assert "subject:auth module" in lg.graph.nodes

    def test_source_node_created(self):
        lg = LatticeGraph()
        a = make_atom(source_id="src-1")
        lg.add_atom(a)
        assert "source:src-1" in lg.graph.nodes

    def test_segment_node_created(self):
        lg = LatticeGraph()
        a = make_atom(source_id="src-1", segment_id="s0")
        lg.add_atom(a)
        assert "segment:src-1:s0" in lg.graph.nodes

    def test_segment_node_uses_session_when_no_source(self):
        lg = LatticeGraph()
        a = make_atom(session_id="sess-1", segment_id="s0")
        lg.add_atom(a)
        assert "segment:sess-1:s0" in lg.graph.nodes

    def test_no_segment_node_without_container(self):
        lg = LatticeGraph()
        a = make_atom(segment_id="s0")  # no source_id, no session_id
        lg.add_atom(a)
        nodes = list(lg.graph.nodes)
        assert not any(n.startswith("segment:") for n in nodes)

    def test_node_type_attributes(self):
        lg = LatticeGraph()
        a = make_atom(subject="Beta", source_id="src-2", segment_id="s1")
        lg.add_atom(a)
        assert lg.graph.nodes[f"atom:{a.atom_id}"]["type"] == "atom"
        assert lg.graph.nodes["source:src-2"]["type"] == "source"
        assert lg.graph.nodes["segment:src-2:s1"]["type"] == "segment"
        assert lg.graph.nodes["subject:beta"]["type"] == "subject"


class TestAddAtomEdges:
    def _edge_types(self, lg: LatticeGraph) -> set[str]:
        return {d["type"] for _, _, d in lg.graph.edges(data=True)}

    def test_atom_has_subject_edge(self):
        lg = LatticeGraph()
        a = make_atom(subject="Gamma")
        lg.add_atom(a)
        assert "atom_has_subject" in self._edge_types(lg)

    def test_source_contains_segment_edge(self):
        lg = LatticeGraph()
        a = make_atom(source_id="src-3", segment_id="s0")
        lg.add_atom(a)
        assert "source_contains_segment" in self._edge_types(lg)

    def test_segment_contains_atom_edge(self):
        lg = LatticeGraph()
        a = make_atom(source_id="src-3", segment_id="s0")
        lg.add_atom(a)
        assert "segment_contains_atom" in self._edge_types(lg)

    def test_same_hash_edge(self):
        lg = LatticeGraph()
        a1 = make_atom(subject="D1", normalized_content_hash="abc123")
        a2 = make_atom(subject="D2", normalized_content_hash="abc123")
        lg.add_atom(a1)
        lg.add_atom(a2)
        assert "same_hash" in self._edge_types(lg)


class TestSameSubjectBidirectional:
    def test_same_subject_edges_both_directions(self):
        lg = LatticeGraph()
        a1 = make_atom(subject="Auth Module", content="First fact.")
        a2 = make_atom(subject="Auth Module", content="Second fact.")
        lg.add_atom(a1)
        lg.add_atom(a2)
        n1 = f"atom:{a1.atom_id}"
        n2 = f"atom:{a2.atom_id}"
        edge_types_1_to_2 = {d["type"] for _, _, d in lg.graph.out_edges(n1, data=True)}
        edge_types_2_to_1 = {d["type"] for _, _, d in lg.graph.out_edges(n2, data=True)}
        assert "same_subject_as" in edge_types_1_to_2
        assert "same_subject_as" in edge_types_2_to_1

    def test_different_subject_no_same_subject_edge(self):
        lg = LatticeGraph()
        a1 = make_atom(subject="Auth")
        a2 = make_atom(subject="Database")
        lg.add_atom(a1)
        lg.add_atom(a2)
        n1 = f"atom:{a1.atom_id}"
        edge_types = {d["type"] for _, _, d in lg.graph.out_edges(n1, data=True)}
        assert "same_subject_as" not in edge_types


class TestMarkSuperseded:
    def test_supersedes_edge_added(self):
        lg = LatticeGraph()
        old = make_atom(subject="X", content="Old fact.")
        new = make_atom(subject="X", content="New fact.")
        lg.add_atom(old)
        lg.add_atom(new)
        lg.mark_superseded(old.atom_id, new.atom_id)
        edge_types = {d["type"] for _, _, d in lg.graph.edges(data=True)}
        assert "supersedes" in edge_types

    def test_old_node_marked_superseded(self):
        lg = LatticeGraph()
        old = make_atom(subject="Y", content="Old.")
        new = make_atom(subject="Y", content="New.")
        lg.add_atom(old)
        lg.add_atom(new)
        lg.mark_superseded(old.atom_id, new.atom_id)
        assert lg.graph.nodes[f"atom:{old.atom_id}"]["is_superseded"] is True

    def test_supersedes_direction(self):
        lg = LatticeGraph()
        old = make_atom(subject="Z", content="Old.")
        new = make_atom(subject="Z", content="New.")
        lg.add_atom(old)
        lg.add_atom(new)
        lg.mark_superseded(old.atom_id, new.atom_id)
        new_node = f"atom:{new.atom_id}"
        old_node = f"atom:{old.atom_id}"
        successors = list(lg.graph.successors(new_node))
        assert old_node in successors


class TestRebuild:
    def test_rebuild_same_as_incremental(self):
        atoms = [
            make_atom(subject="A", content="Fact A.", source_id="src-1", segment_id="s0"),
            make_atom(subject="A", content="Fact A2.", source_id="src-1", segment_id="s1"),
            make_atom(subject="B", content="Fact B.", source_id="src-2", segment_id="s0"),
        ]

        incremental = LatticeGraph()
        for a in atoms:
            incremental.add_atom(a)

        rebuilt = LatticeGraph()
        rebuilt.rebuild(atoms)

        assert set(incremental.graph.nodes) == set(rebuilt.graph.nodes)
        assert incremental.graph.number_of_edges() == rebuilt.graph.number_of_edges()

    def test_rebuild_clears_previous(self):
        lg = LatticeGraph()
        a = make_atom()
        lg.add_atom(a)
        lg.rebuild([])
        assert lg.graph.number_of_nodes() == 0


class TestSaveLoadRoundtrip:
    def test_node_count_preserved(self, tmp_path):
        lg = LatticeGraph()
        for i in range(3):
            lg.add_atom(make_atom(subject=f"Sub{i}", content=f"Content {i}.", source_id="src"))
        lg.save(tmp_path)
        loaded = LatticeGraph.load(tmp_path)
        assert loaded.graph.number_of_nodes() == lg.graph.number_of_nodes()

    def test_edge_count_preserved(self, tmp_path):
        lg = LatticeGraph()
        for i in range(3):
            lg.add_atom(make_atom(subject="Same", content=f"Content {i}."))
        lg.save(tmp_path)
        loaded = LatticeGraph.load(tmp_path)
        assert loaded.graph.number_of_edges() == lg.graph.number_of_edges()

    def test_node_types_preserved(self, tmp_path):
        lg = LatticeGraph()
        lg.add_atom(make_atom(subject="Proj", source_id="s1", segment_id="seg0"))
        lg.save(tmp_path)
        loaded = LatticeGraph.load(tmp_path)
        types = {d["type"] for _, d in loaded.graph.nodes(data=True)}
        assert types == {"atom", "subject", "source", "segment"}

    def test_edge_types_preserved(self, tmp_path):
        lg = LatticeGraph()
        lg.add_atom(make_atom(subject="Proj", source_id="s1", segment_id="seg0"))
        lg.save(tmp_path)
        loaded = LatticeGraph.load(tmp_path)
        edge_types = {d["type"] for _, _, d in loaded.graph.edges(data=True)}
        assert "atom_has_subject" in edge_types
        assert "source_contains_segment" in edge_types
        assert "segment_contains_atom" in edge_types

    def test_manifest_written(self, tmp_path):
        lg = LatticeGraph()
        lg.add_atom(make_atom())
        lg.save(tmp_path)
        assert (tmp_path / "graph" / "manifest.json").exists()


class TestStaleDetection:
    def test_stale_when_no_manifest(self, tmp_path):
        lg = LatticeGraph()
        assert lg.is_stale(tmp_path, 5) is True

    def test_not_stale_when_counts_match(self, tmp_path):
        lg = LatticeGraph()
        for i in range(3):
            lg.add_atom(make_atom(subject=f"S{i}", content=f"C {i}."))
        lg.save(tmp_path)
        assert lg.is_stale(tmp_path, 3) is False

    def test_stale_when_count_differs(self, tmp_path):
        lg = LatticeGraph()
        for i in range(3):
            lg.add_atom(make_atom(subject=f"S{i}", content=f"C {i}."))
        lg.save(tmp_path)
        assert lg.is_stale(tmp_path, 5) is True


class TestDBIntegration:
    def test_db_write_updates_graph(self, db):
        db.preload()
        a = make_atom()
        db.write(a)
        assert db.graph is not None
        assert f"atom:{a.atom_id}" in db.graph.graph.nodes

    def test_db_preload_populates_graph(self, tmp_path):
        # Write atoms to disk first, then preload fresh db
        db1 = LatticeDB(lattice_dir=tmp_path)
        a1 = make_atom(subject="Preload1", content="Fact one.")
        a2 = make_atom(subject="Preload2", content="Fact two.")
        db1.write(a1)
        db1.write(a2)

        db2 = LatticeDB(lattice_dir=tmp_path)
        db2.preload()
        assert db2.graph is not None
        assert f"atom:{a1.atom_id}" in db2.graph.graph.nodes
        assert f"atom:{a2.atom_id}" in db2.graph.graph.nodes

    def test_db_preload_rebuilds_when_stale(self, tmp_path):
        # Save a graph with wrong atom count
        lg = LatticeGraph()
        import json
        manifest = {"version": 1, "atom_count": 999, "edge_count": 0, "built_at": "2020-01-01"}
        (tmp_path / "graph").mkdir()
        (tmp_path / "graph" / "manifest.json").write_text(json.dumps(manifest))

        db = LatticeDB(lattice_dir=tmp_path)
        a = make_atom()
        db.write(a)  # write without graph active (preload not called yet)
        db.preload()  # stale -> should rebuild
        assert db.graph is not None
        assert f"atom:{a.atom_id}" in db.graph.graph.nodes

    def test_db_supersede_adds_edge(self, db):
        db.preload()
        old = make_atom(subject="Topic", content="Old fact.")
        new = make_atom(subject="Topic", content="New fact.")
        db.write(old)
        db.supersede(old.atom_id, new)
        edge_types = {d["type"] for _, _, d in db.graph.graph.edges(data=True)}
        assert "supersedes" in edge_types
