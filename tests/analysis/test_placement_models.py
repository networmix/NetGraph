"""Placement model semantics: combine-mode origination, lossless and lossy
ECMP across demands, TE rerouting bounds, and feasibility at engine resolution.
"""

from __future__ import annotations

import netgraph_core
import numpy as np
import pytest

from ngraph.analysis import AnalysisContext
from ngraph.analysis.functions import (
    build_demand_placement_inputs,
    demand_placement_analysis,
)
from ngraph.analysis.placement import (
    CACHEABLE_PRESETS,
    FLOW_RESOLUTION,
    PlacementSummary,
    place_demands,
)
from ngraph.model.flow.policy_config import (
    HOP_BY_HOP_PRESETS,
    FlowPolicyPreset,
    create_flow_policy,
)
from ngraph.model.network import Link, Network, Node

ECMP = FlowPolicyPreset.SHORTEST_PATHS_ECMP
WCMP = FlowPolicyPreset.SHORTEST_PATHS_WCMP
LOSSY = FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY
TE = FlowPolicyPreset.TE_WCMP_UNLIM


def _run(net, demands, excluded_links=None, **kw):
    return demand_placement_analysis(
        net, set(), set(excluded_links or ()), demands, **kw
    )


def _demand(source, target, volume, preset, mode="pairwise", **extra):
    return {
        "source": source,
        "target": target,
        "volume": volume,
        "mode": mode,
        "flow_policy": preset,
        **extra,
    }


@pytest.fixture
def unequal_sources() -> Network:
    """S1 -> T cap 100 and S2 -> T cap 10, equal cost."""
    net = Network()
    for n in ("S1", "S2", "T"):
        net.add_node(Node(n))
    net.add_link(Link("S1", "T", capacity=100, cost=1))
    net.add_link(Link("S2", "T", capacity=10, cost=1))
    return net


@pytest.fixture
def far_source() -> Network:
    """S1 -> T cost 1 and S2 -> T cost 2, both cap 100."""
    net = Network()
    for n in ("S1", "S2", "T"):
        net.add_node(Node(n))
    net.add_link(Link("S1", "T", capacity=100, cost=1))
    net.add_link(Link("S2", "T", capacity=100, cost=2))
    return net


@pytest.fixture
def parallel_pair() -> Network:
    """S -> T over two equal-cost links, cap 10 and cap 100."""
    net = Network()
    for n in ("S", "T"):
        net.add_node(Node(n))
    net.add_link(Link("S", "T", capacity=10, cost=1))
    net.add_link(Link("S", "T", capacity=100, cost=1))
    return net


class TestPresetSets:
    def test_lossy_preset_is_hop_by_hop_and_cacheable(self) -> None:
        assert LOSSY in HOP_BY_HOP_PRESETS
        assert LOSSY in CACHEABLE_PRESETS
        assert HOP_BY_HOP_PRESETS <= CACHEABLE_PRESETS
        assert TE not in HOP_BY_HOP_PRESETS


class TestCombineModeOrigination:
    """A combine demand is a virtual source: its reachable members originate even shares."""

    @pytest.mark.parametrize(
        "preset,expected", [(ECMP, 20.0), (WCMP, 65.0), (LOSSY, 65.0)]
    )
    def test_hop_by_hop_splits_evenly_across_sources(
        self, unequal_sources: Network, preset, expected
    ) -> None:
        # Even split: 55 from S1, 55 from S2. Lossless ECMP admits the demand as
        # a whole at the scale S2 can carry (10/55), so S1 sends 10 too: 20.
        # Best-effort and proportional presets carry each share independently:
        # 55 + 10 = 65.
        r = _run(unequal_sources, [_demand("^S", "^T$", 110, preset, mode="combine")])
        assert len(r.flows) == 1, "a combine demand stays one result entry"
        assert r.summary.total_placed == pytest.approx(expected)
        assert r.flows[0].placed == pytest.approx(expected)
        assert r.flows[0].demand == pytest.approx(110.0)

    def test_hop_by_hop_uses_every_source_not_only_the_nearest(
        self, far_source: Network
    ) -> None:
        r = _run(
            far_source,
            [_demand("^S", "^T$", 150, ECMP, mode="combine")],
            include_flow_details=True,
        )
        assert r.summary.total_placed == pytest.approx(150.0)
        # 75 at cost 1 from S1 and 75 at cost 2 from S2.
        assert r.flows[0].cost_distribution == {
            1.0: pytest.approx(75.0),
            2.0: pytest.approx(75.0),
        }

    def test_te_keeps_interchangeable_sources(
        self, unequal_sources: Network, far_source: Network
    ) -> None:
        # TE carries the aggregate with whichever sources have capacity.
        r = _run(unequal_sources, [_demand("^S", "^T$", 110, TE, mode="combine")])
        assert r.summary.total_placed == pytest.approx(110.0)
        r = _run(far_source, [_demand("^S", "^T$", 150, TE, mode="combine")])
        assert r.summary.total_placed == pytest.approx(150.0)

    def test_used_edges_are_the_union_over_sources(
        self, unequal_sources: Network
    ) -> None:
        r = _run(
            unequal_sources,
            [_demand("^S", "^T$", 110, ECMP, mode="combine")],
            include_used_edges=True,
        )
        edges = set(r.flows[0].data["edges"])
        assert edges == {"S1|T|0:fwd", "S2|T|0:fwd"}

    def test_lossless_combine_throttles_the_whole_demand(
        self, unequal_sources: Network
    ) -> None:
        """Pairwise demands are admitted one by one; a combine demand is one demand."""
        combine = _run(
            unequal_sources,
            [_demand("^S", "^T$", 110, ECMP, mode="combine")],
            include_flow_details=True,
        )
        pairwise = _run(
            unequal_sources, [_demand("^S", "^T$", 110, ECMP, mode="pairwise")]
        )
        assert combine.summary.total_placed == pytest.approx(20.0)
        assert combine.flows[0].cost_distribution == {1.0: pytest.approx(20.0)}
        assert pairwise.summary.total_placed == pytest.approx(65.0)

    def test_lossless_combine_scales_globally_over_shared_links(self) -> None:
        """S1 -> M cap 100, S2 -> M cap 20, M -> T cap 60, demand 100.

        Even split 50/50. S2's link admits 20 of 50 (scale 0.4) and the shared
        link admits 60 of 100 (scale 0.6); the demand takes the smaller: 40.
        Per-source admission would have given S1 50 and S2 10.
        """
        net = Network()
        for n in ("S1", "S2", "M", "T"):
            net.add_node(Node(n))
        net.add_link(Link("S1", "M", capacity=100, cost=1))
        net.add_link(Link("S2", "M", capacity=20, cost=1))
        net.add_link(Link("M", "T", capacity=60, cost=1))
        lossless = _run(
            net,
            [_demand("^S", "^T$", 100, ECMP, mode="combine")],
            include_used_edges=True,
        )
        assert lossless.summary.total_placed == pytest.approx(40.0)
        assert set(lossless.flows[0].data["edges"]) == {
            "S1|M|0:fwd",
            "S2|M|0:fwd",
            "M|T|0:fwd",
        }
        lossy = _run(
            net,
            [_demand("^S", "^T$", 100, LOSSY, mode="combine")],
            include_flow_details=True,
        )
        assert lossy.summary.total_placed == pytest.approx(60.0)
        assert lossy.flows[0].data["dropped_edges"] == {
            "S2|M|0:fwd": pytest.approx(30.0),
            "M|T|0:fwd": pytest.approx(10.0),
        }

    def test_combine_is_a_pool_an_isolated_source_leaves_the_split(
        self, unequal_sources: Network
    ) -> None:
        """The virtual source pools its members: S2 cannot reach T, so S1
        originates the whole volume (110 on a 100 link)."""
        lossless = _run(
            unequal_sources,
            [_demand("^S", "^T$", 110, ECMP, mode="combine")],
            excluded_links={"S2|T|0"},
            include_flow_details=True,
        )
        assert lossless.summary.total_placed == pytest.approx(100.0)
        assert lossless.flows[0].cost_distribution == {1.0: pytest.approx(100.0)}
        lossy = _run(
            unequal_sources,
            [_demand("^S", "^T$", 110, LOSSY, mode="combine")],
            excluded_links={"S2|T|0"},
            include_flow_details=True,
        )
        assert lossy.summary.total_placed == pytest.approx(100.0)
        assert lossy.flows[0].data["dropped_edges"] == {
            "S1|T|0:fwd": pytest.approx(10.0)
        }
        wcmp = _run(
            unequal_sources,
            [_demand("^S", "^T$", 110, WCMP, mode="combine")],
            excluded_links={"S2|T|0"},
        )
        assert wcmp.summary.total_placed == pytest.approx(100.0)

    def test_pool_with_no_reachable_member_places_nothing(
        self, unequal_sources: Network
    ) -> None:
        for preset in (ECMP, LOSSY, WCMP):
            r = _run(
                unequal_sources,
                [_demand("^S", "^T$", 110, preset, mode="combine")],
                excluded_links={"S1|T|0", "S2|T|0"},
            )
            assert r.summary.total_placed == pytest.approx(0.0)
            assert r.summary.dropped_flows == 1

    def test_fixed_matrix_view_is_per_group(self, unequal_sources: Network) -> None:
        """Independent originators: per-source demands, an isolated one is unserved."""
        r = _run(
            unequal_sources,
            [
                _demand(
                    {"path": "^S", "group_by": "name"},
                    "^T$",
                    110,
                    ECMP,
                    mode="combine",
                    group_mode="per_group",
                )
            ],
            excluded_links={"S2|T|0"},
        )
        assert len(r.flows) == 2
        assert r.summary.total_placed == pytest.approx(55.0)
        assert r.summary.dropped_flows == 1

    def test_msd_probes_reuse_the_fanout_dag(self, unequal_sources: Network) -> None:
        ctx, expansion, ids = build_demand_placement_inputs(
            unequal_sources, [_demand("^S", "^T$", 110, ECMP, mode="combine")]
        )
        cache: dict = {}
        for alpha in (1.0, 0.1):
            fg = netgraph_core.FlowGraph(ctx.multidigraph)
            result = place_demands(
                expansion.demands,
                [110.0 * alpha],
                fg,
                ctx,
                ctx.build_node_mask(),
                ctx.build_edge_mask(),
                resolved_ids=ids,
                dag_cache=cache,
            )
            assert result.summary.total_placed == pytest.approx(
                min(20.0, 110.0 * alpha)
            )
        assert len(cache) == 1

    def test_share_goes_to_nearest_target(self) -> None:
        """A source's share is routed to its closest target under IGP."""
        net = Network()
        for n in ("S", "T1", "T2"):
            net.add_node(Node(n))
        net.add_link(Link("S", "T1", capacity=100, cost=1))
        net.add_link(Link("S", "T2", capacity=100, cost=5))
        r = _run(
            net,
            [_demand("^S$", "^T", 50, ECMP, mode="combine")],
            include_used_edges=True,
        )
        assert r.summary.total_placed == pytest.approx(50.0)
        assert r.flows[0].data["edges"] == ["S|T1|0:fwd"]

    def test_msd_inputs_carry_members(self, unequal_sources: Network) -> None:
        ctx, expansion, ids = build_demand_placement_inputs(
            unequal_sources, [_demand("^S", "^T$", 110, ECMP, mode="combine")]
        )
        assert expansion.demands[0].src_members == ("S1", "S2")
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        result = place_demands(
            expansion.demands,
            [d.volume for d in expansion.demands],
            fg,
            ctx,
            ctx.build_node_mask(),
            ctx.build_edge_mask(),
            resolved_ids=ids,
        )
        assert result.summary.total_placed == pytest.approx(20.0)


class TestEcmpAcrossDemands:
    """ECMP hashes over the topology's next hops regardless of load."""

    def test_single_demand_admits_to_the_weakest_member(
        self, parallel_pair: Network
    ) -> None:
        r = _run(parallel_pair, [_demand("^S$", "^T$", 30, ECMP)])
        assert r.flows[0].placed == pytest.approx(20.0)

    def test_saturated_member_blocks_later_lossless_demand(
        self, parallel_pair: Network
    ) -> None:
        r = _run(
            parallel_pair,
            [
                _demand("^S$", "^T$", 20, ECMP, priority=0),
                _demand("^S$", "^T$", 10, ECMP, priority=1),
            ],
        )
        assert r.flows[0].placed == pytest.approx(20.0)
        assert r.flows[1].placed == pytest.approx(0.0), (
            "half of the second demand would be hashed onto the saturated 10-unit "
            "link and lost, so nothing is admitted losslessly"
        )

    def test_lossy_delivers_what_survives_and_reports_drops(
        self, parallel_pair: Network
    ) -> None:
        r = _run(
            parallel_pair,
            [_demand("^S$", "^T$", 100, LOSSY)],
            include_flow_details=True,
        )
        entry = r.flows[0]
        assert entry.placed == pytest.approx(60.0)
        assert entry.dropped == pytest.approx(40.0)
        assert entry.data["dropped_edges"] == {"S|T|0:fwd": pytest.approx(40.0)}
        assert entry.cost_distribution == {1.0: pytest.approx(60.0)}

    def test_lossy_later_demand_still_loses_its_hashed_share(
        self, parallel_pair: Network
    ) -> None:
        r = _run(
            parallel_pair,
            [
                _demand("^S$", "^T$", 20, LOSSY, priority=0),
                _demand("^S$", "^T$", 10, LOSSY, priority=1),
            ],
            include_flow_details=True,
        )
        assert r.flows[0].placed == pytest.approx(20.0)
        assert r.flows[0].data == {}, "nothing dropped, so no dropped_edges key"
        assert r.flows[1].placed == pytest.approx(5.0)
        assert r.flows[1].data["dropped_edges"] == {"S|T|0:fwd": pytest.approx(5.0)}

    def test_lossy_used_edges_include_links_that_carried_then_dropped(self) -> None:
        net = Network()
        for n in ("S", "M", "T"):
            net.add_node(Node(n))
        net.add_link(Link("S", "M", capacity=100, cost=1))
        net.add_link(Link("M", "T", capacity=30, cost=1))
        r = _run(
            net,
            [_demand("^S$", "^T$", 100, LOSSY)],
            include_used_edges=True,
            include_flow_details=True,
        )
        assert r.flows[0].placed == pytest.approx(30.0)
        assert r.flows[0].data["edges"] == ["M|T|0:fwd", "S|M|0:fwd"]
        assert r.flows[0].data["dropped_edges"] == {"M|T|0:fwd": pytest.approx(70.0)}

    def test_dropped_edges_absent_without_flow_details(
        self, parallel_pair: Network
    ) -> None:
        r = _run(parallel_pair, [_demand("^S$", "^T$", 100, LOSSY)])
        assert r.flows[0].placed == pytest.approx(60.0)
        assert "dropped_edges" not in r.flows[0].data


class TestTeReroutingBound:
    def test_te_reroutes_over_more_than_100_cost_tiers(self) -> None:
        net = Network()
        net.add_node(Node("S"))
        net.add_node(Node("T"))
        tiers = 150
        for i in range(tiers):
            m = f"M{i:03d}"
            net.add_node(Node(m))
            net.add_link(Link("S", m, capacity=1, cost=1 + i))
            net.add_link(Link(m, "T", capacity=1, cost=1))
        r = _run(net, [_demand("^S$", "^T$", tiers, TE)], include_flow_details=True)
        assert r.flows[0].placed == pytest.approx(float(tiers))
        assert len(r.flows[0].cost_distribution) == tiers


class TestFeasibilityResolution:
    def test_shortfall_within_engine_resolution_is_feasible(self) -> None:
        s = PlacementSummary(
            total_demand=1.0,
            total_placed=1.0 - FLOW_RESOLUTION / 2,
            max_shortfall=FLOW_RESOLUTION / 2,
        )
        assert s.is_feasible
        s = PlacementSummary(total_demand=1.0, total_placed=0.999, max_shortfall=0.001)
        assert not s.is_feasible

    def test_many_lsps_on_tiny_volume_are_feasible(self) -> None:
        """256 LSPs cannot each carry less than 1/4096; the residue is the engine's, not the network's."""
        net = Network()
        for n in ("S", "T"):
            net.add_node(Node(n))
        for i in range(8):
            m = f"M{i}"
            net.add_node(Node(m))
            net.add_link(Link("S", m, capacity=100, cost=1))
            net.add_link(Link(m, "T", capacity=100, cost=1))
        ctx, expansion, ids = build_demand_placement_inputs(
            net, [_demand("^S$", "^T$", 0.05, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP)]
        )
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        result = place_demands(
            expansion.demands,
            [0.05],
            fg,
            ctx,
            ctx.build_node_mask(),
            ctx.build_edge_mask(),
            resolved_ids=ids,
        )
        assert 0 < result.summary.max_shortfall <= FLOW_RESOLUTION
        assert result.summary.is_feasible

    def test_max_shortfall_is_the_largest_per_demand_gap(self) -> None:
        net = Network()
        for n in ("A", "B"):
            net.add_node(Node(n))
        net.add_link(Link("A", "B", capacity=10, cost=1))
        ctx, expansion, ids = build_demand_placement_inputs(
            net,
            [
                _demand("^A$", "^B$", 8, ECMP),
                _demand("^A$", "^B$", 8, ECMP, priority=1),
            ],
        )
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        result = place_demands(
            expansion.demands,
            [8.0, 8.0],
            fg,
            ctx,
            ctx.build_node_mask(),
            ctx.build_edge_mask(),
            resolved_ids=ids,
        )
        # The first demand takes 8, the second gets the 2 units of headroom.
        assert result.summary.max_shortfall == pytest.approx(6.0)
        assert not result.summary.is_feasible


class TestEnginesAgreeUnderContention:
    """FlowPolicy built from a hop-by-hop preset places what the cached engine places."""

    @pytest.fixture
    def detour(self) -> Network:
        net = Network()
        for n in ("A", "B", "C"):
            net.add_node(Node(n))
        net.add_link(Link("A", "B", capacity=10, cost=1))
        net.add_link(Link("A", "C", capacity=100, cost=5))
        net.add_link(Link("C", "B", capacity=100, cost=5))
        return net

    @pytest.mark.parametrize("preset", [ECMP, WCMP, LOSSY])
    def test_flow_policy_does_not_reroute(self, detour: Network, preset) -> None:
        cached = _run(detour, [_demand("^A$", "^B$", 50, preset)])
        assert cached.flows[0].placed == pytest.approx(10.0)

        ctx = AnalysisContext.from_network(detour)
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        policy = create_flow_policy(
            ctx.algorithms,
            ctx.handle,
            preset,
            node_mask=ctx.build_node_mask(),
            edge_mask=ctx.build_edge_mask(),
        )
        placed, _ = policy.place_demand(
            fg, ctx.node_mapper.to_id("A"), ctx.node_mapper.to_id("B"), 0, 50.0
        )
        assert placed == pytest.approx(10.0)
        assert {float(v[2]) for v in policy.flows.values()} == {1.0}, (
            "the flow stays on the cost-1 path"
        )

    def test_te_flow_policy_still_reroutes(self, detour: Network) -> None:
        ctx = AnalysisContext.from_network(detour)
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        policy = create_flow_policy(ctx.algorithms, ctx.handle, TE)
        placed, _ = policy.place_demand(
            fg, ctx.node_mapper.to_id("A"), ctx.node_mapper.to_id("B"), 0, 50.0
        )
        assert placed == pytest.approx(50.0)

    def test_masks_still_apply_to_hop_by_hop_policies(self, detour: Network) -> None:
        ctx = AnalysisContext.from_network(detour)
        edge_mask = ctx.build_edge_mask({"A|B|0"})
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        policy = create_flow_policy(
            ctx.algorithms,
            ctx.handle,
            ECMP,
            node_mask=ctx.build_node_mask(),
            edge_mask=edge_mask,
        )
        placed, _ = policy.place_demand(
            fg, ctx.node_mapper.to_id("A"), ctx.node_mapper.to_id("B"), 0, 50.0
        )
        assert placed == pytest.approx(50.0), (
            "with A-B failed, the cost-10 path is the shortest path"
        )
        assert isinstance(edge_mask, np.ndarray)


class TestUnservedDemands:
    def test_demand_that_places_nothing_is_never_feasible(self) -> None:
        """Below the engine's resolution a zero placement is not 'within resolution'."""
        net = Network()
        for n in ("A", "B", "C"):
            net.add_node(Node(n))
        net.add_link(Link("A", "B", capacity=10, cost=1))
        ctx, expansion, ids = build_demand_placement_inputs(
            net, [_demand("^A$", "^B$", 1e-6, ECMP), _demand("^A$", "^C$", 1e-6, ECMP)]
        )
        fg = netgraph_core.FlowGraph(ctx.multidigraph)
        result = place_demands(
            expansion.demands,
            [1e-6, 1e-6],
            fg,
            ctx,
            ctx.build_node_mask(),
            ctx.build_edge_mask(),
            resolved_ids=ids,
        )
        assert result.summary.max_shortfall <= FLOW_RESOLUTION
        assert result.summary.unserved_demands == 2
        assert not result.summary.is_feasible

    def test_summary_defaults_keep_old_constructor_working(self) -> None:
        assert PlacementSummary(total_demand=0.0, total_placed=0.0).is_feasible


class TestLossyWithStaticPaths:
    def test_pinned_routes_carry_what_fits(self) -> None:
        """A -> B direct cap 10 and A -> C -> B cap 100, demand 50 pinned to both.

        Lossy: 25 offered per route, 10 + 25 delivered. Lossless ECMP: equal
        carried share, bottleneck 10, so 20.
        """
        net = Network()
        for n in ("A", "B", "C"):
            net.add_node(Node(n))
        net.add_link(Link("A", "B", capacity=10, cost=1))
        net.add_link(Link("A", "C", capacity=100, cost=1))
        net.add_link(Link("C", "B", capacity=100, cost=1))
        routes = [["A", "B"], ["A", "C", "B"]]
        lossy = _run(
            net,
            [_demand("^A$", "^B$", 50, LOSSY, static_paths=routes)],
            include_flow_details=True,
        )
        assert lossy.flows[0].placed == pytest.approx(35.0)
        assert lossy.flows[0].dropped == pytest.approx(15.0)
        assert lossy.flows[0].cost_distribution == {
            1.0: pytest.approx(10.0),
            2.0: pytest.approx(25.0),
        }
        lossless = _run(net, [_demand("^A$", "^B$", 50, ECMP, static_paths=routes)])
        assert lossless.flows[0].placed == pytest.approx(20.0, abs=1e-3)
