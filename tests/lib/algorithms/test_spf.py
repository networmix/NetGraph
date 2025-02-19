import pytest
from ngraph.lib.algorithms.spf import spf, ksp
from ngraph.lib.algorithms.edge_select import EdgeSelect, edge_select_fabric
from tests.lib.algorithms.sample_graphs import *


class TestSPF:
    def test_spf_1(self, line1):
        """Test SPF on the 'line1' fixture."""
        costs, pred = spf(line1, "A")
        assert costs == {"A": 0, "B": 1, "C": 2}
        # numeric edge IDs: B is reached by [0], then C is reached by [2,4]
        assert pred == {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}}

    def test_spf_2(self, square1):
        """Test SPF on 'square1' fixture."""
        costs, pred = spf(square1, "A")
        assert costs == {"A": 0, "B": 1, "D": 2, "C": 2}
        # numeric edge IDs: B from [0], D from [2], C from [1]
        assert pred == {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1]}}

    def test_spf_3(self, square2):
        """Test SPF on 'square2' fixture."""
        costs, pred = spf(square2, "A")
        assert costs == {"A": 0, "B": 1, "D": 1, "C": 2}
        # B from [0], D from [2], C can come from B([1]) or D([3])
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "D": {"A": [2]},
            "C": {"B": [1], "D": [3]},
        }

    def test_spf_4(self, graph3):
        """Test SPF on 'graph3', which has parallel edges."""
        costs, pred = spf(graph3, "A")
        # minimal costs to each node
        assert costs == {"A": 0, "B": 1, "E": 1, "C": 2, "F": 3, "D": 4}
        # multiple parallel edges used: B from [0,1,2], C from [3,4,5], E->C=8, etc.
        assert pred == {
            "A": {},
            "B": {"A": [0, 1, 2]},
            "E": {"A": [7]},
            "C": {"B": [3, 4, 5], "E": [8]},
            "F": {"C": [10]},
            "D": {"A": [9], "C": [6], "F": [11]},
        }

    def test_spf_5(self, graph3):
        """
        Use SINGLE_MIN_COST selection and multipath=False on graph3.
        Picks exactly one minimal edge among parallel edges.
        """
        costs, pred = spf(
            graph3,
            src_node="A",
            edge_select_func=edge_select_fabric(EdgeSelect.SINGLE_MIN_COST),
            multipath=False,
        )
        assert costs == {"A": 0, "B": 1, "E": 1, "C": 2, "F": 3, "D": 4}
        # Chose first parallel edge to B => ID=0.
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "E": {"A": [7]},
            "C": {"B": [3]},
            "F": {"C": [10]},
            "D": {"A": [9]},
        }


class TestKSP:
    def test_ksp_1(self, line1):
        """KSP on 'line1' from A->C with multipath=True => 2 distinct paths."""
        paths = list(ksp(line1, "A", "C", multipath=True))
        assert paths == [
            (
                {"A": 0, "B": 1, "C": 2},
                {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}},
            ),
            (
                {"A": 0, "B": 1, "C": 3},
                {"A": {}, "B": {"A": [0]}, "C": {"B": [6]}},
            ),
        ]

    def test_ksp_2(self, square1):
        """KSP on 'square1' => 2 distinct paths from A->C."""
        paths = list(ksp(square1, "A", "C", multipath=True))
        assert paths == [
            (
                {"A": 0, "B": 1, "D": 2, "C": 2},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1]}},
            ),
            (
                {"A": 0, "B": 1, "D": 2, "C": 4},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"D": [3]}},
            ),
        ]

    def test_ksp_3(self, square2):
        """Only one distinct shortest path from A->C in 'square2' even with multipath=True."""
        paths = list(ksp(square2, "A", "C", multipath=True))
        assert paths == [
            (
                {"A": 0, "B": 1, "D": 1, "C": 2},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "D": {"A": [2]},
                    "C": {"B": [1], "D": [3]},
                },
            )
        ]

    def test_ksp_4(self, graph3):
        """KSP on graph3 from A->D => single best path in multipath mode."""
        paths = list(ksp(graph3, "A", "D", multipath=True))
        assert paths == [
            (
                {"A": 0, "B": 1, "E": 1, "C": 2, "F": 3, "D": 4},
                {
                    "A": {},
                    "B": {"A": [0, 1, 2]},
                    "E": {"A": [7]},
                    "C": {"B": [3, 4, 5], "E": [8]},
                    "F": {"C": [10]},
                    "D": {"A": [9], "C": [6], "F": [11]},
                },
            )
        ]

    def test_ksp_5(self, graph5):
        """
        KSP on fully connected 'graph5' from A->B in multipath => many distinct paths.
        We verify no duplicates and compare to a known set of 11 results.
        """
        paths = list(ksp(graph5, "A", "B", multipath=True))
        visited = set()
        for costs, pred in paths:
            edge_ids = tuple(
                sorted(
                    edge_id
                    for nbrs in pred.values()
                    for edge_list in nbrs.values()
                    for edge_id in edge_list
                )
            )
            if edge_ids in visited:
                raise Exception(f"Duplicate path found: {edge_ids}")
            visited.add(edge_ids)

        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 1, "D": 2, "E": 2},
                {
                    "A": {},
                    "B": {"D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"C": [10]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 1, "E": 2},
                {
                    "A": {},
                    "B": {"C": [9], "E": [17]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 3, "C": 2, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13]},
                    "C": {"E": [18]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 1, "D": 2, "E": 3},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"A": [1]},
                    "D": {"C": [10]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 1, "D": 3, "E": 2},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"A": [1]},
                    "D": {"E": [19]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 2, "D": 1, "E": 3},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"C": [11]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 3, "D": 1, "E": 2},
                {
                    "A": {},
                    "B": {"C": [9]},
                    "C": {"E": [18]},
                    "D": {"A": [2]},
                    "E": {"D": [15]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 2, "D": 3, "E": 1},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"E": [18]},
                    "D": {"C": [10]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 4, "C": 3, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9]},
                    "C": {"D": [14]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_6(self, graph5):
        """KSP with max_k=2 => only 2 shortest paths from A->B."""
        paths = list(ksp(graph5, "A", "B", multipath=True, max_k=2))
        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_7(self, graph5):
        """KSP with max_path_cost=2 => only paths <= cost=2 from A->B are returned."""
        paths = list(ksp(graph5, "A", "B", multipath=True, max_path_cost=2))
        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"A": [0]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"C": [9], "D": [13], "E": [17]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_8(self, graph5):
        """KSP with max_path_cost_factor=3 => expand cost limit beyond the best path cost."""
        paths = list(ksp(graph5, "A", "B", multipath=True, max_path_cost_factor=3))
        assert len(paths) == 5

    def test_ksp_9(self, graph5):
        """KSP with max_path_cost=0.5 => no paths since cost is at least 1."""
        paths = list(ksp(graph5, "A", "B", multipath=True, max_path_cost=0.5))
        assert paths == []

    def test_ksp_10(self, graph5):
        """KSP with multipath=False, max_path_cost=2 => partial expansions only."""
        paths = list(ksp(graph5, "A", "B", multipath=False, max_path_cost=2))
        assert len(paths) == 4

    def test_ksp_11(self, square5):
        """Multiple routes from A->D in 'square5'. Check expansions in multipath mode."""
        paths = list(ksp(square5, "A", "D", multipath=True))
        assert paths == [
            (
                {"A": 0, "B": 1, "C": 1, "D": 2},
                {"A": {}, "B": {"A": [0]}, "C": {"A": [1]}, "D": {"B": [2], "C": [3]}},
            ),
            (
                {"A": 0, "B": 1, "C": 2, "D": 3},
                {"A": {}, "B": {"A": [0]}, "C": {"B": [4]}, "D": {"C": [3]}},
            ),
            (
                {"A": 0, "B": 2, "C": 1, "D": 3},
                {"A": {}, "B": {"C": [5]}, "C": {"A": [1]}, "D": {"B": [2]}},
            ),
        ]

    def test_ksp_12(self, square5):
        """No route from A->E in 'square5', so we get an empty list."""
        paths = list(ksp(square5, "A", "E", multipath=True))
        assert paths == []
