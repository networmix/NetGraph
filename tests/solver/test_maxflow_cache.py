"""Tests for max_flow caching and masking functionality.

This module tests that the cached max_flow path correctly handles:
- Disabled nodes (pre-computed in cache, applied via masks)
- Disabled links (pre-computed in cache, applied via masks)
- Combination of disabled topology and explicit exclusions
- Consistency between cached and non-cached code paths

These tests validate the fix for a bug where disabled_node_ids and
disabled_link_ids were pre-computed in the cache but never applied
when no explicit exclusions were provided.
"""

from __future__ import annotations

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.solver.maxflow import (
    build_maxflow_cache,
    max_flow,
    max_flow_with_details,
    sensitivity_analysis,
)


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


class TestCachedMaxFlowDisabledNodes:
    """Tests for disabled node masking in cached max_flow path."""

    def test_disabled_node_blocks_path_cached(self) -> None:
        """Disabled node should block flow through it when using cache."""
        net = _diamond_network(disable_node_b=True)

        # Build cache (disabled node B is pre-computed)
        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Verify cache captured the disabled node
        assert len(cache.disabled_node_ids) == 1

        # Call max_flow with cache (no explicit exclusions)
        result = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        # Flow should only go through C (capacity 3), not B
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_node_cached_vs_uncached_consistency(self) -> None:
        """Cached and non-cached paths should produce identical results."""
        net = _diamond_network(disable_node_b=True)

        # Non-cached path
        result_uncached = max_flow(net, "^A$", "^D$", mode="combine")

        # Cached path
        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result_cached = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        assert result_cached == result_uncached

    def test_disabled_node_in_only_path_yields_zero_flow(self) -> None:
        """Disabling the only path's middle node should yield zero flow."""
        net = _linear_network(disable_middle=True)

        cache = build_maxflow_cache(net, "^A$", "^C$", mode="combine")
        result = max_flow(net, "^A$", "^C$", mode="combine", _cache=cache)

        assert result[("^A$", "^C$")] == 0.0

    def test_max_flow_with_details_disabled_node_cached(self) -> None:
        """max_flow_with_details should respect disabled nodes via cache."""
        net = _diamond_network(disable_node_b=True)

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result = max_flow_with_details(net, "^A$", "^D$", mode="combine", _cache=cache)

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 3.0

        # Cost distribution should only show cost 4 path (via C)
        assert len(summary.cost_distribution) == 1
        assert 4.0 in summary.cost_distribution

    def test_sensitivity_analysis_disabled_node_cached(self) -> None:
        """sensitivity_analysis should respect disabled nodes via cache."""
        net = _diamond_network(disable_node_b=True)

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result = sensitivity_analysis(net, "^A$", "^D$", mode="combine", _cache=cache)

        sens = result[("^A$", "^D$")]

        # Should only report edges on the C path (A->C, C->D)
        # The B path edges should not appear as they're masked out
        for link_id in sens:
            assert "A[" not in link_id or "B]" not in link_id  # No A->B link
            assert "B[" not in link_id  # No B->D link


class TestCachedMaxFlowDisabledLinks:
    """Tests for disabled link masking in cached max_flow path."""

    def test_disabled_link_blocks_path_cached(self) -> None:
        """Disabled link should block flow through it when using cache."""
        net = _diamond_network(disable_link_a_b=True)

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Verify cache captured the disabled link
        assert len(cache.disabled_link_ids) == 1

        result = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        # Flow should only go through C (capacity 3)
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0

    def test_disabled_link_cached_vs_uncached_consistency(self) -> None:
        """Cached and non-cached paths should produce identical results."""
        net = _diamond_network(disable_link_a_b=True)

        result_uncached = max_flow(net, "^A$", "^D$", mode="combine")

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result_cached = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        assert result_cached == result_uncached

    def test_disabled_link_in_only_path_yields_zero_flow(self) -> None:
        """Disabling the only link should yield zero flow."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_link(Link("A", "B", capacity=10.0, disabled=True))

        cache = build_maxflow_cache(net, "^A$", "^B$", mode="combine")
        result = max_flow(net, "^A$", "^B$", mode="combine", _cache=cache)

        assert result[("^A$", "^B$")] == 0.0

    def test_max_flow_with_details_disabled_link_cached(self) -> None:
        """max_flow_with_details should respect disabled links via cache."""
        net = _diamond_network(disable_link_a_b=True)

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result = max_flow_with_details(net, "^A$", "^D$", mode="combine", _cache=cache)

        summary = result[("^A$", "^D$")]
        assert pytest.approx(summary.total_flow, abs=1e-9) == 3.0


class TestCachedMaxFlowCombinedExclusions:
    """Tests for combining disabled topology with explicit exclusions."""

    def test_disabled_node_plus_explicit_node_exclusion(self) -> None:
        """Both disabled and explicitly excluded nodes should be masked."""
        net = _diamond_network(disable_node_b=True)  # B disabled

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Also exclude C explicitly - should result in zero flow
        result = max_flow(
            net, "^A$", "^D$", mode="combine", _cache=cache, excluded_nodes={"C"}
        )

        assert result[("^A$", "^D$")] == 0.0

    def test_disabled_link_plus_explicit_link_exclusion(self) -> None:
        """Both disabled and explicitly excluded links should be masked."""
        net = _diamond_network(disable_link_a_b=True)  # A->B disabled

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Get the A->C link ID to exclude it explicitly
        a_c_link_id = None
        for link_id, link in net.links.items():
            if link.source == "A" and link.target == "C":
                a_c_link_id = link_id
                break

        assert a_c_link_id is not None

        result = max_flow(
            net,
            "^A$",
            "^D$",
            mode="combine",
            _cache=cache,
            excluded_links={a_c_link_id},
        )

        assert result[("^A$", "^D$")] == 0.0

    def test_explicit_exclusion_without_disabled_topology(self) -> None:
        """Explicit exclusions should work even when no disabled topology."""
        net = _diamond_network()  # Nothing disabled

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Verify no disabled components in cache
        assert len(cache.disabled_node_ids) == 0
        assert len(cache.disabled_link_ids) == 0

        # Exclude node B explicitly
        result = max_flow(
            net, "^A$", "^D$", mode="combine", _cache=cache, excluded_nodes={"B"}
        )

        # Should only flow through C
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 3.0


class TestCachedMaxFlowNoDisabledTopology:
    """Tests for cache behavior when no topology is disabled."""

    def test_no_disabled_topology_full_flow(self) -> None:
        """With no disabled components, full flow should be achieved."""
        net = _diamond_network()  # Nothing disabled

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        assert len(cache.disabled_node_ids) == 0
        assert len(cache.disabled_link_ids) == 0

        result = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        # Full flow through both paths: 5 via B + 3 via C = 8
        assert pytest.approx(result[("^A$", "^D$")], abs=1e-9) == 8.0

    def test_cached_vs_uncached_no_disabled(self) -> None:
        """Cached and non-cached should match when nothing is disabled."""
        net = _diamond_network()

        result_uncached = max_flow(net, "^A$", "^D$", mode="combine")

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")
        result_cached = max_flow(net, "^A$", "^D$", mode="combine", _cache=cache)

        assert result_cached == result_uncached


class TestCachedMaxFlowPairwiseMode:
    """Tests for cached max_flow in pairwise mode with disabled topology."""

    def test_disabled_node_pairwise_mode_cached(self) -> None:
        """Disabled node should be respected in pairwise mode with cache."""
        net = Network()
        net.add_node(Node("S1"))
        net.add_node(Node("S2", disabled=True))  # Disabled source
        net.add_node(Node("M"))
        net.add_node(Node("T1"))
        net.add_node(Node("T2"))

        net.add_link(Link("S1", "M", capacity=5.0))
        net.add_link(Link("S2", "M", capacity=5.0))
        net.add_link(Link("M", "T1", capacity=5.0))
        net.add_link(Link("M", "T2", capacity=5.0))

        cache = build_maxflow_cache(net, r"^(S\d)$", r"^(T\d)$", mode="pairwise")
        result = max_flow(net, r"^(S\d)$", r"^(T\d)$", mode="pairwise", _cache=cache)

        # S1 -> T1 and S1 -> T2 should have flow
        assert result[("S1", "T1")] == 5.0
        assert result[("S1", "T2")] == 5.0

        # S2 -> anything should be 0 (S2 is disabled)
        assert result[("S2", "T1")] == 0.0
        assert result[("S2", "T2")] == 0.0


class TestBuildMaxflowCachePrecomputation:
    """Tests for correct pre-computation of disabled IDs in cache."""

    def test_cache_captures_disabled_node_ids(self) -> None:
        """Cache should pre-compute disabled node IDs correctly."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B", disabled=True))
        net.add_node(Node("C", disabled=True))
        net.add_node(Node("D"))

        net.add_link(Link("A", "B", capacity=1.0))
        net.add_link(Link("B", "C", capacity=1.0))
        net.add_link(Link("C", "D", capacity=1.0))
        net.add_link(Link("A", "D", capacity=1.0))

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        # Should have captured 2 disabled nodes (B and C)
        assert len(cache.disabled_node_ids) == 2

    def test_cache_captures_disabled_link_ids(self) -> None:
        """Cache should pre-compute disabled link IDs correctly."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        net.add_node(Node("C"))

        link1 = Link("A", "B", capacity=1.0, disabled=True)
        link2 = Link("A", "C", capacity=1.0, disabled=True)
        link3 = Link("B", "C", capacity=1.0)

        net.add_link(link1)
        net.add_link(link2)
        net.add_link(link3)

        cache = build_maxflow_cache(net, "^A$", "^C$", mode="combine")

        # Should have captured 2 disabled links
        assert len(cache.disabled_link_ids) == 2

    def test_cache_empty_disabled_sets_when_nothing_disabled(self) -> None:
        """Cache should have empty disabled sets when nothing is disabled."""
        net = _diamond_network()

        cache = build_maxflow_cache(net, "^A$", "^D$", mode="combine")

        assert len(cache.disabled_node_ids) == 0
        assert len(cache.disabled_link_ids) == 0
