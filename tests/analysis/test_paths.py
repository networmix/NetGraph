"""Tests for shortest path analysis via AnalysisContext.

Tests cover:
- shortest_path_cost: cost only, COMBINE and PAIRWISE modes
- shortest_paths: full Path objects with node sequence and edge references
- k_shortest_paths: multiple paths per pair with cost limits
"""

from __future__ import annotations

import pytest

from ngraph import Link, Mode, Network, Node, analyze


def _simple_path_network() -> Network:
    """Build a small network for path testing.

    Topology:
        A -> B (cost 1, cap 10) -> C (cost 1, cap 10)
        A -> C (cost 3, cap 10)

    Shortest path A->C: via B (cost 2)
    Second path A->C: direct (cost 3)
    """
    net = Network()
    for name in ["A", "B", "C"]:
        net.add_node(Node(name))

    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=3.0))

    return net


def _group_network() -> Network:
    """Build a network with attribute-based groups.

    Topology:
        A (group=src) -> X (cost 1) -> B (group=dst)
        A (group=src) -> Y (cost 2) -> B (group=dst)

    Groups: A has group=src, B has group=dst
    """
    net = Network()
    net.add_node(Node("A", attrs={"group": "src"}))
    net.add_node(Node("X"))
    net.add_node(Node("Y"))
    net.add_node(Node("B", attrs={"group": "dst"}))

    net.add_link(Link("A", "X", capacity=10.0, cost=1.0))
    net.add_link(Link("X", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "Y", capacity=10.0, cost=2.0))
    net.add_link(Link("Y", "B", capacity=10.0, cost=2.0))

    return net


def _multi_source_sink_network() -> Network:
    """Build a network with multiple sources and sinks.

    Topology:
        A (group=src) -> X -> C (group=dst)
        B (group=src) -> X -> D (group=dst)

    Sources: A, B (group=src)
    Sinks: C, D (group=dst)
    """
    net = Network()
    net.add_node(Node("A", attrs={"group": "src"}))
    net.add_node(Node("B", attrs={"group": "src"}))
    net.add_node(Node("X"))
    net.add_node(Node("C", attrs={"group": "dst"}))
    net.add_node(Node("D", attrs={"group": "dst"}))

    net.add_link(Link("A", "X", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "X", capacity=10.0, cost=2.0))
    net.add_link(Link("X", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("X", "D", capacity=10.0, cost=2.0))

    return net


class TestShortestPathCosts:
    """Tests for shortest_path_cost method."""

    def test_pairwise_mode(self) -> None:
        """Test pairwise mode returns costs for each group pair."""
        net = _multi_source_sink_network()

        results = analyze(net).shortest_path_cost(
            {"group_by": "group"}, {"group_by": "group"}, mode=Mode.PAIRWISE
        )

        # With group_by, nodes are grouped by their group attribute value
        # Sources: src (A, B), Sinks: dst (C, D)
        # The only non-self pair is src -> dst
        assert ("src", "dst") in results
        # Best path from src to dst: A->X->C with cost 2
        assert pytest.approx(results[("src", "dst")], abs=1e-9) == 2.0

    def test_combine_mode(self) -> None:
        """Test combine mode returns best cost across all pairs."""
        net = _simple_path_network()

        results = analyze(net).shortest_path_cost("^A$", "^C$", mode=Mode.COMBINE)

        # Best path from A to C: A->B->C with cost 2
        assert len(results) == 1
        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 2.0

    def test_no_path_returns_inf(self) -> None:
        """Test that unreachable pairs return infinity."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        # No link between A and B

        results = analyze(net).shortest_path_cost("^A$", "^B$", mode=Mode.COMBINE)

        assert results[("^A$", "^B$")] == float("inf")

    def test_excluded_nodes(self) -> None:
        """Test that excluded nodes are not used in paths."""
        net = _simple_path_network()

        # Exclude B - only direct A->C path available
        results = analyze(net).shortest_path_cost(
            "^A$", "^C$", mode=Mode.COMBINE, excluded_nodes={"B"}
        )

        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 3.0


class TestShortestPaths:
    """Tests for shortest_paths method."""

    def test_returns_path_objects(self) -> None:
        """Test that shortest_paths returns Path objects."""
        net = _simple_path_network()

        results = analyze(net).shortest_paths("^A$", "^C$", mode=Mode.COMBINE)

        paths = results[("^A$", "^C$")]
        assert len(paths) >= 1

        # Check first path structure
        path = paths[0]
        assert path.cost == 2.0  # A->B->C
        assert len(path.path) == 3  # A, B, C (path attribute is the sequence)

    def test_combine_mode_paths(self) -> None:
        """Test combine mode returns paths for best cost."""
        net = _group_network()

        results = analyze(net).shortest_paths(
            {"group_by": "group"}, {"group_by": "group"}, mode=Mode.COMBINE
        )

        # Should have one result with combined labels
        assert len(results) == 1
        key = list(results.keys())[0]
        paths = results[key]
        # Best path is A->X->B with cost 2
        if paths:  # May be empty if src/dst overlap in combined mode
            assert all(p.cost == 2.0 for p in paths)

    def test_pairwise_mode_paths(self) -> None:
        """Test pairwise mode returns paths per pair."""
        net = _multi_source_sink_network()

        results = analyze(net).shortest_paths(
            {"group_by": "group"}, {"group_by": "group"}, mode=Mode.PAIRWISE
        )

        # Should have a result for src->dst pair
        assert ("src", "dst") in results

    def test_path_contains_node_names(self) -> None:
        """Test that path contains correct node names."""
        net = _simple_path_network()

        results = analyze(net).shortest_paths("^A$", "^C$", mode=Mode.COMBINE)

        paths = results[("^A$", "^C$")]
        path = paths[0]

        # Extract node names from path (path is list of (node_name, edge_refs) tuples)
        node_names = [elem[0] for elem in path.path]
        assert "A" in node_names
        assert "C" in node_names


class TestKShortestPaths:
    """Tests for k_shortest_paths method."""

    def test_returns_multiple_paths(self) -> None:
        """Test that k_shortest_paths can return multiple paths."""
        net = _simple_path_network()

        # Use capturing group to get individual node labels
        results = analyze(net).k_shortest_paths(
            "^(A)$", "^(C)$", max_k=3, mode=Mode.PAIRWISE
        )

        paths = results[("A", "C")]
        # Should have 2 paths: A->B->C (cost 2) and A->C (cost 3)
        assert len(paths) == 2
        assert paths[0].cost <= paths[1].cost  # Sorted by cost

    def test_max_k_limits_paths(self) -> None:
        """Test that max_k limits number of returned paths."""
        net = _simple_path_network()

        results = analyze(net).k_shortest_paths(
            "^(A)$", "^(C)$", max_k=1, mode=Mode.PAIRWISE
        )

        paths = results[("A", "C")]
        assert len(paths) == 1

    def test_combine_mode(self) -> None:
        """Test combine mode returns paths for best group pair."""
        net = _group_network()

        results = analyze(net).k_shortest_paths(
            {"group_by": "group"}, {"group_by": "group"}, max_k=3, mode=Mode.COMBINE
        )

        # Should have one combined result
        assert len(results) == 1

    def test_excluded_nodes(self) -> None:
        """Test that excluded nodes affect k-shortest paths."""
        net = _simple_path_network()

        # Exclude B - only direct A->C path (cost 3) should be available
        results = analyze(net).k_shortest_paths(
            "^(A)$", "^(C)$", max_k=2, mode=Mode.PAIRWISE, excluded_nodes={"B"}
        )

        paths = results[("A", "C")]
        assert len(paths) == 1
        assert paths[0].cost == 3.0

    def test_max_path_cost_factor(self) -> None:
        """Test max_path_cost_factor limits paths by relative cost."""
        net = _simple_path_network()

        # With factor 1.5, only paths up to 1.5 * best_cost = 1.5 * 2 = 3.0
        results = analyze(net).k_shortest_paths(
            "^(A)$", "^(C)$", max_k=5, mode=Mode.PAIRWISE, max_path_cost_factor=1.5
        )

        paths = results[("A", "C")]
        # Both paths (cost 2 and 3) should be included since 3 <= 3.0
        assert len(paths) == 2


class TestDictSelectorsWithShortestPaths:
    """Tests for dict-based selectors with shortest path methods.

    Verifies that shortest_path_cost, shortest_paths, and k_shortest_paths
    correctly handle dict selectors (group_by, match) in both unbound and
    bound context modes.
    """

    def test_shortest_path_cost_with_dict_selector(self) -> None:
        """shortest_path_cost works with dict selectors."""
        net = _multi_source_sink_network()

        results = analyze(net).shortest_path_cost(
            {"group_by": "group"}, {"group_by": "group"}, mode=Mode.PAIRWISE
        )

        assert ("src", "dst") in results
        assert pytest.approx(results[("src", "dst")], abs=1e-9) == 2.0

    def test_shortest_paths_with_match_selector(self) -> None:
        """shortest_paths works with match conditions in selectors."""
        net = _multi_source_sink_network()

        results = analyze(net).shortest_paths(
            {
                "path": ".*",
                "match": {
                    "conditions": [{"attr": "group", "operator": "==", "value": "src"}]
                },
            },
            {
                "path": ".*",
                "match": {
                    "conditions": [{"attr": "group", "operator": "==", "value": "dst"}]
                },
            },
            mode=Mode.COMBINE,
        )

        # Should find paths from src group to dst group
        assert len(results) == 1

    def test_k_shortest_paths_with_dict_selector(self) -> None:
        """k_shortest_paths works with dict selectors."""
        net = _group_network()

        results = analyze(net).k_shortest_paths(
            {"group_by": "group"}, {"group_by": "group"}, max_k=3, mode=Mode.COMBINE
        )

        assert len(results) == 1

    def test_empty_result_when_no_path(self) -> None:
        """Test that no paths are returned when unreachable."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        # No link

        results = analyze(net).k_shortest_paths(
            "^(A)$", "^(B)$", max_k=3, mode=Mode.PAIRWISE
        )

        paths = results[("A", "B")]
        assert len(paths) == 0


class TestPathExclusions:
    """Tests for exclusions in path methods."""

    def test_excluded_links_in_shortest_path(self) -> None:
        """Test excluded links in shortest_path_cost."""
        net = _simple_path_network()

        # Get the A->B link ID
        a_b_link_id = None
        for link_id, link in net.links.items():
            if link.source == "A" and link.target == "B":
                a_b_link_id = link_id
                break

        assert a_b_link_id is not None

        results = analyze(net).shortest_path_cost(
            "^A$", "^C$", mode=Mode.COMBINE, excluded_links={a_b_link_id}
        )

        # Only direct A->C path available (cost 3)
        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 3.0

    def test_disabled_node_in_network(self) -> None:
        """Test that disabled nodes in network are excluded from paths."""
        net = Network()
        for name in ["A", "B", "C"]:
            disabled = name == "B"
            net.add_node(Node(name, disabled=disabled))

        net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
        net.add_link(Link("B", "C", capacity=10.0, cost=1.0))
        net.add_link(Link("A", "C", capacity=10.0, cost=3.0))

        results = analyze(net).shortest_path_cost("^A$", "^C$", mode=Mode.COMBINE)

        # B is disabled, so only direct A->C path (cost 3)
        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 3.0


class TestBoundModePathMethods:
    """Tests for bound mode support in path methods."""

    def test_shortest_path_cost_bound_mode(self) -> None:
        """Test shortest_path_cost works with bound context."""
        net = _simple_path_network()

        # Create bound context
        ctx = analyze(net, source="^A$", sink="^C$")

        # Call without source/sink - should use bound values
        results = ctx.shortest_path_cost()

        # Shortest path A->B->C has cost 2
        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 2.0

    def test_shortest_path_cost_bound_mode_with_exclusions(self) -> None:
        """Test bound mode works with exclusions."""
        net = _simple_path_network()
        ctx = analyze(net, source="^A$", sink="^C$")

        # Exclude B, forcing direct A->C path
        results = ctx.shortest_path_cost(excluded_nodes={"B"})

        # Only direct path A->C (cost 3) available
        assert pytest.approx(results[("^A$", "^C$")], abs=1e-9) == 3.0

    def test_shortest_paths_bound_mode(self) -> None:
        """Test shortest_paths works with bound context."""
        net = _simple_path_network()
        ctx = analyze(net, source="^A$", sink="^C$")

        results = ctx.shortest_paths()

        paths = results[("^A$", "^C$")]
        assert len(paths) >= 1
        # Best path should have cost 2
        assert paths[0].cost == 2.0

    def test_k_shortest_paths_bound_mode(self) -> None:
        """Test k_shortest_paths works with bound context."""
        net = _simple_path_network()
        ctx = analyze(net, source="^A$", sink="^C$")

        results = ctx.k_shortest_paths(max_k=3)

        paths = results[("^A$", "^C$")]
        # Should have at least 2 paths (via B cost 2, direct cost 3)
        assert len(paths) >= 2
        # First should be best (cost 2)
        assert paths[0].cost == 2.0
        # Second should be cost 3
        assert paths[1].cost == 3.0

    def test_bound_mode_rejects_source_sink_args(self) -> None:
        """Test that bound context rejects source/sink arguments."""
        net = _simple_path_network()
        ctx = analyze(net, source="^A$", sink="^C$")

        with pytest.raises(ValueError, match="source/sink already configured"):
            ctx.shortest_path_cost(source="^X$", sink="^Y$")

        with pytest.raises(ValueError, match="source/sink already configured"):
            ctx.shortest_paths(source="^X$", sink="^Y$")

        with pytest.raises(ValueError, match="source/sink already configured"):
            ctx.k_shortest_paths(source="^X$", sink="^Y$")

    def test_unbound_mode_requires_source_sink(self) -> None:
        """Test that unbound context requires source/sink arguments."""
        net = _simple_path_network()
        ctx = analyze(net)  # Unbound

        with pytest.raises(ValueError, match="source and sink are required"):
            ctx.shortest_path_cost()

        with pytest.raises(ValueError, match="source and sink are required"):
            ctx.shortest_paths()

        with pytest.raises(ValueError, match="source and sink are required"):
            ctx.k_shortest_paths()

    def test_bound_properties(self) -> None:
        """Test bound context properties."""
        net = _simple_path_network()

        # Unbound context
        ctx_unbound = analyze(net)
        assert ctx_unbound.is_bound is False
        assert ctx_unbound.bound_source is None
        assert ctx_unbound.bound_sink is None
        assert ctx_unbound.bound_mode is None

        # Bound context
        ctx_bound = analyze(net, source="^A$", sink="^C$", mode=Mode.COMBINE)
        assert ctx_bound.is_bound is True
        assert ctx_bound.bound_source == "^A$"
        assert ctx_bound.bound_sink == "^C$"
        assert ctx_bound.bound_mode == Mode.COMBINE

    def test_node_edge_count_properties(self) -> None:
        """Test node_count and edge_count properties."""
        net = _simple_path_network()
        ctx = analyze(net)

        # 3 nodes: A, B, C
        assert ctx.node_count == 3
        # 3 links x 2 directions = 6 edges
        assert ctx.edge_count == 6
