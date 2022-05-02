from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, fields
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple, Type, ClassVar

from ngraph.graphnx import MultiDiGraphNX
from ngraph.datastore import DataStore, DataStoreDataClass
from ngraph.geo_helpers import airport_iata_coords, distance

import pandas as pd


class LayerType(IntEnum):
    """
    Types of layers
    """

    INFRA = 1


@dataclass
class Node(DataStoreDataClass):
    index: ClassVar[List[str]] = ["name"]
    name: str
    disabled: bool = False


@dataclass
class Edge(DataStoreDataClass):
    index: ClassVar[List[str]] = ["id"]
    id: int = field(init=False)
    node_a: str
    node_z: str
    disabled: bool = False


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
        for node_ntuple in self.nodes_ds:
            if not node_ntuple.disabled:
                self.graph.add_node(node_ntuple.name, **node_ntuple._asdict())

        for edge_ntuple in self.edges_ds:
            if (
                edge_ntuple.node_a in self.graph
                and edge_ntuple.node_z in self.graph
                and not edge_ntuple.disabled
            ):
                self.graph.add_edge(
                    edge_ntuple.node_a,
                    edge_ntuple.node_z,
                    edge_ntuple.id,
                    **edge_ntuple._asdict(),
                )
                self.graph.add_edge(
                    edge_ntuple.node_z,
                    edge_ntuple.node_a,
                    ~edge_ntuple.id,
                    **edge_ntuple._asdict(),
                )


@dataclass
class InfraLocation(Node):
    latlon: Optional[Tuple[float, float]] = None
    airport_code: Optional[str] = None


@dataclass
class InfraConnection(Edge):
    distance_geo: Optional[float] = None


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

    def update_edges_distance_geo(self) -> None:
        for edge_tuple in self.edges_ds:
            latlon_a = self.nodes_ds[edge_tuple.node_a].latlon
            latlon_z = self.nodes_ds[edge_tuple.node_z].latlon
            if latlon_a is None or latlon_z is None:
                continue

            self.edges_ds.update_data(
                edge_tuple.id,
                "distance_geo",
                distance(
                    *latlon_a,
                    *latlon_z,
                ),
            )

    def update_nodes_latlon(self) -> None:
        for node_tuple in self.nodes_ds:
            if node_tuple.latlon is None:
                if node_tuple.airport_code is None:
                    return
                else:
                    latlon = airport_iata_coords(node_tuple.airport_code)
                    self.nodes_ds.update_data(node_tuple.name, "latlon", latlon)

    def get_node_geo_distance(
        self, node_a: InfraLocation, node_z: InfraLocation
    ) -> float:
        for node in [node_a, node_z]:
            if node.latlon is None:
                raise RuntimeError(f"{node} has no latlon tuple defined!")
        return distance(*node_a.latlon, *node_z.latlon)

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

    def get_closest_nodes(self, node_name: str, n: int) -> pd.DataFrame:
        if node_name not in self.nodes_ds:
            raise RuntimeError(f"Unknown node {node_name}")

        self.update_nodes_latlon()
        if (latlon_a := self.nodes_ds[node_name].latlon) is None:
            raise RuntimeError(f"Unknown latlon for {node_name}")
        else:
            df_list = []
            for node_tuple in self.nodes_ds:
                if node_tuple.name == node_name:
                    continue
                entry = node_tuple._asdict()
                entry["distance_geo"] = distance(*latlon_a, *node_tuple.latlon)
                df_list.append(entry)
            return (
                pd.DataFrame(
                    df_list,
                )
                .sort_values(by=["distance_geo"])
                .set_index("name", drop=False)[:n]
            )


LAYER_TYPES: Dict[LayerType, Type[Layer]] = {LayerType.INFRA: InfraLayer}
