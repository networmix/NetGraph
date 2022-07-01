# pylint: disable=protected-access,invalid-name
from dataclasses import asdict
import pytest

from ngraph.algorithms.common import init_flow_graph
from ngraph.analyser import Analyser
from ngraph.demand import FLOW_POLICY_MAP, Demand, FlowPolicyConfig
from ngraph.graph import MultiDiGraph


@pytest.fixture
def triangle_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=15, label="1")
    g.add_edge("B", "A", metric=1, capacity=15, label="1")
    g.add_edge("B", "C", metric=1, capacity=15, label="2")
    g.add_edge("C", "B", metric=1, capacity=15, label="2")
    g.add_edge("A", "C", metric=1, capacity=5, label="3")
    g.add_edge("C", "A", metric=1, capacity=5, label="3")
    return g


class TestAnalyser:
    def test_demand_analyser_1(self, triangle_1):
        r = init_flow_graph(triangle_1)

        demands = [
            Demand(
                "A",
                "B",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_1",
            ),
            Demand(
                "B",
                "A",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_1",
            ),
            Demand(
                "B",
                "C",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_2",
            ),
            Demand(
                "C",
                "B",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_2",
            ),
            Demand(
                "A",
                "C",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_3",
            ),
            Demand(
                "C",
                "A",
                10,
                FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
                label="Demand_3",
            ),
        ]

        for demand in demands:
            demand.place(r)

        analyser = Analyser(r, demands)
        analyser.analyse()

        assert asdict(analyser.demand_data[demands[0]]) == {
            "total_edge_cost_flow_product": 10.0,
            "total_volume": 10,
            "placed_demand": 10,
            "unsatisfied_demand": 0,
        }

        assert asdict(analyser.graph_data) == {
            "total_edge_cost_volume_product": 70.0,
            "total_capacity": 70,
            "total_flow": 70.0,
            "avg_capacity_utilization": 1.0,
        }
