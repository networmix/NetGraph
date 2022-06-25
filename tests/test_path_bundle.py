# pylint: disable=protected-access,invalid-name
from typing import List

from ngraph.path_bundle import Path, PathBundle


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
            path for path in path_bundle.resolve_to_paths(resolve_parallel_edges=True)
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
            path for path in path_bundle.resolve_to_paths(resolve_parallel_edges=False)
        ]

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
