import pytest
from ngraph.network import Link


class TestLink:
    def test_link_creation(self):
        link = Link("Node1", "Node2", attribute1="value1")
        assert link.node1 == "Node1"
        assert link.node2 == "Node2"
        assert link.attributes["attribute1"] == "value1"
        assert "link_id" in link.attributes
        assert "capacity" in link.attributes
        assert "metric" in link.attributes

    def test_link_creation_with_explicit_link_id(self):
        link_id = "custom_link_id"
        link = Link("Node1", "Node2", link_id=link_id)
        assert link.link_id == link_id

    def test_link_creation_with_custom_capacity_and_metric(self):
        link = Link("Node1", "Node2", capacity=100, metric=10)
        assert link.attributes["capacity"] == 100
        assert link.attributes["metric"] == 10

    def test_update_link_attributes(self):
        link = Link("Node1", "Node2", attribute1="value1")
        link.update_attributes(attribute1="new_value", metric=20)
        assert link.attributes["attribute1"] == "new_value"
        assert link.attributes["metric"] == 20

    def test_update_link_attributes_with_new_attribute(self):
        link = Link("Node1", "Node2")
        link.update_attributes(new_attribute="new_value")
        assert "new_attribute" in link.attributes
        assert link.attributes["new_attribute"] == "new_value"
