from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, Type, ClassVar

from ngraph.graphnx import MultiDiGraphNX
from ngraph.datastore import DataStore, DataStoreDataClass
from ngraph.geo_helpers import airport_iata_coords, distance


class LayerType(IntEnum):
    """
    Types of layers
    """

    INFRA = 1


@dataclass
class Node(DataStoreDataClass):
    index: ClassVar[List[str]] = ["name"]
    name: str


@dataclass
class Edge(DataStoreDataClass):
    index: ClassVar[List[str]] = ["id"]
    id: int = field(init=False)
    node_a: str
    node_z: str


class Layer(ABC):
    def __init__(
        self,
        layer_type: LayerType,
        layer_name: str,
        graph: Optional[MultiDiGraphNX] = None,
    ):
        self.name: str = layer_name
        self.layer_type: LayerType = layer_type
        self.graph: MultiDiGraphNX = graph.copy() if graph else MultiDiGraphNX()
        self.nodes_ds: DataStore = DataStore(Node)
        self.edges_ds: DataStore = DataStore(Edge)

    @abstractmethod
    def add_node(self, node: Node) -> None:
        raise NotImplementedError(self)

    @abstractmethod
    def add_edge(self, edge: Node, id: Optional[int] = None) -> None:
        raise NotImplementedError(self)

    @staticmethod
    def create_layer(layer_type: LayerType, layer_name: Optional[str] = None) -> Layer:
        layer_name = layer_name if layer_name else layer_type.name
        return LAYER_TYPES[layer_type](layer_type, layer_name)

    def update_graph(self):
        for node in self.nodes_ds:
            node: Node
            self.graph.add_node(node.name, **node._asdict())

        for edge in self.edges_ds:
            edge: Edge
            self.graph.add_edge(edge.node_a, edge.node_z, edge.id, **node._asdict())


@dataclass
class InfraLocation(Node):
    latlon: Optional[Tuple[float]] = None
    airport_code: Optional[str] = None


@dataclass
class InfraConnection(Edge):
    distance_geo: Optional[float] = field(init=False, default=None)


class InfraLayer(Layer):
    def __init__(
        self,
        layer_type: LayerType,
        layer_name: str,
        graph: Optional[MultiDiGraphNX] = None,
    ):
        super().__init__(layer_type, layer_name, graph)
        self.nodes_ds: DataStore = DataStore(InfraLocation)
        self.edges_ds: DataStore = DataStore(InfraConnection)

    def update_graph(self):
        for node in self.nodes_ds:
            node: Node
            self.graph.add_node(node.name, **node._asdict())

        for edge in self.edges_ds:
            edge: Edge
            print(edge)
            self.graph.add_edge(edge.node_a, edge.node_z, edge.id, **edge._asdict())
            self.graph.add_edge(edge.node_z, edge.node_a, ~edge.id, **edge._asdict())

    def update_edge_distance_geo(self, edge: InfraConnection) -> None:
        node_a: InfraLocation = self.nodes_ds[edge.node_a]
        node_z: InfraLocation = self.nodes_ds[edge.node_z]

        for node in [node_a, node_z]:
            if node.latlon is None:
                if node.airport_code is None:
                    return
                else:
                    node.latlon = airport_iata_coords(node.airport_code)
                    print(node, node.latlon)
                    self.nodes_ds.update_data(node_a.name, "latlon", node.latlon)
        self.edges_ds.update_data(
            edge.id, "distance_geo", distance(*node_a.latlon, *node_z.latlon)
        )

    def add_node(self, node: InfraLocation) -> None:
        self.nodes_ds.add(node)
        self.update_graph()

    def add_edge(self, edge: InfraConnection) -> None:
        if edge.node_a not in self.nodes_ds or edge.node_z not in self.nodes_ds:
            raise RuntimeError(f"Can't add edge {edge}. Unknown location.")

        id = 0 if self.edges_ds.df.empty else self.edges_ds.df.index.max() + 1
        edge.id = id
        self.edges_ds.add(edge)
        self.update_graph()


LAYER_TYPES: Dict[LayerType, Type[Layer]] = {LayerType.INFRA: InfraLayer}
