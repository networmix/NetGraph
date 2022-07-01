from dataclasses import dataclass, field
from typing import Dict, List
from ngraph.graph import MultiDiGraph
from ngraph.demand import Demand


@dataclass(init=False)
class DemandData:
    total_edge_cost_flow_product: float = 0
    total_volume: float = 0
    placed_demand: float = 0
    unsatisfied_demand: float = 0


@dataclass(init=False)
class GraphData:
    total_edge_cost_volume_product: float = 0
    total_capacity: float = 0
    total_flow: float = 0

    avg_capacity_utilization: float = 0


class Analyser:
    def __init__(
        self,
        graph: MultiDiGraph,
        demands: List[Demand],
        cost_attr: str = "metric",
        cap_attr: str = "capacity",
        flow_attr: str = "flow",
        flows_attr: str = "flows",
    ):
        self.graph = graph
        self.demands = demands
        self.demand_data: Dict[Demand, DemandData] = {}
        self.graph_data: GraphData = GraphData()
        self.cost_attr = cost_attr
        self.cap_attr = cap_attr
        self.flow_attr = flow_attr
        self.flows_attr = flows_attr

    def analyse(self) -> None:
        for demand in self.demands:
            self.demand_data[demand] = self._analyse_demand(demand)
        self._analyse_graph()

    def _analyse_graph(self):
        edges = self.graph.get_edges()
        for edge_id in edges:
            edge_attr = edges[edge_id][3]
            self.graph_data.total_edge_cost_volume_product += (
                edge_attr[self.cost_attr] * edge_attr[self.flow_attr]
            )
            self.graph_data.total_capacity += edge_attr[self.cap_attr]
            self.graph_data.total_flow += edge_attr[self.flow_attr]

        if self.graph_data.total_capacity:
            self.graph_data.avg_capacity_utilization = (
                self.graph_data.total_flow / self.graph_data.total_capacity
            )

    def _analyse_demand(self, demand: Demand) -> DemandData:
        edges = self.graph.get_edges()
        demand_data = DemandData()
        demand_data.total_volume = demand.volume
        demand_data.placed_demand = demand.placed_flow
        demand_data.unsatisfied_demand = demand.volume - demand.placed_flow
        for edge_id in demand.edges:
            edge_attr = edges[edge_id][3]
            demand_data.total_edge_cost_flow_product += (
                edge_attr[self.cost_attr]
                * edge_attr[self.flows_attr][demand.flow_index]
            )

        return demand_data
