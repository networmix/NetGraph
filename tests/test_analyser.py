# pylint: disable=protected-access,invalid-name
from dataclasses import asdict
import pytest

from ngraph.algorithms.common import init_flow_graph
from ngraph.analyser import Analyser
from ngraph.demand import Demand
from ngraph.flow import FlowPolicyConfig, get_flow_policy


from .sample_graphs import *


class TestAnalyser:
    def test_demand_analyser_1(self, triangle_1):
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
