import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.paths import (
    k_shortest_paths,
    shortest_path_costs,
    shortest_paths,
)
from ngraph.types.base import EdgeSelect


def test_shortest_paths_simple():
    # Create a simple network
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))

    # Test shortest_paths
    results = shortest_paths(net, "A", "B")
    assert ("A", "B") in results
    paths = results[("A", "B")]
    assert len(paths) == 1
    p = paths[0]
    assert p.cost == 1.0
    assert p.nodes_seq == ("A", "B")
    assert len(p.edges) == 1

    # Test shortest_path_costs
    costs = shortest_path_costs(net, "A", "B")
    assert costs[("A", "B")] == 1.0


def test_shortest_paths_no_path():
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    # No link

    results = shortest_paths(net, "A", "B")
    assert ("A", "B") in results
    assert len(results[("A", "B")]) == 0

    costs = shortest_path_costs(net, "A", "B")
    assert costs[("A", "B")] == float("inf")


def test_shortest_paths_mode_pairwise():
    """Test pairwise mode with multiple source/sink groups."""
    net = Network()
    net.add_node(Node("A", attrs={"group": "src"}))
    net.add_node(Node("B", attrs={"group": "src"}))
    net.add_node(Node("C", attrs={"group": "dst"}))
    net.add_node(Node("D", attrs={"group": "dst"}))
    net.add_link(Link("A", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=10.0, cost=2.0))

    results = shortest_paths(net, "attr:group", "attr:group", mode="pairwise")
    # In pairwise mode with attr:group, we get src->src, src->dst, dst->src, dst->dst
    # but only src->dst should have paths
    assert ("src", "dst") in results
    paths = results[("src", "dst")]
    assert len(paths) > 0
    # Should return the shortest path (A->C with cost 1.0)
    assert min(p.cost for p in paths) == 1.0


def test_shortest_paths_mode_combine():
    """Test combine mode aggregating all sources and sinks."""
    net = Network()
    net.add_node(Node("A", attrs={"type": "src"}))
    net.add_node(Node("B", attrs={"type": "src"}))
    net.add_node(Node("C", attrs={"type": "dst"}))
    net.add_link(Link("A", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=3.0))

    # Use regex to select src vs dst nodes
    results = shortest_paths(net, "^[AB]$", "^C$", mode="combine")
    # In combine mode, we get one aggregated label
    assert len(results) == 1
    label = ("^[AB]$", "^C$")
    assert label in results
    paths = results[label]
    assert len(paths) > 0
    assert min(p.cost for p in paths) == 1.0


def test_shortest_path_costs_mode_pairwise():
    """Test shortest_path_costs with pairwise mode."""
    net = Network()
    net.add_node(Node("A", attrs={"group": "src"}))
    net.add_node(Node("B", attrs={"group": "src"}))
    net.add_node(Node("C", attrs={"group": "dst"}))
    net.add_link(Link("A", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=2.0))

    costs = shortest_path_costs(net, "attr:group", "attr:group", mode="pairwise")
    assert ("src", "dst") in costs
    assert costs[("src", "dst")] == 1.0


def test_shortest_path_costs_mode_combine():
    """Test shortest_path_costs with combine mode."""
    net = Network()
    net.add_node(Node("A", attrs={"type": "src"}))
    net.add_node(Node("B", attrs={"type": "src"}))
    net.add_node(Node("C", attrs={"type": "dst"}))
    net.add_link(Link("A", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=3.0))

    # Use regex to select src vs dst nodes
    costs = shortest_path_costs(net, "^[AB]$", "^C$", mode="combine")
    assert len(costs) == 1
    label = ("^[AB]$", "^C$")
    assert label in costs
    assert costs[label] == 1.0


def test_shortest_paths_invalid_mode():
    """Test error handling for invalid mode."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))

    with pytest.raises(
        ValueError, match="Invalid mode.*Must be 'combine' or 'pairwise'"
    ):
        shortest_paths(net, "A", "B", mode="invalid")

    with pytest.raises(
        ValueError, match="Invalid mode.*Must be 'combine' or 'pairwise'"
    ):
        shortest_path_costs(net, "A", "B", mode="invalid")


def test_shortest_paths_no_source_match():
    """Test error handling when no source nodes match."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    with pytest.raises(ValueError, match="No source nodes found matching"):
        shortest_paths(net, "nonexistent", "B")

    with pytest.raises(ValueError, match="No source nodes found matching"):
        shortest_path_costs(net, "nonexistent", "B")


def test_shortest_paths_no_sink_match():
    """Test error handling when no sink nodes match."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    with pytest.raises(ValueError, match="No sink nodes found matching"):
        shortest_paths(net, "A", "nonexistent")

    with pytest.raises(ValueError, match="No sink nodes found matching"):
        shortest_path_costs(net, "A", "nonexistent")


def test_shortest_paths_excluded_nodes():
    """Test shortest paths with excluded nodes."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=10.0))

    # Without exclusion, should go through B
    results = shortest_paths(net, "A", "C")
    paths = results[("A", "C")]
    assert len(paths) > 0
    assert paths[0].cost == 2.0

    # Exclude B, should take direct path
    results_excluded = shortest_paths(net, "A", "C", excluded_nodes={"B"})
    paths_excluded = results_excluded[("A", "C")]
    assert len(paths_excluded) > 0
    assert paths_excluded[0].cost == 10.0


def test_shortest_paths_excluded_links():
    """Test shortest paths with excluded links."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    link1 = Link("A", "B", capacity=10.0, cost=1.0)
    link2 = Link("B", "C", capacity=10.0, cost=1.0)
    link3 = Link("A", "C", capacity=10.0, cost=10.0)
    net.add_link(link1)
    net.add_link(link2)
    net.add_link(link3)

    # Exclude link1, should take direct path
    results = shortest_paths(net, "A", "C", excluded_links={link1.id})
    paths = results[("A", "C")]
    assert len(paths) > 0
    assert paths[0].cost == 10.0


def test_shortest_paths_edge_select_single():
    """Test shortest paths with SINGLE_MIN_COST edge selection."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    # Add multiple parallel edges with same cost
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "B", capacity=20.0, cost=1.0))

    results = shortest_paths(net, "A", "B", edge_select=EdgeSelect.SINGLE_MIN_COST)
    paths = results[("A", "B")]
    assert len(paths) > 0
    assert paths[0].cost == 1.0


def test_shortest_paths_split_parallel_edges():
    """Test shortest paths with split_parallel_edges=True."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    # Create parallel edges
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "B", capacity=20.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=1.0))

    # With split_parallel_edges, should expand parallel edges into distinct paths
    results = shortest_paths(net, "A", "C", split_parallel_edges=True)
    paths = results[("A", "C")]
    # Should have multiple paths due to parallel edges
    assert len(paths) >= 1


def test_shortest_paths_disabled_node():
    """Test that disabled nodes are excluded from paths."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=True))
    net.add_node(Node("C"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=10.0))

    # Should take direct path, avoiding disabled node B
    results = shortest_paths(net, "A", "C")
    paths = results[("A", "C")]
    assert len(paths) > 0
    assert paths[0].cost == 10.0
    assert "B" not in paths[0].nodes


def test_shortest_paths_overlapping_src_sink():
    """Test that overlapping source/sink membership returns no path."""
    net = Network()
    net.add_node(Node("A", attrs={"group": "both"}))
    net.add_node(Node("B", attrs={"group": "both"}))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))

    # Should return empty path list due to overlap
    results = shortest_paths(net, "attr:group", "attr:group")
    paths = results[("both", "both")]
    assert len(paths) == 0

    costs = shortest_path_costs(net, "attr:group", "attr:group")
    assert costs[("both", "both")] == float("inf")


def test_k_shortest_paths_basic():
    """Test k_shortest_paths with a simple network."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("D"))
    # Create multiple paths from A to D
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=2.0))
    net.add_link(Link("C", "D", capacity=10.0, cost=2.0))

    results = k_shortest_paths(net, "A", "D", max_k=2, mode="pairwise")
    assert ("A", "D") in results
    paths = results[("A", "D")]
    assert len(paths) >= 1
    # Paths should be sorted by cost
    if len(paths) > 1:
        assert paths[0].cost <= paths[1].cost


def test_k_shortest_paths_combine_mode():
    """Test k_shortest_paths with combine mode."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))

    # Use regex to select source and destination
    results = k_shortest_paths(net, "^A$", "^B$", max_k=3, mode="combine")
    label = ("^A$", "^B$")
    assert label in results
    paths = results[label]
    assert len(paths) >= 1


def test_k_shortest_paths_with_exclusions():
    """Test k_shortest_paths with excluded nodes."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("D"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=2.0))
    net.add_link(Link("C", "D", capacity=10.0, cost=2.0))

    # Exclude B, should only find path through C
    results = k_shortest_paths(
        net, "A", "D", max_k=2, mode="pairwise", excluded_nodes={"B"}
    )
    paths = results[("A", "D")]
    assert len(paths) >= 1
    # Verify B is not in any path
    for path in paths:
        assert "B" not in path.nodes


def test_k_shortest_paths_max_path_cost_factor():
    """Test k_shortest_paths with max_path_cost_factor."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("D"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=5.0))
    net.add_link(Link("C", "D", capacity=10.0, cost=5.0))

    # Only paths within 1.5x of the shortest should be returned
    results = k_shortest_paths(
        net, "A", "D", max_k=5, mode="pairwise", max_path_cost_factor=1.5
    )
    paths = results[("A", "D")]
    # Shortest path is 2.0, so max allowed is 3.0
    # Path through C is 10.0, should be excluded
    for path in paths:
        assert path.cost <= 3.0


def test_k_shortest_paths_no_path():
    """Test k_shortest_paths when no path exists."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    # No link

    results = k_shortest_paths(net, "A", "B", max_k=3, mode="pairwise")
    assert ("A", "B") in results
    assert len(results[("A", "B")]) == 0


def test_k_shortest_paths_invalid_mode():
    """Test k_shortest_paths error handling for invalid mode."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))

    with pytest.raises(
        ValueError, match="Invalid mode.*Must be 'combine' or 'pairwise'"
    ):
        k_shortest_paths(net, "A", "B", max_k=3, mode="invalid")


def test_k_shortest_paths_no_source_match():
    """Test k_shortest_paths error handling when no source nodes match."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    with pytest.raises(ValueError, match="No source nodes found matching"):
        k_shortest_paths(net, "nonexistent", "B", max_k=3)


def test_k_shortest_paths_no_sink_match():
    """Test k_shortest_paths error handling when no sink nodes match."""
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    with pytest.raises(ValueError, match="No sink nodes found matching"):
        k_shortest_paths(net, "A", "nonexistent", max_k=3)
