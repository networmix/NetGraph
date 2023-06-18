# pylint: disable=protected-access,invalid-name
from dataclasses import asdict
import pytest

from ngraph.lib.flow_policy import FlowPolicyConfig, get_flow_policy
from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.common import init_flow_graph
from ngraph.lib.demand import Demand
from ngraph.analyser import Analyser


from .sample_data.sample_graphs import *


class TestAnalyser:
    def test_demand_analyser_1(self, triangle1):
        r = init_flow_graph(triangle1)

        demands = [
            Demand(
                "A",
                "B",
                10,
            ),
            Demand(
                "B",
                "A",
                10,
            ),
            Demand(
                "B",
                "C",
                10,
            ),
            Demand(
                "C",
                "B",
                10,
            ),
            Demand(
                "A",
                "C",
                10,
            ),
            Demand(
                "C",
                "A",
                10,
            ),
        ]

        demand_policy_map = {}
        for demand in demands:
            flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
            demand_policy_map[demand] = flow_policy
            demand.place(r, flow_policy)

        analyser = Analyser(r, demand_policy_map)
        analyser.analyse()

        assert analyser.demand_data[demands[0]].total_edge_cost_flow_product == 10.0
        assert analyser.demand_data[demands[0]].total_volume == 10.0
        assert analyser.demand_data[demands[0]].placed_demand == 10.0
        assert analyser.demand_data[demands[0]].unsatisfied_demand == 0

        assert analyser.graph_data.total_edge_cost_volume_product == 70.0
        assert analyser.graph_data.total_capacity == 70.0
        assert analyser.graph_data.total_flow == 70.0
        assert analyser.graph_data.avg_capacity_utilization == 1.0
