import pytest
from ngraph.network import Node


class TestNode:
    def test_node_creation(self):
        node = Node("Node1", node_type="simple", attribute1="value1", capacity=100)
        assert node.node_id == "Node1"
        assert node.node_type == "simple"
        assert node.attributes["attribute1"] == "value1"
        assert node.attributes["capacity"] == 100
        assert node.attributes["total_link_capacity"] == 0  # default value

    def test_update_node_attributes(self):
        node = Node("Node1", attribute1="value1")
        node.update_attributes(attribute1="new_value")
        assert node.attributes["attribute1"] == "new_value"
