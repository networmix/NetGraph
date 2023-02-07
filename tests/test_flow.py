# pylint: disable=protected-access,invalid-name
from ngraph.algorithms.common import (
    EdgeFilter,
    EdgeSelect,
    init_flow_graph,
    PathAlg,
    FlowPlacement,
)
from ngraph.flow import Flow, FlowPolicy, FlowIndex
from ngraph.path_bundle import PathBundle
from ngraph.algorithms.common import MIN_FLOW

from .sample_graphs import *


class TestFlowPolicy:
    def test_flow_policy_1(self):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        assert flow_policy

    def test_flow_policy_get_path_bundle_1(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        path_bundle: PathBundle = flow_policy._get_path_bundle(r, "A", "C")
        assert path_bundle.pred == {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}
        assert path_bundle.edges == {0, 1}
        assert path_bundle.nodes == {"A", "B", "C"}

    def test_flow_policy_get_path_bundle_2(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        path_bundle: PathBundle = flow_policy._get_path_bundle(r, "A", "C", 2)
        assert path_bundle.pred == {"A": {}, "C": {"D": [3]}, "D": {"A": [2]}}
        assert path_bundle.edges == {2, 3}
        assert path_bundle.nodes == {"D", "C", "A"}

    def test_flow_policy_create_flow_1(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        flow = flow_policy._create_flow(r, "A", "C", "test_flow")
        assert flow.path_bundle.pred == {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}

    def test_flow_policy_create_flow_2(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        flow = flow_policy._create_flow(r, "A", "C", "test_flow", 2)
        assert flow.path_bundle.pred == {"A": {}, "C": {"D": [3]}, "D": {"A": [2]}}

    def test_flow_policy_create_flow_3(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        flow = flow_policy._create_flow(r, "A", "C", "test_flow", 10)
        assert flow is None

    def test_flow_policy_place_demand_1(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        flow_policy.place_demand(r, "A", "C", "test_flow", 1)
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            2: ("A", "D", 2, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
            3: ("D", "C", 3, {"capacity": 2, "flow": 0, "flows": {}, "metric": 2}),
        }

    def test_flow_policy_place_demand_2(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        flow_policy.place_demand(r, "A", "C", "test_flow", 2)
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 1): 1.0},
                    "metric": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 1): 1.0},
                    "metric": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_3(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
            max_flow_count=1,
        )
        r = init_flow_graph(square_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 2
        )
        assert placed_flow == 2
        assert remaining_flow == 0
        assert r.get_edges() == {
            0: ("A", "B", 0, {"capacity": 1, "flow": 0.0, "flows": {}, "metric": 1}),
            1: ("B", "C", 1, {"capacity": 1, "flow": 0.0, "flows": {}, "metric": 1}),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 0): 2.0},
                    "metric": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 0): 2.0},
                    "metric": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_4(self, square_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        r = init_flow_graph(square_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 5
        )
        assert placed_flow == 3
        assert remaining_flow == 2
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 1,
                    "flow": 1.0,
                    "flows": {("A", "C", "test_flow", 0): 1.0},
                    "metric": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 1): 2.0},
                    "metric": 2,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 2,
                    "flow": 2.0,
                    "flows": {("A", "C", "test_flow", 1): 2.0},
                    "metric": 2,
                },
            ),
        }

    def test_flow_policy_place_demand_5(self, square_3):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
        )
        r = init_flow_graph(square_3)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 200
        )
        assert placed_flow == 175
        assert remaining_flow == 25
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 100,
                    "flow": 100.0,
                    "flows": {("A", "C", "test_flow", 0): 100.0},
                    "metric": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 125,
                    "flow": 125.0,
                    "flows": {
                        ("A", "C", "test_flow", 0): 100.0,
                        ("A", "C", "test_flow", 2): 25.0,
                    },
                    "metric": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 75,
                    "flow": 75.0,
                    "flows": {
                        ("A", "C", "test_flow", 1): 50.0,
                        ("A", "C", "test_flow", 2): 25.0,
                    },
                    "metric": 1,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 50,
                    "flow": 50.0,
                    "flows": {("A", "C", "test_flow", 1): 50.0},
                    "metric": 1,
                },
            ),
            4: ("B", "D", 4, {"capacity": 50, "flow": 0, "flows": {}, "metric": 1}),
            5: (
                "D",
                "B",
                5,
                {
                    "capacity": 50,
                    "flow": 25.0,
                    "flows": {("A", "C", "test_flow", 2): 25.0},
                    "metric": 1,
                },
            ),
        }

    def test_flow_policy_place_demand_6(self, line_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            min_flow_count=2,
            max_flow_count=2,
        )
        r = init_flow_graph(line_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 7
        )
        assert placed_flow == 5
        assert remaining_flow == 2
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 5,
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=0
                        ): 2.5,
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=1
                        ): 2.5,
                    },
                    "metric": 1,
                },
            ),
            1: ("B", "A", 1, {"capacity": 5, "flow": 0, "flows": {}, "metric": 1}),
            2: ("B", "C", 2, {"capacity": 1, "flow": 0.0, "flows": {}, "metric": 1}),
            3: ("C", "B", 3, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 3,
                    "flow": 2.5,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=1
                        ): 2.5
                    },
                    "metric": 1,
                },
            ),
            5: ("C", "B", 5, {"capacity": 3, "flow": 0, "flows": {}, "metric": 1}),
            6: (
                "B",
                "C",
                6,
                {
                    "capacity": 7,
                    "flow": 2.5,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=0
                        ): 2.5
                    },
                    "metric": 2,
                },
            ),
            7: ("C", "B", 7, {"capacity": 7, "flow": 0, "flows": {}, "metric": 2}),
        }

    def test_flow_policy_place_demand_7(self, square_3):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            min_flow_count=3,
            max_flow_count=3,
        )
        r = init_flow_graph(square_3)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 200
        )
        assert round(placed_flow, 10) == 150
        assert round(remaining_flow, 10) == 50
        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "capacity": 100,
                    "flow": 100.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=0
                        ): 50.0,
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=2
                        ): 49.99999999999999,
                    },
                    "metric": 1,
                },
            ),
            1: (
                "B",
                "C",
                1,
                {
                    "capacity": 125,
                    "flow": 100.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=0
                        ): 50.0,
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=2
                        ): 49.99999999999999,
                    },
                    "metric": 1,
                },
            ),
            2: (
                "A",
                "D",
                2,
                {
                    "capacity": 75,
                    "flow": 50.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=1
                        ): 50.0
                    },
                    "metric": 1,
                },
            ),
            3: (
                "D",
                "C",
                3,
                {
                    "capacity": 50,
                    "flow": 50.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="test_flow", flow_id=1
                        ): 50.0
                    },
                    "metric": 1,
                },
            ),
            4: ("B", "D", 4, {"capacity": 50, "flow": 0, "flows": {}, "metric": 1}),
            5: ("D", "B", 5, {"capacity": 50, "flow": 0.0, "flows": {}, "metric": 1}),
        }

    def test_flow_policy_place_demand_8(self, line_1):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
        r = init_flow_graph(line_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r, "A", "C", "test_flow", 7
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 5

    def test_flow_policy_place_demand_9(self, line_1):
        """
        Causes a RuntimeError due to infinite loop. The flow policy is incorrectly
        configured to use non-capacity aware edge selection without reasonable limit on the number of flows.
        """
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1000000,
        )
        r = init_flow_graph(line_1)
        with pytest.raises(RuntimeError):
            placed_flow, remaining_flow = flow_policy.place_demand(
                r, "A", "C", "test_flow", 7
            )

    def test_flow_policy_place_demand_10(self, square_1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1],
        )
        r = init_flow_graph(square_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 1
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=0)
            ].path_bundle
            == PATH_BUNDLE1
        )
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=0)
            ].placed_flow
            == 2
        )

    def test_flow_policy_place_demand_11(self, square_1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        PATH_BUNDLE2 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1, PATH_BUNDLE2],
        )
        r = init_flow_graph(square_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )
        assert round(placed_flow, 10) == 2
        assert round(remaining_flow, 10) == 1
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=1)
            ].path_bundle
            == PATH_BUNDLE2
        )
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=1)
            ].placed_flow
            == 1
        )

    def test_flow_policy_place_demand_12(self, square_1):
        PATH_BUNDLE1 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        PATH_BUNDLE2 = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [3]}, "B": {"A": [2]}}, 2
        )
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            static_paths=[PATH_BUNDLE1, PATH_BUNDLE2],
        )
        r = init_flow_graph(square_1)
        placed_flow, remaining_flow = flow_policy.place_demand(
            r,
            "A",
            "C",
            "test_flow",
            3,
        )

        assert abs(2 - placed_flow) <= MIN_FLOW  # TODO: why is this not strictly less?
        assert (
            abs(1 - remaining_flow) <= MIN_FLOW
        )  # TODO: why is this not strictly less?
        assert (
            flow_policy.flows[
                FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=1)
            ].path_bundle
            == PATH_BUNDLE2
        )
        assert (
            abs(
                flow_policy.flows[
                    FlowIndex(src_node="A", dst_node="C", label="test_flow", flow_id=1)
                ].placed_flow
                - 1
            )
            <= MIN_FLOW  # TODO: why is this not strictly less?
        )


class TestFlow:
    def test_flow_1(self, square_1):
        flow_graph = init_flow_graph(square_1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 0, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 0
        assert remaining_flow == 0

    def test_flow_2(self, square_1):
        flow_graph = init_flow_graph(square_1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 1, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 1
        assert remaining_flow == 0

    def test_flow_3(self, square_1):
        flow_graph = init_flow_graph(square_1)
        path_bundle = PathBundle(
            "A", "C", {"A": {}, "C": {"B": [1]}, "B": {"A": [0]}}, 2
        )
        flow = Flow(path_bundle, ("A", "C", "test_flow"))
        placed_flow, remaining_flow = flow.place_flow(
            flow_graph, 1, flow_placement=FlowPlacement.EQUAL_BALANCED
        )
        assert placed_flow == 1
        assert flow.placed_flow == 1
        assert remaining_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 1
        flow.remove_flow(flow_graph)
        assert flow.placed_flow == 0
        assert flow_graph.get_edge_attr(0)["flow"] == 0
