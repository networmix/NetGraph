import io
from ngraph.layers import Layer, InfraLayer, LayerType, InfraLocation, InfraConnection
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

    def test_update_edge_distance_geo_1(self):
        node1 = InfraLocation("sjc", airport_code="sjc")
        node2 = InfraLocation("ewr", airport_code="ewr")
        edge1 = InfraConnection("sjc", "ewr")
        layer: InfraLayer = Layer.create_layer(LayerType.INFRA)

        layer.add_node(node1)
        layer.add_node(node2)
        layer.add_edge(edge1)

        layer.update_edge_distance_geo(edge1)

        assert layer.edges_ds[edge1.get_index()].distance_geo == 4091.39
        # print(layer.edges_ds.df)
        # layer.update_graph()
        # print(graph_to_node_link(layer.graph))
        # raise
