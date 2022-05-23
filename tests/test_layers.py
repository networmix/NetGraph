import io
from ngraph.layers import (
    Layer,
    InfraLayer,
    LayerType,
    InfraLocation,
    InfraConnection,
    IPLayer,
    IPDevice,
    IPConnection,
)
from ngraph.io import graph_to_node_link


class TestInfraLayer:
    def test_init(self):
        Layer.create_layer(LayerType.INFRA)

    def test_add_node_1(self):
        node1 = InfraLocation("sjc")
        node2 = InfraLocation("ewr")
        layer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)

        assert layer.nodes_ds[node1.get_index()] == node1

    def test_add_edge_1(self):
        node1 = InfraLocation("sjc")
        node2 = InfraLocation("ewr")
        edge1 = InfraConnection("sjc", "ewr")
        layer: InfraLayer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        assert layer.edges_ds[edge1.get_index()] == edge1

    def test_update_nodes_latlon_1(self):
        node1 = InfraLocation("sjc", airport_code="sjc")
        node2 = InfraLocation("ewr", airport_code="ewr")

        layer: InfraLayer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)

        layer.update_nodes_latlon()

        assert layer.nodes_ds.df["latlon"].to_dict() == {
            "sjc": (37.362598, -121.929001),
            "ewr": (40.692501068115234, -74.168701171875),
        }

    def test_update_edges_distance_geo_1(self):
        node1 = InfraLocation("sjc", airport_code="sjc")
        node2 = InfraLocation("ewr", airport_code="ewr")
        edge1 = InfraConnection("sjc", "ewr")
        layer: InfraLayer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        layer.update_nodes_latlon()
        layer.update_edges_distance_geo()

        assert layer.edges_ds[edge1.get_index()].distance_geo == 4091.39

    def test_update_graph_1(self):
        node1 = InfraLocation("sjc")
        node2 = InfraLocation("ewr")
        edge1 = InfraConnection("sjc", "ewr")

        layer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        layer.update_graph()

        assert "sjc" in layer.graph
        assert "ewr" in layer.graph
        assert layer.graph["sjc"] == {
            "ewr": {
                0: {
                    "id": 0,
                    "node_a": "sjc",
                    "node_z": "ewr",
                    "type": 1,
                    "disabled": False,
                    "distance_geo": None,
                }
            }
        }
        assert layer.graph["ewr"] == {
            "sjc": {
                -1: {
                    "id": 0,
                    "node_a": "sjc",
                    "node_z": "ewr",
                    "type": 1,
                    "disabled": False,
                    "distance_geo": None,
                }
            }
        }

    def test_update_graph_2(self):
        node1 = InfraLocation("sjc")
        node2 = InfraLocation("ewr")
        edge1 = InfraConnection("sjc", "ewr")
        edge1.disabled = True

        layer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        layer.update_graph()

        assert "sjc" in layer.graph
        assert "ewr" in layer.graph
        assert layer.graph["sjc"] == {}
        assert layer.graph["ewr"] == {}

    def test_update_graph_3(self):
        node1 = InfraLocation("sjc")
        node2 = InfraLocation("ewr")
        node2.disabled = True
        edge1 = InfraConnection("sjc", "ewr")

        layer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        layer.update_graph()

        assert "sjc" in layer.graph
        assert "ewr" not in layer.graph
        assert layer.graph["sjc"] == {}

    def test_get_closest_nodes_1(self):
        node1 = InfraLocation("sjc", airport_code="sjc")
        node2 = InfraLocation("ewr", airport_code="ewr")
        node3 = InfraLocation("dfw", airport_code="dfw")
        node4 = InfraLocation("ftw", airport_code="ftw")

        layer: InfraLayer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_node(node3)
        layer.add_node(node4)

        assert layer.get_closest_nodes("dfw", 1)["distance_geo"].to_dict() == {
            "ftw": 31.49
        }
        assert layer.get_closest_nodes("dfw", 2)["distance_geo"].to_dict() == {
            "ftw": 31.49,
            "ewr": 2204.79,
        }


class TestIPLayer:
    def test_init(self):
        Layer.create_layer(LayerType.IP)

    def test_add_node_1(self):
        node1 = IPDevice("bb01", infra_location="sjc")
        node2 = IPDevice("bb02", infra_location="ewr")
        layer = Layer.create_layer(LayerType.IP)

        layer.add_node(node1)
        layer.add_node(node2)

        assert layer.nodes_ds[node1.get_index()] == node1

    def test_add_edge_1(self):
        node1 = IPDevice("bb01", infra_location="sjc")
        node2 = IPDevice("bb02", infra_location="ewr")
        edge1 = IPConnection("bb01", "bb02")
        layer: InfraLayer = Layer.create_layer(LayerType.IP)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        assert layer.edges_ds[edge1.get_index()] == edge1

    def test_get_max_flows_bfs_1(self):
        nodes = [
            IPDevice("bb01.sjc", infra_location="sjc"),
            IPDevice("bb02.sjc", infra_location="sjc"),
            IPDevice("bb01.ewr", infra_location="ewr"),
            IPDevice("bb02.ewr", infra_location="ewr"),
        ]

        edges = [
            IPConnection("bb01.sjc", "bb01.ewr"),
            IPConnection("bb02.sjc", "bb01.ewr"),
            IPConnection("bb01.sjc", "bb02.ewr"),
            IPConnection("bb02.sjc", "bb02.ewr"),
        ]
        layer: IPLayer = Layer.create_layer(LayerType.IP)

        for node in nodes:
            layer.add_node(node)

        for edge in edges:
            layer.add_edge(edge)

        assert layer.get_max_flows(shortest_path=False).fillna(0).to_dict() == {
            "bb01.sjc": {
                "bb02.sjc": 200.0,
                "bb01.ewr": 200.0,
                "bb02.ewr": 200.0,
                "bb01.sjc": 0.0,
            },
            "bb02.sjc": {
                "bb02.sjc": 0.0,
                "bb01.ewr": 200.0,
                "bb02.ewr": 200.0,
                "bb01.sjc": 200.0,
            },
            "bb01.ewr": {
                "bb02.sjc": 200.0,
                "bb01.ewr": 0.0,
                "bb02.ewr": 200.0,
                "bb01.sjc": 200.0,
            },
            "bb02.ewr": {
                "bb02.sjc": 200.0,
                "bb01.ewr": 200.0,
                "bb02.ewr": 0.0,
                "bb01.sjc": 200.0,
            },
        }

    def test_get_max_flows_spf_1(self):
        nodes = [
            IPDevice("bb01.sjc", infra_location="sjc"),
            IPDevice("bb02.sjc", infra_location="sjc"),
            IPDevice("bb01.ewr", infra_location="ewr"),
            IPDevice("bb02.ewr", infra_location="ewr"),
        ]

        edges = [
            IPConnection("bb01.sjc", "bb01.ewr"),
            IPConnection("bb02.sjc", "bb01.ewr"),
            IPConnection("bb01.sjc", "bb02.ewr"),
            IPConnection("bb02.sjc", "bb02.ewr"),
        ]
        layer: IPLayer = Layer.create_layer(LayerType.IP)

        for node in nodes:
            layer.add_node(node)

        for edge in edges:
            layer.add_edge(edge)

        assert layer.get_max_flows(shortest_path=True).fillna(0).to_dict() == {
            "bb01.sjc": {
                "bb01.sjc": 0.0,
                "bb02.sjc": 200.0,
                "bb01.ewr": 100.0,
                "bb02.ewr": 100.0,
            },
            "bb02.sjc": {
                "bb01.sjc": 200.0,
                "bb02.sjc": 0.0,
                "bb01.ewr": 100.0,
                "bb02.ewr": 100.0,
            },
            "bb01.ewr": {
                "bb01.sjc": 100.0,
                "bb02.sjc": 100.0,
                "bb01.ewr": 0.0,
                "bb02.ewr": 200.0,
            },
            "bb02.ewr": {
                "bb01.sjc": 100.0,
                "bb02.sjc": 100.0,
                "bb01.ewr": 200.0,
                "bb02.ewr": 0.0,
            },
        }
