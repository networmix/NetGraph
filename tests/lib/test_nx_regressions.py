"""Regression tests for ngraph.lib.nx conversion fixes.

Covers:
- Fractional edge costs raise ValueError instead of silent int() truncation.
- Undirected Graph/MultiGraph inputs default to antiparallel arc pairs so
  connectivity is preserved (bidirectional=None inference).
- Docstring-example semantics: node indices follow sorted-name order while
  edge refs preserve the original (u, v, key) orientation.
"""

import networkx as nx
import pytest

from ngraph.lib.nx import from_networkx


class TestFractionalCostRejection:
    """from_networkx must reject fractional costs, not truncate them."""

    def test_fractional_cost_raises_value_error(self):
        """Fractional edge cost raises ValueError naming the edge."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=10.0, cost=1.9)

        with pytest.raises(ValueError, match=r"'A', 'B'.*1\.9.*not an integer"):
            from_networkx(G)

    def test_fractional_cost_error_suggests_prescaling(self):
        """Error message includes the pre-scaling hint."""
        G = nx.DiGraph()
        G.add_edge("A", "B", cost=0.5)

        with pytest.raises(ValueError, match="Pre-scale fractional costs"):
            from_networkx(G)

    def test_integral_float_cost_accepted(self):
        """Float costs with integral values are accepted and converted."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=10.0, cost=10.0)

        graph, _, _ = from_networkx(G)

        assert int(graph.cost_view()[0]) == 10

    def test_fractional_default_cost_raises(self):
        """Fractional default_cost is rejected when applied to an edge."""
        G = nx.DiGraph()
        G.add_edge("A", "B")  # no cost attribute

        with pytest.raises(ValueError, match="not an integer"):
            from_networkx(G, default_cost=1.5)  # type: ignore[arg-type]

    def test_fractional_cost_in_multigraph_raises(self):
        """Fractional cost on a parallel edge is also rejected."""
        G = nx.MultiDiGraph()
        G.add_edge("A", "B", cost=1)
        G.add_edge("A", "B", cost=2.5)

        with pytest.raises(ValueError, match="not an integer"):
            from_networkx(G)


class TestUndirectedDefaultBidirectional:
    """Undirected inputs must default to antiparallel arc pairs."""

    def test_undirected_graph_default_creates_both_arcs(self):
        """Undirected edge yields arcs in both directions by default."""
        G = nx.Graph()
        G.add_edge("X", "Y", capacity=75.0, cost=3)

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_edges() == 2
        src_arr = graph.edge_src_view()
        dst_arr = graph.edge_dst_view()
        arcs = set(zip(src_arr.tolist(), dst_arr.tolist(), strict=True))
        x_idx = node_map.to_index["X"]
        y_idx = node_map.to_index["Y"]
        assert (x_idx, y_idx) in arcs
        assert (y_idx, x_idx) in arcs
        # Both internal IDs map back to the same undirected edge
        assert edge_map.from_ref[("X", "Y", 0)] == [0, 1]

    def test_undirected_graph_flow_works_in_both_directions(self):
        """Max flow over an undirected edge is nonzero in both directions."""
        import netgraph_core

        G = nx.Graph()
        G.add_edge("A", "B", capacity=100.0, cost=1)

        graph, node_map, _ = from_networkx(G)
        backend = netgraph_core.Backend.cpu()
        algorithms = netgraph_core.Algorithms(backend)
        handle = algorithms.build_graph(graph)

        a_idx = node_map.to_index["A"]
        b_idx = node_map.to_index["B"]

        flow_fwd, _ = algorithms.max_flow(handle, a_idx, b_idx)
        flow_rev, _ = algorithms.max_flow(handle, b_idx, a_idx)
        assert flow_fwd == 100.0
        assert flow_rev == 100.0

    def test_undirected_explicit_false_yields_single_arc(self):
        """Explicit bidirectional=False overrides the undirected default."""
        G = nx.Graph()
        G.add_edge("X", "Y", capacity=75.0, cost=3)

        graph, _, edge_map = from_networkx(G, bidirectional=False)

        assert graph.num_edges() == 1
        assert len(edge_map) == 1

    def test_directed_graph_default_single_arc(self):
        """Directed inputs keep one arc per edge by default."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=10.0, cost=1)

        graph, _, edge_map = from_networkx(G)

        assert graph.num_edges() == 1
        assert len(edge_map) == 1

    def test_directed_explicit_true_adds_reverse(self):
        """Explicit bidirectional=True still works for directed inputs."""
        G = nx.DiGraph()
        G.add_edge("A", "B", capacity=10.0, cost=1)

        graph, _, edge_map = from_networkx(G, bidirectional=True)

        assert graph.num_edges() == 2
        assert len(edge_map) == 2

    def test_multigraph_default_creates_arc_pairs_per_parallel_edge(self):
        """Each parallel undirected edge yields its own antiparallel pair."""
        G = nx.MultiGraph()
        G.add_edge(1, 2, capacity=10.0)
        G.add_edge(1, 2, capacity=20.0)

        graph, _, edge_map = from_networkx(G)

        assert graph.num_edges() == 4
        assert len(edge_map) == 4
        assert len(edge_map.from_ref[(1, 2, 0)]) == 2
        assert len(edge_map.from_ref[(1, 2, 1)]) == 2


class TestDocstringExampleSemantics:
    """Pin the corrected from_networkx docstring example outputs."""

    def test_node_indices_sorted_edge_refs_original_orientation(self):
        """Node indices follow sorted names; edge refs keep (u, v, key)."""
        G = nx.DiGraph()
        G.add_edge("src", "dst", capacity=100.0, cost=10)

        graph, node_map, edge_map = from_networkx(G)

        assert graph.num_nodes() == 2
        assert node_map.to_index == {"dst": 0, "src": 1}
        assert edge_map.to_ref[0] == ("src", "dst", 0)
