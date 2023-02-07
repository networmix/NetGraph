# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.algorithms.common import (
    EdgeSelect,
    init_flow_graph,
    PathAlg,
    FlowPlacement,
)
from ngraph.demand import Demand
from ngraph.flow import FlowPolicy, FlowPolicyConfig, get_flow_policy, FlowIndex

from .sample_graphs import *


class TestDemand:
    def test_demand_1(self):
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        assert Demand("A", "C", float("inf"), flow_policy)

    def test_demand_place_1(self, line_1):
        r = init_flow_graph(line_1)
        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_demand, remaining_demand = d.place(r)

        assert placed_demand == 5
        assert remaining_demand == float("inf")
        assert d.placed_demand == placed_demand
        assert (
            any(
                edge[3]["flow"] > edge[3]["capacity"] for edge in r.get_edges().values()
            )
            == False
        )
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
                            src_node="A", dst_node="C", label="TEST", flow_id=0
                        ): 5.0
                    },
                    "metric": 1,
                },
            ),
            1: ("B", "A", 1, {"capacity": 5, "flow": 0, "flows": {}, "metric": 1}),
            2: (
                "B",
                "C",
                2,
                {
                    "capacity": 1,
                    "flow": 0.45454545454545453,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="TEST", flow_id=0
                        ): 0.45454545454545453
                    },
                    "metric": 1,
                },
            ),
            3: ("C", "B", 3, {"capacity": 1, "flow": 0, "flows": {}, "metric": 1}),
            4: (
                "B",
                "C",
                4,
                {
                    "capacity": 3,
                    "flow": 1.3636363636363635,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="TEST", flow_id=0
                        ): 1.3636363636363635
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
                    "flow": 3.1818181818181817,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="TEST", flow_id=0
                        ): 3.1818181818181817
                    },
                    "metric": 2,
                },
            ),
            7: ("C", "B", 7, {"capacity": 7, "flow": 0, "flows": {}, "metric": 2}),
        }

    def test_demand_place_2(self, square_1):
        r = init_flow_graph(square_1)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING,
            multipath=True,
            max_path_cost_factor=1,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_demand, remaining_demand = d.place(r)
        assert placed_demand == 1
        assert remaining_demand == float("inf")

    def test_demand_place_3(self, square_1):
        r = init_flow_graph(square_1)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.PROPORTIONAL,
            edge_select=EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING,
            multipath=True,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_demand, remaining_demand = d.place(r)
        assert placed_demand == 3
        assert remaining_demand == float("inf")

    def test_demand_place_4(self, square_2):
        r = init_flow_graph(square_2)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.ALL_MIN_COST,
            multipath=True,
            max_flow_count=1,
        )
        d = Demand("A", "C", float("inf"), flow_policy, label="TEST")

        placed_demand, remaining_demand = d.place(r)
        assert placed_demand == 2
        assert remaining_demand == float("inf")

    def test_demand_place_5(self, triangle_1):
        r = init_flow_graph(triangle_1)

        demands = [
            Demand(
                "A",
                "B",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_1",
            ),
            Demand(
                "B",
                "A",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_1",
            ),
            Demand(
                "B",
                "C",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_2",
            ),
            Demand(
                "C",
                "B",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_2",
            ),
            Demand(
                "A",
                "C",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_3",
            ),
            Demand(
                "C",
                "A",
                10,
                get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM),
                label="Demand_3",
            ),
        ]

        for demand in demands:
            demand.place(r)

        assert r.get_edges() == {
            0: (
                "A",
                "B",
                0,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "1",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="B", label="Demand_1", flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="A", dst_node="C", label="Demand_3", flow_id=1
                        ): 5.0,
                    },
                },
            ),
            1: (
                "B",
                "A",
                1,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "1",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="B", dst_node="A", label="Demand_1", flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="C", dst_node="A", label="Demand_3", flow_id=1
                        ): 5.0,
                    },
                },
            ),
            2: (
                "B",
                "C",
                2,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "2",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="B", dst_node="C", label="Demand_2", flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="A", dst_node="C", label="Demand_3", flow_id=1
                        ): 5.0,
                    },
                },
            ),
            3: (
                "C",
                "B",
                3,
                {
                    "metric": 1,
                    "capacity": 15,
                    "label": "2",
                    "flow": 15.0,
                    "flows": {
                        FlowIndex(
                            src_node="C", dst_node="B", label="Demand_2", flow_id=0
                        ): 10.0,
                        FlowIndex(
                            src_node="C", dst_node="A", label="Demand_3", flow_id=1
                        ): 5.0,
                    },
                },
            ),
            4: (
                "A",
                "C",
                4,
                {
                    "metric": 1,
                    "capacity": 5,
                    "label": "3",
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="A", dst_node="C", label="Demand_3", flow_id=0
                        ): 5.0
                    },
                },
            ),
            5: (
                "C",
                "A",
                5,
                {
                    "metric": 1,
                    "capacity": 5,
                    "label": "3",
                    "flow": 5.0,
                    "flows": {
                        FlowIndex(
                            src_node="C", dst_node="A", label="Demand_3", flow_id=0
                        ): 5.0
                    },
                },
            ),
        }

        for demand in demands:
            assert demand.placed_demand == 10

    def test_demand_place_6(self, square_2):
        r = init_flow_graph(square_2)

        flow_policy = FlowPolicy(
            path_alg=PathAlg.SPF,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            edge_select=EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING,
            multipath=False,
            max_flow_count=2,
        )
        d = Demand("A", "C", 3, flow_policy, label="TEST")

        placed_demand, remaining_demand = d.place(r, max_fraction=1 / 2)
        assert placed_demand == 1.5
        assert remaining_demand == 0

        placed_demand, remaining_demand = d.place(r, max_fraction=1 / 2)
        assert placed_demand == 0.5
        assert remaining_demand == 1

    def test_demand_place_7(self, square_2):
        r = init_flow_graph(square_2)

        d = Demand.create(
            "A", "C", 3, flow_policy_config=FlowPolicyConfig.TE_UCMP_UNLIM, label="TEST"
        )
        placed_demand, remaining_demand = d.place(r)
        assert placed_demand == 3
        assert remaining_demand == 0

    def test_demand_place_8(self, square_2):
        r = init_flow_graph(square_2)

        d = Demand.create(
            "A",
            "C",
            3,
            flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
            label="TEST",
        )
        placed_demand, remaining_demand = d.place(r)
        assert placed_demand == 2
        assert remaining_demand == 1

    def test_demand_place_9(self, graph_1):
        r = init_flow_graph(graph_1)

        d = Demand.create(
            "A",
            "D",
            float("inf"),
            flow_policy_config=FlowPolicyConfig.SHORTEST_PATHS_ECMP,
            label="TEST",
        )
        placed_demand, remaining_demand = d.place(r)

        assert placed_demand == 2.5
        assert remaining_demand == float("inf")

    def test_demand_place_10(self, graph_1):
        r = init_flow_graph(graph_1)

        d = Demand.create(
            "A",
            "D",
            float("inf"),
            flow_policy_config=FlowPolicyConfig.TE_UCMP_UNLIM,
            label="TEST",
        )
        placed_demand, remaining_demand = d.place(r)

        assert placed_demand == 6
        assert remaining_demand == float("inf")
