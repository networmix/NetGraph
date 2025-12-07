"""Tests for ngraph.lib.nx NetworkX conversion utilities."""

import networkx as nx
import pytest

from ngraph.lib.nx import EdgeMap, NodeMap, from_networkx, to_networkx


class TestNodeMap:
    """Tests for NodeMap class."""

    def test_from_names_creates_bidirectional_mapping(self):
        """NodeMap.from_names creates correct to_index and to_name mappings."""
        names = ["A", "B", "C"]
        node_map = NodeMap.from_names(names)

        assert node_map.to_index == {"A": 0, "B": 1, "C": 2}
        assert node_map.to_name == {0: "A", 1: "B", 2: "C"}

    def test_from_names_empty_list(self):
        """NodeMap.from_names handles empty list."""
        node_map = NodeMap.from_names([])
        assert len(node_map) == 0
        assert node_map.to_index == {}
        assert node_map.to_name == {}

    def test_len_returns_node_count(self):
        """len(NodeMap) returns number of nodes."""
        node_map = NodeMap.from_names(["X", "Y", "Z"])
        assert len(node_map) == 3

    def test_numeric_node_names(self):
        """NodeMap handles numeric node names."""
        names = [1, 2, 3]
        node_map = NodeMap.from_names(names)

        assert node_map.to_index[1] == 0
        assert node_map.to_name[0] == 1

    def test_mixed_type_node_names(self):
        """NodeMap handles mixed type node names."""
        names = ["A", 1, (0, 1)]
        node_map = NodeMap.from_names(names)

        assert len(node_map) == 3
        assert node_map.to_index[(0, 1)] == 2


class TestEdgeMap:
    """Tests for EdgeMap class."""

    def test_edge_map_direct_construction(self):
        """EdgeMap can be constructed directly with data."""
        edge_map = EdgeMap(
            to_ref={0: ("A", "B", 0), 1: ("B", "C", 0)},
            from_ref={("A", "B", 0): [0], ("B", "C", 0): [1]},
        )

        assert len(edge_map) == 2
        assert edge_map.to_ref[0] == ("A", "B", 0)
        assert edge_map.from_ref[("B", "C", 0)] == [1]

    def test_edge_map_empty_construction(self):
        """EdgeMap can be constructed empty."""
        edge_map = EdgeMap()

        assert len(edge_map) == 0
        assert edge_map.to_ref == {}
        assert edge_map.from_ref == {}

    def test_edge_map_created_from_digraph(self):
        """EdgeMap is created with correct mappings from DiGraph."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)
        G.add_edge("B", "C", capacity=50.0, cost=5)

        _, _, edge_map = from_networkx(G)

        assert len(edge_map) == 2
        # Edge IDs are assigned in iteration order (sorted nodes)
        assert edge_map.to_ref[0] == ("A", "B", 0)
        assert edge_map.to_ref[1] == ("B", "C", 0)

    def test_edge_map_from_multidigraph(self):
        """EdgeMap handles parallel edges in MultiDiGraph."""
        G = nx.MultiDiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)  # key=0
        G.add_edge("A", "B", capacity=50.0, cost=5)  # key=1

        _, _, edge_map = from_networkx(G)

        assert len(edge_map) == 2
        # Parallel edges have different keys
        refs = [edge_map.to_ref[0], edge_map.to_ref[1]]
        assert ("A", "B", 0) in refs
        assert ("A", "B", 1) in refs

    def test_edge_map_from_ref_lookup(self):
        """EdgeMap.from_ref enables lookup from original edge to IDs."""
        G = nx.DiGraph()
        G.add_edge("X", "Y", capacity=1.0, cost=1)

        _, _, edge_map = from_networkx(G)

        # from_ref maps (u, v, key) -> list of edge IDs
        edge_ids = edge_map.from_ref[("X", "Y", 0)]
        assert len(edge_ids) == 1
        assert edge_ids[0] == 0

    def test_edge_map_bidirectional_maps_both_to_same_ref(self):
        """With bidirectional=True, both forward and reverse map to same ref."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)

        _, _, edge_map = from_networkx(G, bidirectional=True)

        # Both edge IDs (0 and 1) map to the original edge reference
        assert edge_map.to_ref[0] == ("A", "B", 0)
        assert edge_map.to_ref[1] == ("A", "B", 0)

        # from_ref shows both IDs for the original edge
        edge_ids = edge_map.from_ref[("A", "B", 0)]
        assert len(edge_ids) == 2
        assert 0 in edge_ids
        assert 1 in edge_ids


class TestFromNetworkx:
    """Tests for from_networkx function."""

    def test_simple_digraph(self):
        """Convert simple DiGraph with capacity and cost."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)
        G.add_edge("B", "C", capacity=50.0, cost=5)

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 3
        assert graph.num_edges() == 2
        assert len(node_map) == 3
        assert len(edge_map) == 2

    def test_multidigraph(self):
        """Convert MultiDiGraph with parallel edges."""
        G = nx.MultiDiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)
        G.add_edge("A", "B", capacity=50.0, cost=5)  # parallel edge

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 2
        assert graph.num_edges() == 2
        assert len(edge_map) == 2

    def test_undirected_graph(self):
        """Convert undirected Graph."""
        G = nx.Graph()
        G.add_edge("X", "Y", capacity=75.0, cost=3)

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 2
        assert graph.num_edges() == 1
        assert len(edge_map) == 1

    def test_multigraph(self):
        """Convert undirected MultiGraph."""
        G = nx.MultiGraph()
        G.add_edge(1, 2, capacity=10.0)
        G.add_edge(1, 2, capacity=20.0)

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 2
        assert graph.num_edges() == 2
        assert len(edge_map) == 2

    def test_bidirectional_adds_reverse_edges(self):
        """bidirectional=True adds reverse edge for each edge."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)

        graph, node_map, edge_map = from_networkx(G, bidirectional=True)

        assert graph.num_edges() == 2  # forward + reverse
        assert len(edge_map) == 2  # Both map to same original ref

        # Verify both directions exist
        src_arr = graph.edge_src_view()
        dst_arr = graph.edge_dst_view()
        edges = set(zip(src_arr.tolist(), dst_arr.tolist(), strict=True))

        a_idx = node_map.to_index["A"]
        b_idx = node_map.to_index["B"]
        assert (a_idx, b_idx) in edges
        assert (b_idx, a_idx) in edges

    def test_default_values_when_attrs_missing(self):
        """Uses default_capacity and default_cost when attributes missing."""
        G = nx.DiGraph()
        G.add_edge("A", "B")  # no capacity/cost attributes

        graph, _, _ = from_networkx(G, default_capacity=999.0, default_cost=42)

        capacity_arr = graph.capacity_view()
        cost_arr = graph.cost_view()

        assert float(capacity_arr[0]) == 999.0
        assert int(cost_arr[0]) == 42

    def test_custom_attribute_names(self):
        """Uses custom attribute names for capacity and cost."""
        G = nx.DiGraph()
        G.add_edge("A", "B", bw=200.0, weight=15)

        graph, _, _ = from_networkx(G, capacity_attr="bw", cost_attr="weight")

        capacity_arr = graph.capacity_view()
        cost_arr = graph.cost_view()

        assert float(capacity_arr[0]) == 200.0
        assert int(cost_arr[0]) == 15

    def test_node_names_sorted_deterministically(self):
        """Node indices are assigned in sorted order for determinism."""
        G = nx.DiGraph()
        G.add_edge("Z", "A")
        G.add_edge("M", "B")

        _, node_map, _ = from_networkx(G)

        # Sorted order: A, B, M, Z
        assert node_map.to_index["A"] == 0
        assert node_map.to_index["B"] == 1
        assert node_map.to_index["M"] == 2
        assert node_map.to_index["Z"] == 3

    def test_graph_with_nodes_no_edges(self):
        """Handles graph with nodes but no edges."""
        G = nx.DiGraph()
        G.add_node("A")
        G.add_node("B")

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 2
        assert graph.num_edges() == 0
        assert len(edge_map) == 0

    def test_raises_on_empty_graph(self):
        """Raises ValueError for graph with no nodes."""
        G = nx.DiGraph()

        with pytest.raises(ValueError, match="no nodes"):
            from_networkx(G)

    def test_raises_on_invalid_type(self):
        """Raises TypeError for non-NetworkX input."""
        with pytest.raises(TypeError, match="Expected NetworkX graph"):
            from_networkx({"not": "a graph"})

    def test_preserves_capacity_and_cost_values(self):
        """Capacity and cost values are preserved exactly."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=123.456, cost=789)

        graph, _, _ = from_networkx(G)

        capacity_arr = graph.capacity_view()
        cost_arr = graph.cost_view()

        assert abs(float(capacity_arr[0]) - 123.456) < 1e-10
        assert int(cost_arr[0]) == 789


class TestToNetworkx:
    """Tests for to_networkx function."""

    def test_roundtrip_simple_digraph(self):
        """Roundtrip: DiGraph -> internal -> DiGraph preserves structure."""
        G_in = nx.DiGraph()
        G_in.add_edge("A", "B", capacity=100.0, cost=10)
        G_in.add_edge("B", "C", capacity=50.0, cost=5)

        graph, node_map, _ = from_networkx(G_in)
        G_out = to_networkx(graph, node_map)

        assert set(G_out.nodes()) == set(G_in.nodes())
        assert G_out.number_of_edges() == G_in.number_of_edges()

        # Check edge attributes
        assert G_out["A"]["B"][0]["capacity"] == 100.0
        assert G_out["A"]["B"][0]["cost"] == 10
        assert G_out["B"]["C"][0]["capacity"] == 50.0
        assert G_out["B"]["C"][0]["cost"] == 5

    def test_roundtrip_multidigraph_parallel_edges(self):
        """Roundtrip preserves parallel edges in MultiDiGraph."""
        G_in = nx.MultiDiGraph()
        G_in.add_edge("X", "Y", capacity=10.0, cost=1)
        G_in.add_edge("X", "Y", capacity=20.0, cost=2)

        graph, node_map, _ = from_networkx(G_in)
        G_out = to_networkx(graph, node_map)

        assert G_out.number_of_edges() == 2
        # Both edges should exist between X and Y
        edges_xy = list(G_out["X"]["Y"].values())
        capacities = sorted([e["capacity"] for e in edges_xy])
        assert capacities == [10.0, 20.0]

    def test_without_node_map_uses_integer_nodes(self):
        """Without node_map, nodes are integer indices."""
        G_in = nx.DiGraph()
        G_in.add_edge("A", "B", capacity=1.0, cost=1)

        graph, _, _ = from_networkx(G_in)
        G_out = to_networkx(graph, node_map=None)

        assert set(G_out.nodes()) == {0, 1}

    def test_custom_attribute_names(self):
        """Uses custom attribute names in output."""
        G_in = nx.DiGraph()
        G_in.add_edge("A", "B", capacity=50.0, cost=5)

        graph, node_map, _ = from_networkx(G_in)
        G_out = to_networkx(
            graph, node_map, capacity_attr="bandwidth", cost_attr="weight"
        )

        edge_data = G_out["A"]["B"][0]
        assert "bandwidth" in edge_data
        assert "weight" in edge_data
        assert edge_data["bandwidth"] == 50.0
        assert edge_data["weight"] == 5

    def test_returns_multidigraph(self):
        """to_networkx always returns MultiDiGraph."""
        G_in = nx.DiGraph()
        G_in.add_edge("A", "B")

        graph, node_map, _ = from_networkx(G_in)
        G_out = to_networkx(graph, node_map)

        assert isinstance(G_out, nx.MultiDiGraph)

    def test_nodes_preserved_when_no_edges(self):
        """Nodes are preserved even when graph has no edges."""
        G_in = nx.DiGraph()
        G_in.add_node("A")
        G_in.add_node("B")

        graph, node_map, _ = from_networkx(G_in)
        G_out = to_networkx(graph, node_map)

        assert set(G_out.nodes()) == {"A", "B"}
        assert G_out.number_of_edges() == 0


class TestMappingCorrectness:
    """Tests that verify mappings are functionally correct."""

    def test_node_map_matches_core_graph_indices(self):
        """NodeMap indices correspond to actual Core graph node indices."""
        G = nx.MultiDiGraph()
        G.add_edge("X", "Y", capacity=10.0, cost=1)
        G.add_edge("Y", "Z", capacity=20.0, cost=2)

        graph, node_map, edge_map = from_networkx(G)

        # Get actual edge data from Core graph
        src_arr = graph.edge_src_view()
        dst_arr = graph.edge_dst_view()

        # For edge X->Y: src should be node_map.to_index["X"], dst should be to_index["Y"]
        x_idx = node_map.to_index["X"]
        y_idx = node_map.to_index["Y"]
        z_idx = node_map.to_index["Z"]

        # Find which Core edge corresponds to X->Y
        xy_edge_ids = edge_map.from_ref[("X", "Y", 0)]
        assert len(xy_edge_ids) == 1
        xy_core_idx = xy_edge_ids[0]

        # Verify Core graph has correct src/dst for this edge
        assert int(src_arr[xy_core_idx]) == x_idx
        assert int(dst_arr[xy_core_idx]) == y_idx

        # Same for Y->Z
        yz_edge_ids = edge_map.from_ref[("Y", "Z", 0)]
        yz_core_idx = yz_edge_ids[0]
        assert int(src_arr[yz_core_idx]) == y_idx
        assert int(dst_arr[yz_core_idx]) == z_idx

    def test_edge_map_matches_ext_edge_ids(self):
        """EdgeMap IDs match ext_edge_ids in Core graph."""
        G = nx.MultiDiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)
        G.add_edge("B", "C", capacity=50.0, cost=5)

        graph, node_map, edge_map = from_networkx(G)

        ext_ids = graph.ext_edge_ids_view()

        # Each ext_edge_id should be the key in edge_map.to_ref
        for core_idx in range(graph.num_edges()):
            ext_id = int(ext_ids[core_idx])
            # ext_id should exist in edge_map.to_ref
            assert ext_id in edge_map.to_ref
            # And should point back to valid edge reference
            u, v, key = edge_map.to_ref[ext_id]
            assert G.has_edge(u, v)

    def test_roundtrip_edge_attributes_via_edge_map(self):
        """Can use edge_map to update original graph after algorithm run."""
        G = nx.MultiDiGraph()
        G.add_edge("S", "A", capacity=100.0, cost=1)
        G.add_edge("A", "T", capacity=100.0, cost=1)
        G.add_edge("S", "B", capacity=50.0, cost=1)
        G.add_edge("B", "T", capacity=50.0, cost=1)

        graph, node_map, edge_map = from_networkx(G)

        # Simulate algorithm output: get capacity for each edge
        capacity_arr = graph.capacity_view()

        # Use edge_map to write back to original graph
        for core_idx in range(graph.num_edges()):
            ext_id = int(graph.ext_edge_ids_view()[core_idx])
            u, v, key = edge_map.to_ref[ext_id]
            # Write some computed value back
            G.edges[u, v, key]["computed_capacity"] = float(capacity_arr[core_idx])

        # Verify values were written correctly
        assert G.edges["S", "A", 0]["computed_capacity"] == 100.0
        assert G.edges["A", "T", 0]["computed_capacity"] == 100.0
        assert G.edges["S", "B", 0]["computed_capacity"] == 50.0
        assert G.edges["B", "T", 0]["computed_capacity"] == 50.0

    def test_bidirectional_edge_map_both_directions_work(self):
        """With bidirectional, both forward and reverse edges can be mapped back."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)

        graph, node_map, edge_map = from_networkx(G, bidirectional=True)

        # Both edges should map to same original edge
        assert graph.num_edges() == 2

        # Get src/dst for both edges
        src_arr = graph.edge_src_view()
        dst_arr = graph.edge_dst_view()

        a_idx = node_map.to_index["A"]
        b_idx = node_map.to_index["B"]

        # Find forward edge (A->B in Core)
        forward_found = False
        reverse_found = False
        for core_idx in range(graph.num_edges()):
            src = int(src_arr[core_idx])
            dst = int(dst_arr[core_idx])
            ext_id = int(graph.ext_edge_ids_view()[core_idx])

            # Both should map to original ("A", "B", 0)
            assert edge_map.to_ref[ext_id] == ("A", "B", 0)

            if src == a_idx and dst == b_idx:
                forward_found = True
            if src == b_idx and dst == a_idx:
                reverse_found = True

        assert forward_found, "Forward edge A->B not found in Core graph"
        assert reverse_found, "Reverse edge B->A not found in Core graph"


class TestIntegrationWithAlgorithms:
    """Integration tests using converted graphs with ngraph algorithms."""

    def test_spf_on_converted_graph(self):
        """SPF algorithm works on converted graph."""
        import netgraph_core

        # Create NetworkX graph
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=10)
        G.add_edge("B", "C", capacity=100.0, cost=10)
        G.add_edge("A", "C", capacity=100.0, cost=30)  # longer path

        graph, node_map, _ = from_networkx(G)

        # Run SPF
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
        handle = algorithms.build_graph(graph)

        src_idx = node_map.to_index["A"]
        dst_idx = node_map.to_index["C"]

        dists, _ = algorithms.spf(handle, src=src_idx, dst=dst_idx)

        # Shortest path A->B->C has cost 20 (10+10), not direct A->C with cost 30
        assert dists[dst_idx] == 20

    def test_max_flow_on_converted_graph(self):
        """Max flow algorithm works on converted graph."""
        import netgraph_core

        # Create NetworkX graph with capacity constraints
        G = nx.DiGraph()
        G.add_edge("S", "A", capacity=10.0, cost=1)
        G.add_edge("S", "B", capacity=10.0, cost=1)
        G.add_edge("A", "T", capacity=10.0, cost=1)
        G.add_edge("B", "T", capacity=10.0, cost=1)

        graph, node_map, _ = from_networkx(G)

        # Run max flow
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
        handle = algorithms.build_graph(graph)

        src_idx = node_map.to_index["S"]
        dst_idx = node_map.to_index["T"]

        flow_value, _ = algorithms.max_flow(handle, src_idx, dst_idx)

        # Max flow should be 20 (two paths of capacity 10 each)
        assert flow_value == 20.0

    def test_bidirectional_enables_undirected_flow(self):
        """bidirectional=True enables flow in both directions."""
        import netgraph_core

        # Single directed edge A->B
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=100.0, cost=1)

        # Without bidirectional: no path B->A
        graph1, node_map1, _ = from_networkx(G, bidirectional=False)
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
        handle1 = algorithms.build_graph(graph1)

        a_idx = node_map1.to_index["A"]
        b_idx = node_map1.to_index["B"]

        flow1, _ = algorithms.max_flow(handle1, b_idx, a_idx)
        assert flow1 == 0.0  # No reverse path

        # With bidirectional: path B->A exists
        graph2, node_map2, _ = from_networkx(G, bidirectional=True)
        handle2 = algorithms.build_graph(graph2)

        flow2, _ = algorithms.max_flow(handle2, b_idx, a_idx)
        assert flow2 == 100.0  # Reverse path available

    def test_edge_map_flow_attribution(self):
        """EdgeMap enables flow attribution back to original edges."""
        import netgraph_core

        # Create NetworkX graph
        G = nx.MultiDiGraph()
        G.add_edge("S", "T", capacity=100.0, cost=1, key="link1")
        G.add_edge("S", "T", capacity=50.0, cost=2, key="link2")

        graph, node_map, edge_map = from_networkx(G)

        # Run max flow
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
        handle = algorithms.build_graph(graph)

        src_idx = node_map.to_index["S"]
        dst_idx = node_map.to_index["T"]

        flow_state = netgraph_core.FlowState(graph)
        _, pred_dag = algorithms.spf(handle, src=src_idx, dst=dst_idx)

        flow_state.place_on_dag(
            src=src_idx,
            dst=dst_idx,
            dag=pred_dag,
            requested_flow=150.0,
            flow_placement=netgraph_core.FlowPlacement.PROPORTIONAL,
        )

        # Map flow back to original edges
        edge_flows = flow_state.edge_flow_view()
        flow_by_ref: dict = {}
        for edge_id, flow in enumerate(edge_flows):
            if flow > 0:
                ref = edge_map.to_ref[edge_id]
                flow_by_ref[ref] = flow

        # Verify we can identify which original edges got flow
        assert len(flow_by_ref) > 0
        for ref in flow_by_ref:
            u, v, key = ref
            assert u == "S"
            assert v == "T"
            assert key in ["link1", "link2"]
