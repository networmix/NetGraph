from dataclasses import dataclass, field
from typing import ClassVar, List

from ngraph.datastore import DataStoreDataClass
from ngraph.layers import InfraLayer, IPLayer, Layer, LayerType


@dataclass
class Demand(DataStoreDataClass):
    index: ClassVar[List[str]] = ["src", "dst", "traffic_class"]
    src: str
    dst: str
    traffic_class: str


class Net:
    def __init__(self):
        self.infra_layer: InfraLayer = Layer.create_layer(LayerType.INFRA)
        self.ip_layer: IPLayer = Layer.create_layer(LayerType.IP)
