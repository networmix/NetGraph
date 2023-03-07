# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.spf import spf, ksp
from ngraph.lib.common import EdgeSelect, edge_select_fabric
from ..sample_data.sample_graphs import *


class TestSPF:
    def test_spf_1(self, line1):
        costs, pred = spf(line1, "A")
        assert costs == {"A": 0, "B": 1, "C": 2}
        assert pred == {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}}

    def test_spf_2(self, square1):
        costs, pred = spf(square1, "A")
        assert costs == {"A": 0, "B": 1, "D": 2, "C": 2}
        assert pred == {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1]}}

    def test_spf_3(self, square2):
        costs, pred = spf(square2, "A")
        assert costs == {"A": 0, "B": 1, "D": 1, "C": 2}
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "D": {"A": [2]},
            "C": {"B": [1], "D": [3]},
        }

    def test_spf_4(self, graph3):
        costs, pred = spf(graph3, "A")
        assert costs == {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3}
        assert pred == {
            "A": {},
            "B": {"A": [0, 1, 2]},
            "E": {"A": [7]},
            "D": {"A": [9], "C": [6], "F": [11]},
            "C": {"B": [3, 4, 5], "E": [8]},
            "F": {"C": [10]},
        }

    def test_spf_5(self, graph3):
        costs, pred = spf(
            graph3,
            "A",
            edge_select_func=edge_select_fabric(EdgeSelect.SINGLE_MIN_COST),
            multipath=False,
        )
        assert costs == {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3}
        assert pred == {
            "A": {},
            "B": {"A": [0]},
            "E": {"A": [7]},
            "D": {"A": [9]},
            "C": {"B": [3]},
            "F": {"C": [10]},
        }


class TestKSP:
    def test_ksp_1(self, line1):
        paths = list(ksp(line1, "A", "C", multipath=True))

        assert paths == [
            ({"A": 0, "B": 1, "C": 2}, {"A": {}, "B": {"A": [0]}, "C": {"B": [2, 4]}}),
            ({"A": 0, "B": 1, "C": 3}, {"A": {}, "B": {"A": [0]}, "C": {"B": [6]}}),
        ]

    def test_ksp_2(self, square1):
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
        paths = list(ksp(square2, "A", "C", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "D": 1, "C": 2},
                {"A": {}, "B": {"A": [0]}, "D": {"A": [2]}, "C": {"B": [1], "D": [3]}},
            )
        ]

    def test_ksp_4(self, graph3):
        paths = list(ksp(graph3, "A", "D", multipath=True))

        assert paths == [
            (
                {"A": 0, "B": 1, "E": 1, "D": 4, "C": 2, "F": 3},
                {
                    "A": {},
                    "B": {"A": [0, 1, 2]},
                    "E": {"A": [7]},
                    "D": {"A": [9], "C": [6], "F": [11]},
                    "C": {"B": [3, 4, 5], "E": [8]},
                    "F": {"C": [10]},
                },
            )
        ]

    def test_ksp_5(self, graph5):
        paths = list(ksp(graph5, "A", "B", multipath=True))

        visited = set()
        for path in paths:
            costs, pred = path
            edge_ids = tuple(
                sorted(
                    [
                        edge_id
                        for _, v1 in pred.items()
                        for _, edge_list in v1.items()
                        for edge_id in edge_list
                    ]
                )
            )
            if edge_ids not in visited:
                visited.add(edge_ids)
            else:
                raise Exception(f"Duplicate path found: {edge_ids}")
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
        paths = list(ksp(graph5, "A", "B", multipath=True, max_path_cost_factor=3))

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
        ]

    def test_ksp_9(self, graph5):
        paths = list(ksp(graph5, "A", "B", multipath=True, max_path_cost=0.5))

        assert paths == []

    def test_ksp_10(self, graph5):
        paths = list(ksp(graph5, "A", "B", multipath=False, max_path_cost=2))

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
                    "B": {"C": [9]},
                    "C": {"A": [1]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 2, "D": 1, "E": 1},
                {
                    "A": {},
                    "B": {"D": [13]},
                    "C": {"D": [14]},
                    "D": {"A": [2]},
                    "E": {"A": [3]},
                },
            ),
            (
                {"A": 0, "B": 2, "C": 2, "D": 2, "E": 1},
                {
                    "A": {},
                    "B": {"E": [17]},
                    "C": {"E": [18]},
                    "D": {"E": [19]},
                    "E": {"A": [3]},
                },
            ),
        ]

    def test_ksp_11(self, square5):
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
        paths = list(ksp(square5, "A", "E", multipath=True))

        assert paths == []
