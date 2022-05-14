# pylint: disable=protected-access,invalid-name
from algorithms.common import resolve_paths_to_nodes_edges
from algorithms.spf import spf
from ngraph.graph import MultiDiGraph
from ngraph.algorithms.flow import (
    FlowPlacement,
    NodeCapacity,
    PathAlgType,
    calc_capacity_balanced,
    init_residual_graph,
    calc_path_capacity,
    place_flow,
    calc_max_flow,
    PathCapacity,
    PathElementCapacity,
    place_flow_balanced,
)


class Test_Flow:
    def test_init_residual_graph_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=1)

        g.add_edge("B", "C1", metric=1, capacity=1)
        g.add_edge("B", "C2", metric=2, capacity=1)

        g.add_edge("C1", "D", metric=1, capacity=1)
        g.add_edge("C2", "D", metric=1, capacity=1)

        r = init_residual_graph(g.copy())
        assert r.get_edges() == {
            0: ("A", "B", 0, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            1: ("B", "C1", 1, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            2: ("B", "C2", 2, {"metric": 2, "capacity": 1, "flow": 0, "flows": {}}),
            3: ("C1", "D", 3, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
            4: ("C2", "D", 4, {"metric": 1, "capacity": 1, "flow": 0, "flows": {}}),
        }

    def test_calc_path_capacity_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=3)
        g.add_edge("B", "C", metric=1, capacity=1)
        g.add_edge("B", "C", metric=1, capacity=2)

        r = init_residual_graph(g.copy())
        assert calc_path_capacity(r, (("A", [0]), ("B", [1, 2]), ("C", [3]))) == (
            PathCapacity(max_flow=3, max_single_flow=2, max_balanced_flow=2),
            [
                PathElementCapacity(
                    node_id="A",
                    edges=[0],
                    total_cap=3,
                    max_edge_cap=3,
                    min_edge_cap=3,
                    max_edge_cap_id=0,
                    min_edge_cap_id=0,
                    total_rem_cap=3,
                    max_edge_rem_cap=3,
                    min_edge_rem_cap=3,
                    max_edge_rem_cap_id=0,
                    min_edge_rem_cap_id=0,
                    edge_count=1,
                ),
                PathElementCapacity(
                    node_id="B",
                    edges=[1, 2],
                    total_cap=3,
                    max_edge_cap=2,
                    min_edge_cap=1,
                    max_edge_cap_id=2,
                    min_edge_cap_id=1,
                    total_rem_cap=3,
                    max_edge_rem_cap=2,
                    min_edge_rem_cap=1,
                    max_edge_rem_cap_id=2,
                    min_edge_rem_cap_id=1,
                    edge_count=2,
                ),
            ],
        )

    def test_calc_path_capacity_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=1)
        g.add_edge("A", "B", metric=1, capacity=4)
        g.add_edge("A", "B", metric=1, capacity=6)
        g.add_edge("B", "C", metric=1, capacity=1)
        g.add_edge("B", "C", metric=1, capacity=2)
        g.add_edge("B", "C", metric=1, capacity=3)

        r = init_residual_graph(g.copy())
        print(
            calc_path_capacity(
                r, (("A", [0, 1, 2]), ("B", [3, 4, 5]), ("C", [6, 7, 8]))
            )
        )
        assert calc_path_capacity(
            r, (("A", [0, 1, 2]), ("B", [3, 4, 5]), ("C", [6, 7, 8]))
        ) == (
            PathCapacity(max_flow=6, max_single_flow=3, max_balanced_flow=3),
            [
                PathElementCapacity(
                    node_id="A",
                    edges=[0, 1, 2],
                    total_cap=11,
                    max_edge_cap=6,
                    min_edge_cap=1,
                    max_edge_cap_id=2,
                    min_edge_cap_id=0,
                    total_rem_cap=11,
                    max_edge_rem_cap=6,
                    min_edge_rem_cap=1,
                    max_edge_rem_cap_id=2,
                    min_edge_rem_cap_id=0,
                    edge_count=3,
                ),
                PathElementCapacity(
                    node_id="B",
                    edges=[3, 4, 5],
                    total_cap=6,
                    max_edge_cap=3,
                    min_edge_cap=1,
                    max_edge_cap_id=5,
                    min_edge_cap_id=3,
                    total_rem_cap=6,
                    max_edge_rem_cap=3,
                    min_edge_rem_cap=1,
                    max_edge_rem_cap_id=5,
                    min_edge_rem_cap_id=3,
                    edge_count=3,
                ),
            ],
        )

    def test_place_flow_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=1)

        g.add_edge("B", "C1", metric=1, capacity=1)
        g.add_edge("B", "C2", metric=2, capacity=1)

        g.add_edge("C1", "D", metric=1, capacity=1)
        g.add_edge("C2", "D", metric=1, capacity=1)

        r = init_residual_graph(g.copy())
        assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
            1,
            float("inf"),
        )

    def test_place_flow_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=2)

        g.add_edge("B", "C1", metric=1, capacity=1)
        g.add_edge("B", "C2", metric=2, capacity=1)

        g.add_edge("C1", "D", metric=1, capacity=0.5)
        g.add_edge("C2", "D", metric=1, capacity=0.5)

        r = init_residual_graph(g.copy())
        assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
            0.5,
            float("inf"),
        )
        assert place_flow(r, (("A", [0]), ("B", [1]), ("C1", [3]), ("D", []))) == (
            0,
            float("inf"),
        )


class Test_Flow_SPF_Proportional:
    def test_max_flow_spf_proportional_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=11, capacity=2)
        g.add_edge("A", "B", metric=10, capacity=2)

        g.add_edge("B", "C", metric=10, capacity=1)
        g.add_edge("B", "C", metric=10, capacity=1)

        g.add_edge("C", "D", metric=20, capacity=1)
        g.add_edge("C", "D", metric=10, capacity=1)

        max_flow, res_g = calc_max_flow(
            g,
            "A",
            "D",
            flow_placement=FlowPlacement.PROPORTIONAL,
            path_alg=PathAlgType.SPF,
        )
        assert max_flow == 2
        print(res_g.get_edges())
        assert res_g.get_edges() == {
            0: ("A", "B", 0, {"metric": 11, "capacity": 2, "flow": 0, "flows": {}}),
            1: (
                "A",
                "B",
                1,
                {
                    "metric": 10,
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {0: ("A", "D", 1.0), 1: ("A", "D", 1.0)},
                },
            ),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 0.5), 1: ("A", "D", 0.5)},
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 0.5), 1: ("A", "D", 0.5)},
                },
            ),
            4: (
                "C",
                "D",
                4,
                {
                    "metric": 20,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {1: ("A", "D", 1.0)},
                },
            ),
            5: (
                "C",
                "D",
                5,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
        }

    def test_max_flow_proportional_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=11, capacity=1)
        g.add_edge("A", "B", metric=10, capacity=2)

        g.add_edge("A", "C", metric=10, capacity=1)
        g.add_edge("A", "C", metric=10, capacity=3)

        g.add_edge("A", "D", metric=20, capacity=1)
        g.add_edge("B", "D", metric=10, capacity=1)
        g.add_edge("C", "D", metric=10, capacity=1)

        max_flow, _ = calc_max_flow(
            g, "A", "D", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 3

    def test_max_flow_proportional_3(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=11, capacity=1)
        g.add_edge("A", "B", metric=10, capacity=2)

        g.add_edge("A", "C", metric=10, capacity=1)
        g.add_edge("A", "C", metric=10, capacity=3)

        g.add_edge("A", "D", metric=20, capacity=1)
        g.add_edge("B", "D", metric=10, capacity=1)
        g.add_edge("C", "D", metric=10, capacity=5)

        max_flow, _ = calc_max_flow(
            g, "A", "D", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 6

    def test_max_flow_proportional_4(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=11, capacity=2)
        g.add_edge("A", "B", metric=10, capacity=2)

        g.add_edge("B", "C", metric=10, capacity=1)
        g.add_edge("B", "C", metric=10, capacity=1)

        g.add_edge("C", "D", metric=20, capacity=1)
        g.add_edge("C", "D", metric=10, capacity=1)

        max_flow, res_g = calc_max_flow(
            g, "A", "D", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert max_flow == 2
        print(res_g.get_edges())
        assert res_g.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 11,
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            1: (
                "A",
                "B",
                1,
                {
                    "metric": 10,
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            4: (
                "C",
                "D",
                4,
                {
                    "metric": 20,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            5: (
                "C",
                "D",
                5,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
        }


class Test_Flow_SPF_Proportional_BestOnly:
    def test_max_flow_spf_proportional_best_only_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=11, capacity=2)
        g.add_edge("A", "B", metric=10, capacity=2)

        g.add_edge("B", "C", metric=10, capacity=1)
        g.add_edge("B", "C", metric=10, capacity=1)

        g.add_edge("C", "D", metric=20, capacity=1)
        g.add_edge("C", "D", metric=10, capacity=1)

        max_flow, res_g = calc_max_flow(
            g,
            "A",
            "D",
            flow_placement=FlowPlacement.PROPORTIONAL,
            path_alg=PathAlgType.SPF,
            shortest_path=True,
        )
        assert max_flow == 1
        assert res_g.get_edges() == {
            0: ("A", "B", 0, {"metric": 11, "capacity": 2, "flow": 0, "flows": {}}),
            1: (
                "A",
                "B",
                1,
                {
                    "metric": 10,
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 0.5,
                    "flows": {0: ("A", "D", 0.5)},
                },
            ),
            3: (
                "B",
                "C",
                3,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 0.5,
                    "flows": {0: ("A", "D", 0.5)},
                },
            ),
            4: ("C", "D", 4, {"metric": 20, "capacity": 1, "flow": 0, "flows": {}}),
            5: (
                "C",
                "D",
                5,
                {
                    "metric": 10,
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {0: ("A", "D", 1.0)},
                },
            ),
        }

    def test_max_flow_spf_proportional_best_only_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=1, capacity=1)
        g.add_edge("A", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("A", "D", metric=3, capacity=2)

        r = init_residual_graph(g)
        max_flow, res_g = calc_max_flow(
            g,
            "A",
            "D",
            flow_placement=FlowPlacement.PROPORTIONAL,
            path_alg=PathAlgType.SPF,
            shortest_path=True,
        )
        assert max_flow == 3


class Test_Flow_Balanced:
    def test_calc_capacity_balanced_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=2, capacity=1)
        g.add_edge("A", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("A", "D", metric=4, capacity=2)
        g.add_edge("C", "F", metric=1, capacity=1)
        g.add_edge("F", "D", metric=1, capacity=2)

        _, pred = spf(g, "A")
        r = init_residual_graph(g)

        max_flow, node_cap = calc_capacity_balanced(r, "A", "D", pred)
        assert max_flow == 2.5
        assert node_cap == {
            "A": NodeCapacity(
                node_id="A",
                edges={0, 1, 2, 7, 9},
                edges_max_flow={(0, 1, 2): 2.0, (7,): 2.0, (9,): 2},
                max_balanced_flow=3.333333333333333,
                downstream_nodes={
                    (0, 1, 2): {"D", "F", "B", "C"},
                    (7,): {"E", "C", "F", "D"},
                    (9,): {"D"},
                },
                flow_fraction=1,
            ),
            "B": NodeCapacity(
                node_id="B",
                edges={3, 4, 5},
                edges_max_flow={(3, 4, 5): 2.0},
                max_balanced_flow=2.0,
                downstream_nodes={(3, 4, 5): {"D", "F", "C"}},
                flow_fraction=0.6000000000000001,
            ),
            "C": NodeCapacity(
                node_id="C",
                edges={10, 6},
                edges_max_flow={(6,): 1, (10,): 1},
                max_balanced_flow=2.0,
                downstream_nodes={(6,): {"D"}, (10,): {"F", "D"}},
                flow_fraction=0.8,
            ),
            "E": NodeCapacity(
                node_id="E",
                edges={8},
                edges_max_flow={(8,): 2},
                max_balanced_flow=2.0,
                downstream_nodes={(8,): {"D", "F", "C"}},
                flow_fraction=0.2,
            ),
            "F": NodeCapacity(
                node_id="F",
                edges={11},
                edges_max_flow={(11,): 2},
                max_balanced_flow=2.0,
                downstream_nodes={(11,): {"D"}},
                flow_fraction=0.4,
            ),
        }

    def test_calc_capacity_balanced_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=2, capacity=1)
        g.add_edge("A", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("A", "D", metric=4, capacity=2)
        g.add_edge("C", "F", metric=1, capacity=1)
        g.add_edge("F", "D", metric=1, capacity=2)

        _, pred = spf(g, "A")
        r = init_residual_graph(g)

        max_flow, _ = calc_capacity_balanced(r, "A", "D", pred)
        assert max_flow == 2.5

    def test_calc_capacity_balanced_3(self):
        g = MultiDiGraph()
        g.add_edge("Source", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=2, capacity=1)
        g.add_edge("Source", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("Source", "D", metric=4, capacity=2)
        g.add_edge("C", "F", metric=1, capacity=1)
        g.add_edge("F", "D", metric=1, capacity=2)

        _, pred = spf(g, "Source")
        r = init_residual_graph(g)

        max_flow, _ = calc_capacity_balanced(r, "Source", "D", pred)
        assert max_flow == 3

    def test_place_flow_balanced_1(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=2, capacity=1)
        g.add_edge("A", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("A", "D", metric=4, capacity=2)
        g.add_edge("C", "F", metric=1, capacity=1)
        g.add_edge("F", "D", metric=1, capacity=2)

        r = init_residual_graph(g)

        placed_flow, remaining_flow = place_flow_balanced(r, "A", "D", 10)
        assert placed_flow == 2.5
        assert remaining_flow == 7.5

    def test_place_flow_balanced_2(self):
        g = MultiDiGraph()
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("A", "B", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("B", "C", metric=1, capacity=10)
        g.add_edge("C", "D", metric=2, capacity=1)
        g.add_edge("A", "E", metric=1, capacity=3)
        g.add_edge("E", "C", metric=1, capacity=2)
        g.add_edge("A", "D", metric=4, capacity=2)
        g.add_edge("C", "F", metric=1, capacity=1)
        g.add_edge("F", "D", metric=1, capacity=2)

        r = init_residual_graph(g)

        placed_flow, remaining_flow = place_flow_balanced(r, "A", "D")
        assert placed_flow == 2.5
        assert remaining_flow == float("inf")
