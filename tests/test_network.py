import pytest

from ngraph.lib.graph import MultiDiGraph
from ngraph.network import Network, Node, Link, LinkID
from .sample_data.sample_networks import *


class TestNetwork:
    def test_add_plane(self):
        network = Network()
        network.add_plane("Plane1")
        assert "Plane1" in network.planes
        assert isinstance(network.planes["Plane1"], MultiDiGraph)

    def test_generate_edge_id(self):
        network = Network()
        link = Link("Node1", "Node2", capacity=100)
        edge_id = network.generate_edge_id("Node1", "Node2", link.link_id)
        assert edge_id == LinkID("Node1", "Node2", link.link_id[2])

    def test_add_node(self):
        network = Network()
        network.add_plane("Plane1")
        node_id = network.add_node("Node1", plane_ids=["Plane1"])
        assert node_id in network.nodes
        assert network.nodes[node_id].node_id == "Node1"
        assert "Plane1" in network.nodes[node_id].attributes["plane_ids"]

    def test_add_link(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_node("Node1", plane_ids=["Plane1"])
        network.add_node("Node2", plane_ids=["Plane1"])
        link_id = network.add_link("Node1", "Node2", plane_ids=["Plane1"], capacity=100)
        assert link_id in network.links
        assert network.links[link_id].node1 == "Node1"
        assert network.links[link_id].node2 == "Node2"
        assert network.links[link_id].attributes["capacity"] == 100
        assert network.nodes["Node1"].attributes["total_link_capacity"] == 100
        assert network.nodes["Node2"].attributes["total_link_capacity"] == 100

    def test_add_multiple_planes(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_plane("Plane2")
        network.add_node("Node1", plane_ids=["Plane1", "Plane2"])
        assert "Plane1" in network.nodes["Node1"].attributes["plane_ids"]
        assert "Plane2" in network.nodes["Node1"].attributes["plane_ids"]

    def test_add_node_to_all_planes_by_default(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_plane("Plane2")
        network.add_node("Node1")
        assert "Plane1" in network.nodes["Node1"].attributes["plane_ids"]
        assert "Plane2" in network.nodes["Node1"].attributes["plane_ids"]

    def test_add_link_to_all_planes_by_default(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_plane("Plane2")
        network.add_node("Node1")
        network.add_node("Node2")
        link_id = network.add_link("Node1", "Node2")
        assert "Plane1" in network.links[link_id].attributes["plane_ids"]
        assert "Plane2" in network.links[link_id].attributes["plane_ids"]

    def test_update_total_link_capacity(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_node("Node1", plane_ids=["Plane1"])
        network.add_node("Node2", plane_ids=["Plane1"])
        network.add_link("Node1", "Node2", plane_ids=["Plane1"], capacity=100)
        network.add_link("Node2", "Node1", plane_ids=["Plane1"], capacity=200)
        assert network.nodes["Node1"].attributes["total_link_capacity"] == 300
        assert network.nodes["Node2"].attributes["total_link_capacity"] == 300

    def test_plane_max_flow(self):
        network = Network()
        network.add_plane("Plane1")
        network.add_node("Node1", plane_ids=["Plane1"])
        network.add_node("Node2", plane_ids=["Plane1"])
        network.add_link(
            "Node1", "Node2", plane_ids=["Plane1"], capacity=100, metric=10
        )
        max_flow = network.plane_max_flow(
            "Plane1", network.planes["Plane1"], "Node1", ["Node2"]
        )
        assert max_flow == 100

    def test_network1_max_flow_1(self, network1):
        max_flow = network1.calc_max_flow(["LAX"], ["SFO"])
        assert max_flow == {"LAX": {("SFO",): {"Plane1": 200.0, "Plane2": 200.0}}}
        assert "sink" not in network1.planes["Plane1"]
        assert "sink" not in network1.planes["Plane2"]

    def test_network1_max_flow_2(self, network1):
        max_flow = network1.calc_max_flow(["SEA", "LAX"], ["SFO"])
        assert max_flow == {
            "LAX": {("SFO",): {"Plane1": 200.0, "Plane2": 200.0}},
            "SEA": {("SFO",): {"Plane1": 100.0, "Plane2": 100.0}},
        }
        assert "sink" not in network1.planes["Plane1"]
        assert "sink" not in network1.planes["Plane2"]

    def test_network1_max_flow_3(self, network1):
        max_flow = network1.calc_max_flow(["SFO", "LAX"], ["JFK", "SEA"])
        assert max_flow == {
            "LAX": {("JFK", "SEA"): {"Plane1": 200.0, "Plane2": 200.0}},
            "SFO": {("JFK", "SEA"): {"Plane1": 200.0, "Plane2": 200.0}},
        }
        assert "sink" not in network1.planes["Plane1"]
        assert "sink" not in network1.planes["Plane2"]
