from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, ClassVar, Dict, List, Type
from ngraph.algorithms.flow import init_flow_graph, place_flow, place_flow_balanced

from ngraph.datastore import DataStore, DataStoreDataClass
from ngraph.layers import (
    Edge,
    EdgeType,
    InfraLayer,
    IPLayer,
    Layer,
    LayerType,
    Node,
    NodeType,
)


class TrafficClass(IntEnum):
    """
    Traffic classes
    """

    ICP = 1
    GOLD = 2
    SILVER = 3
    BRONZE = 4


@dataclass
class TrafficDemand(DataStoreDataClass):
    index: ClassVar[List[str]] = ["src", "dst", "traffic_class"]
    type_hooks: ClassVar[Dict[Type, Callable]] = {TrafficClass: TrafficClass}
    src: str
    dst: str
    traffic_class: TrafficClass
    demand: float


class TrafficDemands:
    def __init__(self):
        self.demands_ds: DataStore = DataStore(TrafficDemand)

    def add_demand(self, demand: TrafficDemand) -> None:
        self.demands_ds.add(demand)


class Net:
    def __init__(self):
        self.infra_layer: InfraLayer = Layer.create_layer(LayerType.INFRA)
        self.ip_layer: IPLayer = Layer.create_layer(LayerType.IP)
        self.traffic_demands: TrafficDemands = TrafficDemands()

    def add_nodes_edges(self, nodes: List[Node], edges: List[Edge]) -> None:
        for node in nodes:
            if node.type == NodeType.INFRA:
                self.infra_layer.add_node(node)
            elif node.type == NodeType.IP:
                self.ip_layer.add_node(node)

        for edge in edges:
            if edge.type == EdgeType.INFRA:
                self.infra_layer.add_edge(edge)
            elif edge.type == EdgeType.IP:
                self.ip_layer.add_edge(edge)

        self.infra_layer.update_nodes_latlon()
        self.infra_layer.update_edges_distance_geo()

    def add_traffic_demands(self, traf_demands: List[TrafficDemand]) -> None:
        for traf_demand in traf_demands:
            self.traffic_demands.add_demand(traf_demand)

    def place_traffic_demands(self) -> None:
        init_flow_graph(self.ip_layer.graph)
        for traffic_class in TrafficClass:
            for demand_tuple in self.traffic_demands.demands_ds.query_iter(
                f"traffic_class == {traffic_class}"
            ):
                print(demand_tuple)
                place_flow_balanced()
