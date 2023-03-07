# pylint: disable=protected-access,invalid-name
import pytest
from typing import List
from ngraph.lib.graph import MultiDiGraph

from ngraph.lib.path_bundle import Path, PathBundle
from ngraph.lib.common import EdgeSelect


@pytest.fixture
def triangle1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=15, label="1")
    g.add_edge("B", "A", metric=1, capacity=15, label="1")
    g.add_edge("B", "C", metric=1, capacity=15, label="2")
    g.add_edge("C", "B", metric=1, capacity=15, label="2")
    g.add_edge("A", "C", metric=1, capacity=5, label="3")
    g.add_edge("C", "A", metric=1, capacity=5, label="3")
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
