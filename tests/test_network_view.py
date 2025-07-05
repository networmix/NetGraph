"""Tests for NetworkView class."""

import pytest

from ngraph.lib.algorithms.base import FlowPlacement
from ngraph.network import Link, Network, Node, RiskGroup
from ngraph.network_view import NetworkView


class TestNetworkViewBasics:
    """Test basic NetworkView functionality."""

    def test_create_empty_view(self):
        """Test creating a NetworkView with empty exclusions."""
        net = Network()
        view = NetworkView(_base=net)

        assert view._base is net
        assert view._excluded_nodes == frozenset()
        assert view._excluded_links == frozenset()

    def test_from_failure_sets(self):
        """Test creating NetworkView using from_failure_sets factory method."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B")
        net.add_link(link)

        view = NetworkView.from_failure_sets(
            net, failed_nodes=["A"], failed_links=[link.id]
        )

        assert view._base is net
        assert view._excluded_nodes == {"A"}
        assert view._excluded_links == {link.id}

    def test_from_failure_sets_empty(self):
        """Test from_failure_sets with empty iterables."""
        net = Network()
        view = NetworkView.from_failure_sets(net)

        assert view._excluded_nodes == frozenset()
        assert view._excluded_links == frozenset()

    def test_view_is_frozen(self):
        """Test that NetworkView is immutable."""
        net = Network()
        view = NetworkView(_base=net)

        with pytest.raises(AttributeError):
            view._base = Network()  # type: ignore
        with pytest.raises(AttributeError):
            view._excluded_nodes = frozenset(["A"])  # type: ignore

    def test_attrs_delegation(self):
        """Test that attrs and risk_groups are delegated to base network."""
        net = Network()
        net.attrs["test"] = "value"
        net.risk_groups["rg1"] = RiskGroup("rg1")

        view = NetworkView(_base=net)

        assert view.attrs == {"test": "value"}
        assert "rg1" in view.risk_groups
        assert view.risk_groups["rg1"].name == "rg1"


class TestNetworkViewVisibility:
    """Test node and link visibility logic."""

    def setup_method(self):
        """Set up test network."""
        self.net = Network()

        # Add nodes
        self.net.add_node(Node("A"))
        self.net.add_node(Node("B"))
        self.net.add_node(Node("C"))
        self.net.add_node(Node("D", disabled=True))  # scenario-disabled

        # Add links
        self.link_ab = Link("A", "B")
        self.link_bc = Link("B", "C")
        self.link_cd = Link("C", "D")
        self.link_disabled = Link("A", "C", disabled=True)  # scenario-disabled

        self.net.add_link(self.link_ab)
        self.net.add_link(self.link_bc)
        self.net.add_link(self.link_cd)
        self.net.add_link(self.link_disabled)

    def test_node_visibility_no_exclusions(self):
        """Test node visibility with no analysis exclusions."""
        view = NetworkView(_base=self.net)

        assert not view.is_node_hidden("A")
        assert not view.is_node_hidden("B")
        assert not view.is_node_hidden("C")
        assert view.is_node_hidden("D")  # scenario-disabled
        assert view.is_node_hidden("NONEXISTENT")  # doesn't exist

    def test_node_visibility_with_exclusions(self):
        """Test node visibility with analysis exclusions."""
        view = NetworkView(_base=self.net, _excluded_nodes=frozenset(["B"]))

        assert not view.is_node_hidden("A")
        assert view.is_node_hidden("B")  # analysis-excluded
        assert not view.is_node_hidden("C")
        assert view.is_node_hidden("D")  # scenario-disabled

    def test_link_visibility_no_exclusions(self):
        """Test link visibility with no analysis exclusions."""
        view = NetworkView(_base=self.net)

        assert not view.is_link_hidden(self.link_ab.id)
        assert not view.is_link_hidden(self.link_bc.id)
        assert view.is_link_hidden(self.link_cd.id)  # connected to disabled node D
        assert view.is_link_hidden(self.link_disabled.id)  # scenario-disabled
        assert view.is_link_hidden("NONEXISTENT")  # doesn't exist

    def test_link_visibility_with_exclusions(self):
        """Test link visibility with analysis exclusions."""
        view = NetworkView(
            _base=self.net,
            _excluded_nodes=frozenset(["B"]),
            _excluded_links=frozenset([self.link_ab.id]),
        )

        assert view.is_link_hidden(self.link_ab.id)  # analysis-excluded
        assert view.is_link_hidden(self.link_bc.id)  # connected to excluded node B
        assert view.is_link_hidden(
            self.link_disabled.id
        )  # A-C, both visible, but scenario-disabled
        assert view.is_link_hidden(self.link_cd.id)  # connected to disabled node D

    def test_nodes_property(self):
        """Test nodes property returns only visible nodes."""
        view = NetworkView(_base=self.net, _excluded_nodes=frozenset(["B"]))

        visible_nodes = view.nodes

        assert "A" in visible_nodes
        assert "B" not in visible_nodes  # analysis-excluded
        assert "C" in visible_nodes
        assert "D" not in visible_nodes  # scenario-disabled
        assert len(visible_nodes) == 2

    def test_links_property(self):
        """Test links property returns only visible links."""
        view = NetworkView(_base=self.net, _excluded_nodes=frozenset(["B"]))

        visible_links = view.links

        # Only links not connected to hidden nodes and not disabled
        expected_links = {
            link_id
            for link_id, link in self.net.links.items()
            if not view.is_link_hidden(link_id)
        }

        assert set(visible_links.keys()) == expected_links
        # Should exclude links connected to B, D, and the disabled link


class TestNetworkViewCaching:
    """Test NetworkView graph caching functionality."""

    def setup_method(self):
        """Set up test network."""
        self.net = Network()
        for i in range(10):
            self.net.add_node(Node(f"node_{i}"))
        for i in range(9):
            self.net.add_link(Link(f"node_{i}", f"node_{i + 1}"))

        self.view = NetworkView.from_failure_sets(self.net, failed_nodes=["node_0"])

    def test_initial_cache_state(self):
        """Test that cache doesn't exist initially."""
        assert not hasattr(self.view, "_graph_cache")

    def test_cache_initialization(self):
        """Test cache is initialized on first graph build."""
        graph = self.view.to_strict_multidigraph()

        assert hasattr(self.view, "_graph_cache")
        assert True in self.view._graph_cache  # type: ignore
        assert self.view._graph_cache[True] is graph  # type: ignore

    def test_cache_hit(self):
        """Test that subsequent calls return cached graph."""
        graph1 = self.view.to_strict_multidigraph()
        graph2 = self.view.to_strict_multidigraph()

        assert graph1 is graph2  # Same object reference

    def test_cache_per_add_reverse_parameter(self):
        """Test that cache is separate for different add_reverse values."""
        graph_with_reverse = self.view.to_strict_multidigraph(add_reverse=True)
        graph_without_reverse = self.view.to_strict_multidigraph(add_reverse=False)

        assert graph_with_reverse is not graph_without_reverse
        assert hasattr(self.view, "_graph_cache")
        assert True in self.view._graph_cache  # type: ignore
        assert False in self.view._graph_cache  # type: ignore

        # Subsequent calls should hit cache
        assert self.view.to_strict_multidigraph(add_reverse=True) is graph_with_reverse
        assert (
            self.view.to_strict_multidigraph(add_reverse=False) is graph_without_reverse
        )

    def test_different_views_independent_cache(self):
        """Test that different NetworkView instances have independent caches."""
        view1 = NetworkView.from_failure_sets(self.net, failed_nodes=["node_0"])
        view2 = NetworkView.from_failure_sets(self.net, failed_nodes=["node_1"])

        graph1 = view1.to_strict_multidigraph()
        graph2 = view2.to_strict_multidigraph()

        assert graph1 is not graph2
        assert hasattr(view1, "_graph_cache")
        assert hasattr(view2, "_graph_cache")
        assert view1._graph_cache is not view2._graph_cache  # type: ignore


class TestNetworkViewFlowMethods:
    """Test NetworkView flow analysis methods."""

    def setup_method(self):
        """Set up test network with flow capacity."""
        self.net = Network()

        # Create a simple path: A -> B -> C -> D
        for name in ["A", "B", "C", "D"]:
            self.net.add_node(Node(name))

        self.net.add_link(Link("A", "B", capacity=10.0))
        self.net.add_link(Link("B", "C", capacity=5.0))  # bottleneck
        self.net.add_link(Link("C", "D", capacity=15.0))

        self.view = NetworkView(_base=self.net)

    def test_max_flow_delegation(self):
        """Test that max_flow delegates to base network internal method."""
        flows = self.view.max_flow("A", "D")

        assert isinstance(flows, dict)
        assert len(flows) == 1
        # Should get bottleneck capacity of 5.0
        flow_value = list(flows.values())[0]
        assert flow_value == 5.0

    def test_max_flow_with_summary(self):
        """Test max_flow_with_summary method."""
        results = self.view.max_flow_with_summary("A", "D")

        assert isinstance(results, dict)
        assert len(results) == 1

        flow_value, summary = list(results.values())[0]
        assert flow_value == 5.0
        assert hasattr(summary, "total_flow")
        assert summary.total_flow == 5.0

    def test_max_flow_with_graph(self):
        """Test max_flow_with_graph method."""
        results = self.view.max_flow_with_graph("A", "D")

        assert isinstance(results, dict)
        assert len(results) == 1

        flow_value, graph = list(results.values())[0]
        assert flow_value == 5.0
        assert hasattr(graph, "nodes")
        assert hasattr(graph, "edges")

    def test_max_flow_detailed(self):
        """Test max_flow_detailed method."""
        results = self.view.max_flow_detailed("A", "D")

        assert isinstance(results, dict)
        assert len(results) == 1

        flow_value, summary, graph = list(results.values())[0]
        assert flow_value == 5.0
        assert hasattr(summary, "total_flow")
        assert hasattr(graph, "nodes")

    def test_saturated_edges(self):
        """Test saturated_edges method."""
        results = self.view.saturated_edges("A", "D")

        assert isinstance(results, dict)
        assert len(results) == 1

        saturated_list = list(results.values())[0]
        assert isinstance(saturated_list, list)
        # Should identify B->C as saturated (capacity 5.0, fully utilized)

    def test_sensitivity_analysis(self):
        """Test sensitivity_analysis method."""
        results = self.view.sensitivity_analysis("A", "D", change_amount=1.0)

        assert isinstance(results, dict)
        assert len(results) == 1

        sensitivity_dict = list(results.values())[0]
        assert isinstance(sensitivity_dict, dict)

    def test_flow_methods_with_exclusions(self):
        """Test flow methods work correctly with node/link exclusions."""
        # Exclude node B to break the path
        view = NetworkView(_base=self.net, _excluded_nodes=frozenset(["B"]))

        flows = view.max_flow("A", "D")
        flow_value = list(flows.values())[0]
        assert flow_value == 0.0  # No path available

    def test_flow_methods_parameters(self):
        """Test flow methods accept all expected parameters."""
        # Test with all parameters
        flows = self.view.max_flow(
            "A",
            "D",
            mode="combine",
            shortest_path=True,
            flow_placement=FlowPlacement.PROPORTIONAL,
        )

        assert isinstance(flows, dict)


class TestNetworkViewSelectNodeGroups:
    """Test select_node_groups_by_path method."""

    def setup_method(self):
        """Set up test network with grouped nodes."""
        self.net = Network()

        # Add nodes with patterns
        nodes = [
            "dc1_rack1_server1",
            "dc1_rack1_server2",
            "dc1_rack2_server1",
            "dc1_rack2_server2",
            "dc2_rack1_server1",
            "dc2_rack1_server2",
            "edge_router1",
            "edge_router2",
        ]

        for name in nodes:
            self.net.add_node(Node(name))

        # Disable one node
        self.net.nodes["dc1_rack1_server2"].disabled = True

        self.view = NetworkView(_base=self.net)

    def test_select_all_visible_nodes(self):
        """Test selecting all visible nodes."""
        groups = self.view.select_node_groups_by_path(".*")

        # Should get one group with all visible nodes
        assert len(groups) == 1
        group_nodes = list(groups.values())[0]

        # Should exclude disabled node
        node_names = [node.name for node in group_nodes]
        assert "dc1_rack1_server2" not in node_names
        assert len(node_names) == 7  # 8 total - 1 disabled

    def test_select_with_capturing_groups(self):
        """Test selecting nodes with regex capturing groups."""
        groups = self.view.select_node_groups_by_path(r"(dc\d+)_.*")

        # Should group by datacenter
        assert "dc1" in groups
        assert "dc2" in groups

        dc1_nodes = [node.name for node in groups["dc1"]]
        dc2_nodes = [node.name for node in groups["dc2"]]

        # dc1 should have 3 nodes (4 total - 1 disabled)
        assert len(dc1_nodes) == 3
        assert "dc1_rack1_server2" not in dc1_nodes  # disabled

        # dc2 should have 2 nodes
        assert len(dc2_nodes) == 2

    def test_select_with_exclusions(self):
        """Test selecting nodes with analysis exclusions."""
        view = NetworkView(
            _base=self.net, _excluded_nodes=frozenset(["dc1_rack1_server1"])
        )

        groups = view.select_node_groups_by_path(r"(dc1)_.*")

        if "dc1" in groups:
            dc1_nodes = [node.name for node in groups["dc1"]]
            # Should exclude both disabled and analysis-excluded nodes
            assert "dc1_rack1_server1" not in dc1_nodes  # analysis-excluded
            assert "dc1_rack1_server2" not in dc1_nodes  # scenario-disabled
            assert len(dc1_nodes) == 2  # only rack2 servers
        else:
            # If all nodes in group are hidden, group should be empty
            assert len(groups) == 0

    def test_select_no_matches(self):
        """Test selecting with pattern that matches no visible nodes."""
        groups = self.view.select_node_groups_by_path("nonexistent.*")

        assert len(groups) == 0

    def test_select_empty_after_filtering(self):
        """Test selecting where all matching nodes are hidden."""
        # Exclude all dc1 nodes
        view = NetworkView(
            _base=self.net,
            _excluded_nodes=frozenset(
                ["dc1_rack1_server1", "dc1_rack2_server1", "dc1_rack2_server2"]
            ),
        )

        groups = view.select_node_groups_by_path(r"(dc1)_.*")

        # Should return empty dict since all dc1 nodes are hidden
        assert len(groups) == 0


class TestNetworkViewEdgeCases:
    """Test NetworkView edge cases and error conditions."""

    def test_view_of_empty_network(self):
        """Test NetworkView with empty base network."""
        net = Network()
        view = NetworkView(_base=net)

        assert len(view.nodes) == 0
        assert len(view.links) == 0

        # Should handle empty network gracefully
        graph = view.to_strict_multidigraph()
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    def test_view_excluding_all_nodes(self):
        """Test NetworkView that excludes all nodes."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))

        view = NetworkView(_base=net, _excluded_nodes=frozenset(["A", "B"]))

        assert len(view.nodes) == 0

        graph = view.to_strict_multidigraph()
        assert len(graph.nodes) == 0

    def test_view_with_nonexistent_exclusions(self):
        """Test NetworkView with exclusions for nonexistent nodes/links."""
        net = Network()
        net.add_node(Node("A"))

        view = NetworkView(
            _base=net,
            _excluded_nodes=frozenset(["NONEXISTENT"]),
            _excluded_links=frozenset(["NONEXISTENT_LINK"]),
        )

        # Should work normally, ignoring nonexistent exclusions
        assert "A" in view.nodes
        assert len(view.nodes) == 1

    def test_multiple_cache_initialization_calls(self):
        """Test that multiple threads/calls don't break cache initialization."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B"))

        view = NetworkView(_base=net)

        # Multiple calls should be safe
        graph1 = view.to_strict_multidigraph()
        graph2 = view.to_strict_multidigraph()
        graph3 = view.to_strict_multidigraph()

        assert graph1 is graph2 is graph3


class TestNetworkViewIntegration:
    """Test NetworkView integration with Network workflows."""

    def test_view_after_network_modification(self):
        """Test NetworkView behavior after base network is modified."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B")
        net.add_link(link)

        view = NetworkView(_base=net)

        # Cache a graph
        graph1 = view.to_strict_multidigraph()
        assert len(graph1.nodes) == 2

        # Modify base network
        net.disable_node("A")

        # Note: Cache is now stale, but this is documented behavior
        # In practice, views should be created after transforms complete
        cached_graph = view.to_strict_multidigraph()
        assert cached_graph is graph1  # Still returns cached version

        # Fresh view sees the change
        fresh_view = NetworkView(_base=net)
        fresh_graph = fresh_view.to_strict_multidigraph()
        assert len(fresh_graph.nodes) == 1  # Node A is disabled

    def test_view_with_risk_groups(self):
        """Test NetworkView with nodes in risk groups."""
        net = Network()

        # Add nodes with risk groups
        node_a = Node("A", risk_groups={"rg1"})
        node_b = Node("B", risk_groups={"rg1", "rg2"})
        node_c = Node("C")

        net.add_node(node_a)
        net.add_node(node_b)
        net.add_node(node_c)

        # Add risk group
        net.risk_groups["rg1"] = RiskGroup("rg1")

        view = NetworkView(_base=net)

        # Risk groups should be accessible through view
        assert "rg1" in view.risk_groups
        assert view.risk_groups["rg1"].name == "rg1"

        # Nodes should be visible normally
        assert len(view.nodes) == 3

    def test_from_failure_sets_with_iterables(self):
        """Test from_failure_sets with different iterable types."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B")
        net.add_link(link)

        # Test with lists
        view1 = NetworkView.from_failure_sets(
            net, failed_nodes=["A"], failed_links=[link.id]
        )

        # Test with sets
        view2 = NetworkView.from_failure_sets(
            net, failed_nodes={"A"}, failed_links={link.id}
        )

        # Test with tuples
        view3 = NetworkView.from_failure_sets(
            net, failed_nodes=("A",), failed_links=(link.id,)
        )

        # All should have same exclusion sets
        assert view1._excluded_nodes == view2._excluded_nodes == view3._excluded_nodes
        assert view1._excluded_links == view2._excluded_links == view3._excluded_links
