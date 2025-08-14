from typing import Dict, List, Set

import pytest

from ngraph.algorithms.base import EdgeSelect
from ngraph.graph.strict_multidigraph import EdgeID, NodeID, StrictMultiDiGraph
from ngraph.paths.bundle import Path, PathBundle


@pytest.fixture
def triangle1():
    """A small triangle graph for testing basic path operations."""
    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")
    g.add_edge("A", "B", cost=1, capacity=15, key=0)
    g.add_edge("B", "A", cost=1, capacity=15, key=1)
    g.add_edge("B", "C", cost=1, capacity=15, key=2)
    g.add_edge("C", "B", cost=1, capacity=15, key=3)
    g.add_edge("A", "C", cost=1, capacity=5, key=4)
    g.add_edge("C", "A", cost=1, capacity=5, key=5)
    return g


class TestPathBundle:
    def test_path_bundle_1(self):
        path_bundle = PathBundle(
            "A",
            "C",
            {
                "A": {},
                "C": {"B": [1], "D": [3]},
                "B": {"A": [0]},
                "D": {"A": [2]},
                "E": {"A": [4]},
            },
            2,
        )
        assert path_bundle.pred == {
            "A": {},
            "C": {"B": [1], "D": [3]},
            "B": {"A": [0]},
            "D": {"A": [2]},
        }

    def test_path_bundle_2(self):
        path_bundle = PathBundle(
            "A",
            "C",
            {
                "A": {},
                "C": {"B": [1, 5], "D": [3, 6, 7]},
                "B": {"A": [0, 8]},
                "D": {"A": [2]},
                "E": {"A": [4]},
            },
            2,
        )

        assert [path for path in path_bundle.resolve_to_paths()] == [
            Path((("A", (0, 8)), ("B", (1, 5)), ("C", ())), 2),
            Path((("A", (2,)), ("D", (3, 6, 7)), ("C", ())), 2),
        ]

        assert [
            path for path in path_bundle.resolve_to_paths(split_parallel_edges=True)
        ] == [
            Path((("A", (0,)), ("B", (1,)), ("C", ())), 2),
            Path((("A", (0,)), ("B", (5,)), ("C", ())), 2),
            Path((("A", (8,)), ("B", (1,)), ("C", ())), 2),
            Path((("A", (8,)), ("B", (5,)), ("C", ())), 2),
            Path((("A", (2,)), ("D", (3,)), ("C", ())), 2),
            Path((("A", (2,)), ("D", (6,)), ("C", ())), 2),
            Path((("A", (2,)), ("D", (7,)), ("C", ())), 2),
        ]

    def test_path_bundle_3(self):
        path_bundle = PathBundle(
            "A",
            "C",
            {
                "A": {},
                "C": {"B": [2, 3]},
                "B": {"A": [0, 1]},
            },
            2,
        )

        paths: List[Path] = [
            path for path in path_bundle.resolve_to_paths(split_parallel_edges=False)
        ]

        assert len(paths) == 1
        assert paths[0].cost == 2
        assert paths[0].edges == {0, 1, 2, 3}
        assert paths[0].nodes == {"A", "B", "C"}

    def test_path_bundle_4(self):
        path_bundle = PathBundle.from_path(
            Path((("A", (0,)), ("B", (1,)), ("C", ())), 2)
        )
        assert path_bundle.pred == {
            "A": {},
            "C": {"B": [1]},
            "B": {"A": [0]},
        }
        assert path_bundle.cost == 2

    def test_path_bundle_5(self, triangle1):
        path_bundle = PathBundle.from_path(
            Path((("A", ()), ("B", ()), ("C", ())), 2),
            resolve_edges=True,
            graph=triangle1,
            edge_select=EdgeSelect.ALL_MIN_COST,
        )
        assert path_bundle.pred == {
            "A": {},
            "C": {"B": [2]},
            "B": {"A": [0]},
        }
        assert path_bundle.cost == 2

    def test_get_sub_bundle_1(self, triangle1):
        path_bundle = PathBundle.from_path(
            Path((("A", ()), ("B", ()), ("C", ())), 2),
            resolve_edges=True,
            graph=triangle1,
            edge_select=EdgeSelect.ALL_MIN_COST,
        )
        sub_bundle = path_bundle.get_sub_path_bundle("B", triangle1)
        assert sub_bundle.pred == {
            "A": {},
            "B": {"A": [0]},
        }
        assert sub_bundle.cost == 1

    def test_get_sub_bundle_2(self, triangle1):
        path_bundle = PathBundle.from_path(
            Path((("A", ()), ("B", ()), ("C", ())), 2),
            resolve_edges=True,
            graph=triangle1,
            edge_select=EdgeSelect.ALL_MIN_COST,
        )
        sub_bundle = path_bundle.get_sub_path_bundle("A", triangle1)
        assert sub_bundle.pred == {
            "A": {},
        }
        assert sub_bundle.cost == 0

    def test_get_sub_bundle_min_cost_across_alternatives(self):
        g = StrictMultiDiGraph()
        for n in ("A", "B", "C", "D"):
            g.add_node(n)

        # Two routes A->D: A->C->D cost 2 (1+1), A->B->D cost 20 (10+10)
        e_ac = g.add_edge("A", "C", cost=1)
        e_cd = g.add_edge("C", "D", cost=1)
        e_ab = g.add_edge("A", "B", cost=10)
        e_bd = g.add_edge("B", "D", cost=10)

        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {
            "A": {},
            "C": {"A": [e_ac]},
            "B": {"A": [e_ab]},
            "D": {"C": [e_cd], "B": [e_bd]},
        }

        bundle = PathBundle("A", "D", pred, cost=2)
        sub = bundle.get_sub_path_bundle("D", g, cost_attr="cost")
        assert sub.cost == 2

    def test_get_sub_bundle_src_equals_dst_zero_cost(self):
        g = StrictMultiDiGraph()
        g.add_node("A")
        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {"A": {}}
        bundle = PathBundle("A", "A", pred, cost=0)
        sub = bundle.get_sub_path_bundle("A", g)
        assert sub.cost == 0

    def test_get_sub_bundle_raises_when_src_unreachable_in_subgraph(self):
        g = StrictMultiDiGraph()
        for n in ("A", "B", "C"):
            g.add_node(n)
        # pred missing any chain from A to C (only B->C exists)
        e_bc = g.add_edge("B", "C", cost=1)
        pred: Dict[NodeID, Dict[NodeID, List[EdgeID]]] = {
            "A": {},
            "B": {},
            "C": {"B": [e_bc]},
        }
        bundle = PathBundle("A", "C", pred, cost=0)
        with pytest.raises(ValueError, match="No path from 'A' to 'C'"):
            _ = bundle.get_sub_path_bundle("C", g)

    def test_add_method(self):
        """Test concatenating two PathBundles with matching src/dst."""
        pb1 = PathBundle(
            "A",
            "B",
            {
                "A": {},
                "B": {"A": [0]},
            },
            cost=3,
        )
        pb2 = PathBundle(
            "B",
            "C",
            {
                "B": {},
                "C": {"B": [1]},
            },
            cost=4,
        )
        new_pb = pb1.add(pb2)
        # new_pb should be A->C with cost=7
        assert new_pb.src_node == "A"
        assert new_pb.dst_node == "C"
        assert new_pb.cost == 7
        assert new_pb.pred == {
            "A": {},
            "B": {"A": [0]},
            "C": {"B": [1]},
        }

    def test_contains_subset_disjoint(self):
        """Test contains, is_subset_of, and is_disjoint_from."""
        pb_base = PathBundle(
            "X",
            "Z",
            {
                "X": {},
                "Y": {"X": [1]},
                "Z": {"Y": [2]},
            },
            cost=10,
        )
        pb_small = PathBundle(
            "X",
            "Z",
            {
                "X": {},
                "Y": {"X": [1]},
                "Z": {"Y": [2]},
            },
            cost=10,
        )
        # They have the same edges
        assert pb_base.contains(pb_small) is True
        assert pb_small.contains(pb_base) is True
        assert pb_small.is_subset_of(pb_base) is True
        assert pb_base.is_subset_of(pb_small) is True
        assert pb_small.is_disjoint_from(pb_base) is False

        # Now create a partial subset
        pb_partial = PathBundle(
            "X",
            "Y",
            {
                "X": {},
                "Y": {"X": [1]},
            },
            cost=5,
        )
        # pb_partial edges is {1} while pb_base edges is {1, 2}
        assert pb_base.contains(pb_partial) is True
        assert pb_partial.contains(pb_base) is False
        assert pb_partial.is_subset_of(pb_base) is True
        assert pb_base.is_subset_of(pb_partial) is False

        # Now a disjoint
        pb_disjoint = PathBundle(
            "R",
            "S",
            {
                "R": {},
                "S": {"R": [9]},
            },
            cost=2,
        )
        assert pb_base.is_disjoint_from(pb_disjoint) is True
        assert pb_disjoint.is_disjoint_from(pb_base) is True

    def test_ordering_and_hash_contract(self):
        """Equality, ordering by cost, and hash set behavior for `PathBundle`."""
        pb1 = PathBundle("A", "B", {"A": {}, "B": {"A": [11]}}, cost=5)
        pb2 = PathBundle("A", "B", {"A": {}, "B": {"A": [11]}}, cost=5)
        pb3 = PathBundle("A", "B", {"A": {}, "B": {"A": [11, 12]}}, cost=5)
        pb4 = PathBundle("A", "B", {"A": {}, "B": {"A": [11]}}, cost=6)

        # Equality driven by (src, dst, cost, edges)
        assert pb1 == pb2
        assert pb1 != pb3
        assert pb1 != pb4

        # Ordering by cost only
        assert pb1 < pb4
        assert not (pb4 < pb1)

        # Hash respects equality
        unique: Set[PathBundle] = {pb1, pb2, pb3, pb4}
        assert len(unique) == 3
