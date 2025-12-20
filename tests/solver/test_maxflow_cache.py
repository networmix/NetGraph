"""Tests for AnalysisContext caching and masking functionality.

This module tests that AnalysisContext correctly handles:
- Disabled nodes (pre-computed in context, applied via masks)
- Disabled links (pre-computed in context, applied via masks)
- Combination of disabled topology and explicit exclusions
- Reuse of context for repeated analysis (bound vs unbound patterns)

These tests validate that disabled topology elements are correctly
masked out in analysis results.
"""

from __future__ import annotations

import pytest

from ngraph import Link, Mode, Network, Node, analyze


def _diamond_network(
    *,
    disable_node_b: bool = False,
    disable_link_a_b: bool = False,
) -> Network:
    """Build a diamond network with optional disabled components.

    Topology:
        A -> B (cap 5) -> D (cap 5)   [path 1, cost 2]
        A -> C (cap 3) -> D (cap 3)   [path 2, cost 4]

    With both paths enabled: max flow = 8 (5 via B + 3 via C)
    With B disabled: max flow = 3 (only via C)
    With A->B link disabled: max flow = 3 (only via C)

    Args:
        disable_node_b: If True, disable node B.
        disable_link_a_b: If True, disable the A->B link.

    Returns:
        Network with configured topology.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=disable_node_b))
    net.add_node(Node("C"))
    net.add_node(Node("D"))

    net.add_link(Link("A", "B", capacity=5.0, cost=1.0, disabled=disable_link_a_b))
    net.add_link(Link("B", "D", capacity=5.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=3.0, cost=2.0))
    net.add_link(Link("C", "D", capacity=3.0, cost=2.0))

    return net


def _linear_network(*, disable_middle: bool = False) -> Network:
    """Build a linear network A -> B -> C with optional disabled middle node.

    Args:
        disable_middle: If True, disable node B.

    Returns:
        Network with linear topology.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B", disabled=disable_middle))
    net.add_node(Node("C"))

    net.add_link(Link("A", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "C", capacity=10.0, cost=1.0))

    return net


class TestDisabledNodes:
    """Tests for disabled node masking in AnalysisContext."""

    def test_disabled_node_blocks_path_bound(self) -> None:
        """Disabled node should block flow through it in bound context."""
        net = _diamond_network(disable_node_b=True)

        # Bound context - source/sink pre-configured
        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.max_flow()

        # Flow should only go through C (capacity 3), not B
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_node_blocks_path_unbound(self) -> None:
        """Disabled node should block flow through it in unbound context."""
        net = _diamond_network(disable_node_b=True)

        # Unbound context - source/sink per-call
        ctx = analyze(net)
        result = ctx.max_flow("^A$", "^D$", mode=Mode.COMBINE)

        # Flow should only go through C (capacity 3), not B
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_node_bound_vs_unbound_consistency(self) -> None:
        """Bound and unbound contexts should produce identical results."""
        net = _diamond_network(disable_node_b=True)

        # Unbound
        result_unbound = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)

        # Bound
        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result_bound = ctx.max_flow()

        assert result_bound == result_unbound

    def test_disabled_node_in_only_path_yields_zero_flow(self) -> None:
        """Disabling the only path's middle node should yield zero flow."""
        net = _linear_network(disable_middle=True)

        ctx = analyze(net, source="^A$", sink="^C$", mode=Mode.COMBINE)
        result = ctx.max_flow()

        assert result[("^A$", "^C$")] == 0.0

    def test_max_flow_detailed_disabled_node(self) -> None:
        """max_flow_detailed should respect disabled nodes."""
        net = _diamond_network(disable_node_b=True)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.max_flow_detailed()

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 3.0

        # Cost distribution should only show cost 4 path (via C)
        assert len(summary.cost_distribution) == 1
        assert 4.0 in summary.cost_distribution

    def test_sensitivity_disabled_node(self) -> None:
        """sensitivity analysis should respect disabled nodes."""
        net = _diamond_network(disable_node_b=True)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.sensitivity()

        sens = result[("^A$", "^D$")]

        # Should only report edges on the C path (A->C, C->D)
        # The B path edges should not appear as they're masked out
        for link_id in sens:
            assert "A[" not in link_id or "B]" not in link_id  # No A->B link
            assert "B[" not in link_id  # No B->D link


class TestDisabledLinks:
    """Tests for disabled link masking in AnalysisContext."""

    def test_disabled_link_blocks_path_bound(self) -> None:
        """Disabled link should block flow through it in bound context."""
        net = _diamond_network(disable_link_a_b=True)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.max_flow()

        # Flow should only go through C (capacity 3)
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_link_blocks_path_unbound(self) -> None:
        """Disabled link should block flow through it in unbound context."""
        net = _diamond_network(disable_link_a_b=True)

        result = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)

        # Flow should only go through C (capacity 3)
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_link_bound_vs_unbound_consistency(self) -> None:
        """Bound and unbound contexts should produce identical results."""
        net = _diamond_network(disable_link_a_b=True)

        result_unbound = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result_bound = ctx.max_flow()

        assert result_bound == result_unbound

    def test_disabled_link_in_only_path_yields_zero_flow(self) -> None:
        """Disabling the only link should yield zero flow."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10.0, disabled=True))

        ctx = analyze(net, source="^A$", sink="^B$", mode=Mode.COMBINE)
        result = ctx.max_flow()

        assert result[("^A$", "^B$")] == 0.0

    def test_max_flow_detailed_disabled_link(self) -> None:
        """max_flow_detailed should respect disabled links."""
        net = _diamond_network(disable_link_a_b=True)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.max_flow_detailed()

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 3.0


class TestCombinedExclusions:
    """Tests for combining disabled topology with explicit exclusions."""

    def test_disabled_node_plus_explicit_node_exclusion(self) -> None:
        """Both disabled and explicitly excluded nodes should be masked."""
        net = _diamond_network(disable_node_b=True)  # B disabled

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        # Also exclude C explicitly - should result in zero flow
        result = ctx.max_flow(excluded_nodes={"C"})

        assert result[("^A$", "^D$")] == 0.0

    def test_disabled_link_plus_explicit_link_exclusion(self) -> None:
        """Both disabled and explicitly excluded links should be masked."""
        net = _diamond_network(disable_link_a_b=True)  # A->B disabled

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        # Get the A->C link ID to exclude it explicitly
        a_c_link_id = None
        for link_id, link in net.links.items():
            if link.source == "A" and link.target == "C":
                a_c_link_id = link_id
                break

        assert a_c_link_id is not None

        result = ctx.max_flow(excluded_links={a_c_link_id})

        assert result[("^A$", "^D$")] == 0.0

    def test_explicit_exclusion_without_disabled_topology(self) -> None:
        """Explicit exclusions should work even when no disabled topology."""
        net = _diamond_network()  # Nothing disabled

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        # Exclude node B explicitly
        result = ctx.max_flow(excluded_nodes={"B"})

        # Should only flow through C
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0


class TestNoDisabledTopology:
    """Tests for context behavior when no topology is disabled."""

    def test_no_disabled_topology_full_flow(self) -> None:
        """With no disabled components, full flow should be achieved."""
        net = _diamond_network()  # Nothing disabled

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result = ctx.max_flow()

        # Full flow through both paths: 5 via B + 3 via C = 8
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 8.0

    def test_bound_vs_unbound_no_disabled(self) -> None:
        """Bound and unbound should match when nothing is disabled."""
        net = _diamond_network()

        result_unbound = analyze(net).max_flow("^A$", "^D$", mode=Mode.COMBINE)

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)
        result_bound = ctx.max_flow()

        assert result_bound == result_unbound


class TestPairwiseMode:
    """Tests for AnalysisContext in pairwise mode with disabled topology."""

    def test_disabled_node_pairwise_mode(self) -> None:
        """Disabled node should be excluded from pairwise mode results."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(
            Node("S2", disabled=True)
        )  # Disabled source - excluded from selection
        net.add_node(Node("M"))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "M", capacity=5.0))
        net.add_link(Link("S2", "M", capacity=5.0))
        net.add_link(Link("M", "T1", capacity=5.0))
        net.add_link(Link("M", "T2", capacity=5.0))

        ctx = analyze(net, source=r"^(S\d)$", sink=r"^(T\d)$", mode=Mode.PAIRWISE)
        result = ctx.max_flow()

        # Only S1 is active, so only S1 -> T1 and S1 -> T2 pairs exist
        assert len(result) == 2
        assert result[("S1", "T1")] == 5.0
        assert result[("S1", "T2")] == 5.0

        # S2 pairs are not in result (S2 is disabled and excluded from selection)
        assert ("S2", "T1") not in result
        assert ("S2", "T2") not in result


class TestContextReuse:
    """Tests for efficient context reuse with different exclusions."""

    def test_multiple_exclusion_scenarios(self) -> None:
        """Same context should work with different exclusion sets."""
        net = _diamond_network()  # Nothing disabled

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        # Baseline - full flow
        baseline = ctx.max_flow()
        assert pytest.approx(baseline[("^A$", "^D$")], abs=1e-9) == 8.0

        # Exclude B
        exclude_b = ctx.max_flow(excluded_nodes={"B"})
        assert pytest.approx(exclude_b[("^A$", "^D$")], abs=1e-9) == 3.0

        # Exclude C
        exclude_c = ctx.max_flow(excluded_nodes={"C"})
        assert pytest.approx(exclude_c[("^A$", "^D$")], abs=1e-9) == 5.0

        # Exclude both B and C - no path
        exclude_both = ctx.max_flow(excluded_nodes={"B", "C"})
        assert exclude_both[("^A$", "^D$")] == 0.0

    def test_bound_context_rejects_source_sink_override(self) -> None:
        """Bound context should reject source/sink arguments."""
        net = _diamond_network()

        ctx = analyze(net, source="^A$", sink="^D$", mode=Mode.COMBINE)

        with pytest.raises(ValueError, match="Bound context"):
            ctx.max_flow(source="^X$", sink="^Y$")

    def test_unbound_context_requires_source_sink(self) -> None:
        """Unbound context should require source/sink arguments."""
        net = _diamond_network()

        ctx = analyze(net)

        with pytest.raises(ValueError, match="Unbound context"):
            ctx.max_flow()

        # But should work with source/sink provided
        result = ctx.max_flow("^A$", "^D$", mode=Mode.COMBINE)
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 8.0
