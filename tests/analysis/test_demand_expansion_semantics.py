"""Expansion semantics tests for group_mode='per_group'.

Pins the documented behavior:
- combine + per_group: one demand per source group with all targets combined.
- pairwise + per_group: pairwise within each group label present on both sides.
- td.volume is split evenly across groups; a skipped group's share (targets
  empty after overlap exclusion, or no non-self pairs) is not redistributed,
  so total expanded volume can be less than td.volume in those edge cases.
- combine mode excludes nodes selected on both sides (no zero-cost pseudo
  bypass when source/target selections overlap).
"""

import pytest

from ngraph.analysis.demand import expand_demands
from ngraph.analysis.functions import demand_placement_analysis
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.network import Link, Network, Node


def _dc_network() -> Network:
    """Two DCs with two nodes each, plus two hub nodes, fully meshed to hubs."""
    network = Network()
    node_names = ["dc1/a", "dc1/b", "dc2/a", "dc2/b", "hub1", "hub2"]
    for name in node_names:
        network.add_node(Node(name))
    for dc_node in ("dc1/a", "dc1/b", "dc2/a", "dc2/b"):
        for hub in ("hub1", "hub2"):
            network.add_link(Link(dc_node, hub, capacity=10.0))
    return network


class TestPerGroupCombine:
    """combine + per_group: one demand per source group, targets combined."""

    def test_one_demand_per_source_group(self) -> None:
        network = _dc_network()
        td = TrafficDemand(
            id="d1",
            source="^(dc[0-9]+)/.*",
            target="^hub.*",
            volume=8.0,
            mode="combine",
            group_mode="per_group",
        )

        expansion = expand_demands(network, [td])

        assert len(expansion.demands) == 2
        # Volume split evenly across source groups; total preserved
        assert all(d.volume == pytest.approx(4.0) for d in expansion.demands)
        assert sum(d.volume for d in expansion.demands) == pytest.approx(8.0)
        # One pseudo source/sink pair per source group
        assert {d.src_name for d in expansion.demands} == {
            "_src_d1|dc1",
            "_src_d1|dc2",
        }
        assert {d.dst_name for d in expansion.demands} == {
            "_snk_d1|dc1",
            "_snk_d1|dc2",
        }

    def test_targets_combined_per_source_group(self) -> None:
        network = _dc_network()
        td = TrafficDemand(
            id="d1",
            source="^(dc[0-9]+)/.*",
            target="^hub.*",
            volume=8.0,
            mode="combine",
            group_mode="per_group",
        )

        expansion = expand_demands(network, [td])

        # Per source group: 2 source attachments + 2 target attachments
        # (BOTH hubs combined), so 8 augmentation edges in total.
        assert len(expansion.augmentations) == 8
        dc1_sources = {
            aug.target for aug in expansion.augmentations if aug.source == "_src_d1|dc1"
        }
        dc1_sinks = {
            aug.source for aug in expansion.augmentations if aug.target == "_snk_d1|dc1"
        }
        assert dc1_sources == {"dc1/a", "dc1/b"}
        assert dc1_sinks == {"hub1", "hub2"}


class TestPerGroupPairwise:
    """pairwise + per_group: pairwise within each same-label group only."""

    def test_pairwise_within_each_group(self) -> None:
        network = _dc_network()
        td = TrafficDemand(
            id="d1",
            source="^(dc[0-9]+)/.*",
            target="^(dc[0-9]+)/.*",
            volume=8.0,
            mode="pairwise",
            group_mode="per_group",
        )

        expansion = expand_demands(network, [td])

        # Within dc1: (a,b), (b,a); within dc2: (a,b), (b,a). No cross-DC pairs.
        assert len(expansion.demands) == 4
        pairs = {(d.src_name, d.dst_name) for d in expansion.demands}
        assert pairs == {
            ("dc1/a", "dc1/b"),
            ("dc1/b", "dc1/a"),
            ("dc2/a", "dc2/b"),
            ("dc2/b", "dc2/a"),
        }
        # 8.0 split across 2 groups, then across 2 pairs per group
        assert all(d.volume == pytest.approx(2.0) for d in expansion.demands)
        assert sum(d.volume for d in expansion.demands) == pytest.approx(8.0)
        # Pairwise mode creates no pseudo nodes
        assert expansion.augmentations == []

    def test_no_shared_labels_yields_no_demands(self) -> None:
        network = _dc_network()
        td = TrafficDemand(
            id="d1",
            source="^(dc[0-9]+)/.*",
            target="^(hub[0-9]+)$",
            volume=8.0,
            mode="pairwise",
            group_mode="per_group",
        )

        # Source labels (dc1, dc2) and target labels (hub1, hub2) are
        # disjoint, so per_group pairwise produces nothing.
        with pytest.raises(ValueError, match="No demands could be expanded"):
            expand_demands(network, [td])


class TestCombineOverlapExclusion:
    """Combine mode excludes nodes selected on both sides.

    Regression: overlapping source/target selections previously attached
    shared nodes to both pseudo endpoints, creating a zero-cost
    pseudo_src -> node -> pseudo_snk bypass over two LARGE_CAPACITY
    augmentation edges that absorbed the entire demand without touching
    the real network.
    """

    @staticmethod
    def _two_group_single_link_network() -> Network:
        """Four nodes in two groups joined by a single capacity-1.0 link."""
        network = Network()
        for name in ("A/1", "A/2", "B/1", "B/2"):
            network.add_node(Node(name))
        network.add_link(Link("A/1", "B/1", capacity=1.0))
        return network

    def test_per_group_combine_excludes_own_group_nodes(self) -> None:
        network = self._two_group_single_link_network()
        td = TrafficDemand(
            id="d1",
            source="^(A|B)/",
            target="^(A|B)/",
            volume=100.0,
            mode="combine",
            group_mode="per_group",
        )

        expansion = expand_demands(network, [td])

        assert len(expansion.demands) == 2
        # Each source group's pseudo sink attaches only the OTHER group's nodes
        snk_a_sources = {
            aug.source for aug in expansion.augmentations if aug.target == "_snk_d1|A"
        }
        snk_b_sources = {
            aug.source for aug in expansion.augmentations if aug.target == "_snk_d1|B"
        }
        assert snk_a_sources == {"B/1", "B/2"}
        assert snk_b_sources == {"A/1", "A/2"}
        # No node is attached to both pseudo endpoints of the same demand
        # (such a node would form a zero-cost bypass)
        for demand in expansion.demands:
            attached_to_src = {
                aug.target
                for aug in expansion.augmentations
                if aug.source == demand.src_name
            }
            attached_to_snk = {
                aug.source
                for aug in expansion.augmentations
                if aug.target == demand.dst_name
            }
            assert not attached_to_src & attached_to_snk

    def test_per_group_combine_placement_bounded_by_real_capacity(self) -> None:
        """Placement is bounded by real capacity, not the pseudo bypass."""
        network = self._two_group_single_link_network()
        demands_config = [
            {
                "source": "^(A|B)/",
                "target": "^(A|B)/",
                "volume": 100.0,
                "mode": "combine",
                "group_mode": "per_group",
            }
        ]

        result = demand_placement_analysis(
            network=network,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=demands_config,
        )

        # The single capacity-1.0 link (plus its reverse edge) bounds
        # placement at 2.0; the bypass previously placed all 100.
        assert result.summary.total_demand == pytest.approx(100.0)
        assert result.summary.total_placed == pytest.approx(2.0)
        assert result.summary.overall_ratio == pytest.approx(0.02)

    def test_flatten_combine_full_overlap_raises(self) -> None:
        network = self._two_group_single_link_network()
        td = TrafficDemand(
            id="d1",
            source="^(A|B)/",
            target="^(A|B)/",
            volume=100.0,
            mode="combine",
            group_mode="flatten",
        )

        # All targets are excluded as overlapping, so nothing expands
        with pytest.raises(ValueError, match="No demands could be expanded"):
            expand_demands(network, [td])

    def test_flatten_combine_partial_overlap_excludes_shared_node(self) -> None:
        network = self._two_group_single_link_network()
        td = TrafficDemand(
            id="d1",
            source="^A/",
            target="^(A/1|B)",  # A/1 is also selected as a source
            volume=10.0,
            mode="combine",
            group_mode="flatten",
        )

        expansion = expand_demands(network, [td])

        assert len(expansion.demands) == 1
        snk_sources = {
            aug.source for aug in expansion.augmentations if aug.target == "_snk_d1"
        }
        assert snk_sources == {"B/1", "B/2"}


class TestPerGroupVolumeConservation:
    """Total expanded volume equals td.volume regardless of group count."""

    def test_combine_volume_conserved_with_three_groups(self) -> None:
        network = Network()
        for name in ("g1/x", "g2/x", "g3/x", "sink"):
            network.add_node(Node(name))
        for name in ("g1/x", "g2/x", "g3/x"):
            network.add_link(Link(name, "sink", capacity=10.0))

        td = TrafficDemand(
            id="d1",
            source="^(g[0-9]+)/.*",
            target="^sink$",
            volume=9.0,
            mode="combine",
            group_mode="per_group",
        )

        expansion = expand_demands(network, [td])

        assert len(expansion.demands) == 3
        assert all(d.volume == pytest.approx(3.0) for d in expansion.demands)
        assert sum(d.volume for d in expansion.demands) == pytest.approx(9.0)


def test_cross_demand_composed_pseudo_collision_raises() -> None:
    """Composed per_group ids can render identically across demands when ids
    or labels contain '|'; the shared pseudo endpoint must be rejected, not
    silently merged (which would recreate the zero-cost bypass)."""
    import pytest

    from ngraph.analysis.functions import demand_placement_analysis
    from ngraph.model.network import Link, Network, Node

    net = Network()
    for name, attrs in (("A1", {"grp": "Y|Z"}), ("T", {}), ("B1", {"grp2": "Z"})):
        net.add_node(Node(name, attrs=attrs))
    net.add_link(Link("A1", "T", capacity=20.0))

    cfg = [
        {
            "id": "X",
            "source": {"path": "^A1$", "group_by": "grp"},
            "target": "^T$",
            "volume": 10.0,
            "mode": "combine",
            "group_mode": "per_group",
        },
        {
            "id": "X|Y",
            "source": {"path": "^B1$", "group_by": "grp2"},
            "target": "^T$",
            "volume": 10.0,
            "mode": "combine",
            "group_mode": "per_group",
        },
    ]
    with pytest.raises(ValueError, match="pseudo endpoint"):
        demand_placement_analysis(
            network=net,
            excluded_nodes=set(),
            excluded_links=set(),
            demands_config=cfg,
        )
