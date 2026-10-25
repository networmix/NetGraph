"""Exact native source allocation, ordered contention and routing semantics."""

from dataclasses import replace
from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    PinnedRoutes,
    RouteSpec,
)
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare
from tests.placement_fixture import demand, matrix, named_flows, network_of

ECMP = FlowPolicyPreset.SHORTEST_PATHS_ECMP
WCMP = FlowPolicyPreset.SHORTEST_PATHS_WCMP
LOSSY = FlowPolicyPreset.SHORTEST_PATHS_ECMP_LOSSY
TE = FlowPolicyPreset.TE_MAXFLOW_UNLIM


@pytest.fixture
def unequal_sources():
    return network_of((("S1", "T", 100, 1), ("S2", "T", 10, 1)))


@pytest.fixture
def far_source():
    return network_of((("S1", "T", 100, 1), ("S2", "T", 100, 2)))


@pytest.fixture
def parallel_pair():
    return network_of((("S", "T", 10, 1), ("S", "T", 100, 1)))


class TestCombineModeOrigination:
    @pytest.mark.parametrize("preset,expected", [(ECMP, 21), (WCMP, 21), (LOSSY, 65)])
    def test_hop_by_hop_splits_evenly_across_sources(
        self, unequal_sources, preset, expected
    ):
        _, state = matrix(unequal_sources, (demand("^S", "^T$", 110, preset),))
        (row,) = state.rows
        # Integer RR21 is11/10. RR22 would put11 on the ten-unit source.
        assert row.reference_request_units == 110
        assert row.result.delivered == state.totals.delivered_units == expected
        assert [source.delivered for source in row.result.by_source] == (
            [55, 10] if preset == LOSSY else [11, 10]
        )

    def test_hop_by_hop_uses_every_source_not_only_the_nearest(self, far_source):
        _, state = matrix(far_source, (demand("^S", "^T$", 150),), details=True)
        (row,) = state.rows
        assert row.result.delivered == 150
        assert [
            (bin.cost, bin.delivered_units) for bin in row.cost_distribution.bins
        ] == [(1, 75), (2, 75)]

    def test_te_keeps_interchangeable_sources(self, unequal_sources, far_source):
        for network, volume, expected_sources in (
            (unequal_sources, 110, [100, 10]),
            (far_source, 150, [100, 50]),
        ):
            _, state = matrix(network, (demand("^S", "^T$", volume, TE),))
            assert state.totals.delivered_units == volume
            assert [
                source.delivered for source in state.rows[0].result.by_source
            ] == expected_sources

    def test_used_edges_are_the_union_over_sources(self, unequal_sources):
        prepared, state = matrix(
            unequal_sources, (demand("^S", "^T$", 110),), details=True
        )
        assert named_flows(prepared, state.rows[0]) == {
            ("S1|T|0", "forward"): 11,
            ("S2|T|0", "forward"): 10,
        }

    def test_lossless_combine_throttles_the_whole_demand(self, unequal_sources):
        _, combined = matrix(unequal_sources, (demand("^S", "^T$", 110),), details=True)
        _, pairwise = matrix(
            unequal_sources, (demand("^S", "^T$", 110, mode="pairwise"),)
        )
        assert combined.totals.delivered_units == 21
        assert combined.rows[0].cost_distribution.bins[0].delivered_units == 21
        assert [row.result.delivered for row in pairwise.rows] == [55, 10]
        assert pairwise.totals.delivered_units == 65

    def test_lossless_combine_scales_globally_over_shared_links(self):
        network = network_of(
            (("S1", "M", 100, 1), ("S2", "M", 20, 1), ("M", "T", 60, 1))
        )
        prepared, lossless = matrix(network, (demand("^S", "^T$", 100),), details=True)
        # RR41 supplies21/20;42 supplies21/21 and cannot fit S2-M.
        assert lossless.totals.delivered_units == 41
        assert named_flows(prepared, lossless.rows[0]) == {
            ("S1|M|0", "forward"): 21,
            ("S2|M|0", "forward"): 20,
            ("M|T|0", "forward"): 41,
        }
        prepared, lossy = matrix(
            network, (demand("^S", "^T$", 100, LOSSY),), details=True
        )
        assert lossy.totals.delivered_units == 60
        drops = {
            (
                prepared.topology.edge_refs[edge].link,
                prepared.topology.edge_refs[edge].direction,
            ): units
            for edge, units in lossy.rows[0].result.edge_drops
        }
        assert drops == {("S2|M|0", "forward"): 30, ("M|T|0", "forward"): 10}

    def test_combine_is_a_pool_an_isolated_source_leaves_the_split(
        self, unequal_sources
    ):
        for preset in (ECMP, WCMP, LOSSY):
            _, state = matrix(
                unequal_sources,
                (demand("^S", "^T$", 110, preset),),
                excluded_links=("S2|T|0",),
                details=True,
            )
            assert state.totals.delivered_units == 100
            assert [source.delivered for source in state.rows[0].result.by_source] == [
                100,
                0,
            ]
            assert state.rows[0].cost_distribution.bins[0].delivered_units == 100
            if preset == LOSSY:
                assert sum(units for _, units in state.rows[0].result.edge_drops) == 10

    def test_pool_with_no_reachable_member_places_nothing(self, unequal_sources):
        for preset in (ECMP, WCMP, LOSSY):
            _, state = matrix(
                unequal_sources,
                (demand("^S", "^T$", 110, preset),),
                excluded_links=("S1|T|0", "S2|T|0"),
            )
            assert state.totals.delivered_units == 0 and not state.totals.feasible
            assert [source.delivered for source in state.rows[0].result.by_source] == [
                0,
                0,
            ]

    def test_fixed_matrix_view_is_per_group(self, unequal_sources):
        spec = DemandSpec(
            Selector("^S", group_by="name"),
            Selector("^T$"),
            110,
            ECMP,
            group_mode="per_group",
        )
        _, state = matrix(unequal_sources, (spec,), excluded_links=("S2|T|0",))
        assert [row.reference_request_units for row in state.rows] == [55, 55]
        assert [row.result.delivered for row in state.rows] == [55, 0]
        assert state.totals.delivered_units == 55 and not state.totals.feasible

    def test_msd_uses_one_prepared_source_roster(self, unequal_sources):
        prepared, _ = matrix(unequal_sources, (demand("^S", "^T$", 110),))
        value = maximum_supported_demand(
            prepared,
            MSDQuery(
                prepared.demand_sets["load"],
                alpha_min=0.1,
                growth_factor=10,
                max_bracket_iters=2,
                max_bisect_iters=1,
            ),
        )
        assert [probe.alpha.value for probe in value.history[:2]] == [1, 0.1]
        assert [probe.totals.delivered_units for probe in value.history[:2]] == [21, 11]
        assert value.alpha_feasible.value == 0.1
        assert value.best_rows[0].endpoints.sources == ("S1", "S2")
        assert [source.delivered for source in value.best_rows[0].result.by_source] == [
            6,
            5,
        ]

    def test_share_goes_to_nearest_target(self):
        prepared, state = matrix(
            network_of((("S", "T1", 100, 1), ("S", "T2", 100, 5))),
            (demand("^S$", "^T", 50),),
            details=True,
        )
        assert state.totals.delivered_units == 50
        assert named_flows(prepared, state.rows[0]) == {("S|T1|0", "forward"): 50}

    def test_resolved_inputs_carry_members(self, unequal_sources):
        prepared, state = matrix(unequal_sources, (demand("^S", "^T$", 110),))
        (row,) = prepared.demand_sets["load"].demands
        assert row.endpoints.sources == ("S1", "S2")
        assert state.rows[0].endpoints == row.endpoints
        assert state.rows[0].result.delivered == 21


class TestEcmpAcrossDemands:
    def test_single_demand_admits_to_the_weakest_member(self, parallel_pair):
        _, state = matrix(parallel_pair, (demand("^S$", "^T$", 100),))
        assert state.rows[0].result.delivered == 20
        assert state.rows[0].result.unadmitted == 80

    def test_saturated_member_blocks_later_lossless_demand(self, parallel_pair):
        _, state = matrix(
            parallel_pair, (demand("^S$", "^T$", 100), demand("^S$", "^T$", 100))
        )
        assert [row.result.delivered for row in state.rows] == [20, 0]

    def test_lossy_delivers_what_survives_and_reports_drops(self, parallel_pair):
        _, state = matrix(
            parallel_pair, (demand("^S$", "^T$", 100, LOSSY),), details=True
        )
        (row,) = state.rows
        assert row.result.delivered == 60
        assert sum(units for _, units in row.result.edge_drops) == 40
        assert row.result.unadmitted == 0

    def test_lossy_later_demand_still_loses_its_hashed_share(self, parallel_pair):
        _, state = matrix(
            parallel_pair,
            (demand("^S$", "^T$", 100, LOSSY), demand("^S$", "^T$", 100, LOSSY)),
            details=True,
        )
        assert [row.result.delivered for row in state.rows] == [60, 50]
        assert [
            sum(units for _, units in row.result.edge_drops) for row in state.rows
        ] == [40, 50]

    def test_lossy_used_edges_include_links_that_carried_then_dropped(self):
        prepared, state = matrix(
            network_of((("S", "M", 100, 1), ("M", "T", 30, 1))),
            (demand("^S$", "^T$", 100, LOSSY),),
            details=True,
        )
        assert named_flows(prepared, state.rows[0]) == {
            ("S|M|0", "forward"): 100,
            ("M|T|0", "forward"): 30,
        }
        assert state.rows[0].result.delivered == 30
        assert sum(units for _, units in state.rows[0].result.edge_drops) == 70

    def test_drop_locations_are_native_even_without_optional_arrays(
        self, parallel_pair
    ):
        _, state = matrix(parallel_pair, (demand("^S$", "^T$", 100, LOSSY),))
        assert state.rows[0].result.delivered == 60
        assert state.rows[0].result.edge_flows is None
        assert sum(units for _, units in state.rows[0].result.edge_drops) == 40


class TestUnrestrictedController:
    def test_controller_uses_more_than_100_distinct_path_costs(self):
        edges = tuple(
            edge
            for index in range(150)
            for edge in (
                ("S", f"M{index:03d}", 1, 1 + index),
                (f"M{index:03d}", "T", 1, 1),
            )
        )
        _, state = matrix(
            network_of(edges), (demand("^S$", "^T$", 150, TE),), details=True
        )
        assert state.rows[0].result.delivered == 150
        assert [
            (bin.marginal_cost, bin.units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(cost, 1) for cost in range(2, 152)]


class TestExactFeasibility:
    def test_many_lsps_on_tiny_volume_are_feasible(self):
        edges = tuple(
            edge
            for index in range(8)
            for edge in (("S", f"M{index}", 100, 1), (f"M{index}", "T", 100, 1))
        )
        prepared, state = matrix(
            network_of(edges),
            (demand("^S$", "^T$", 0.05, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP),),
            q=1 / 4096,
        )
        assert (
            state.totals.reference_request_units == state.totals.delivered_units == 205
        )
        assert state.totals.feasible and state.totals.delivery_ratio == Fraction(1)
        assert prepared.topology.q == 1 / 4096

    def test_each_demand_retains_its_exact_shortfall(self):
        _, state = matrix(
            network_of((("A", "B", 10, 1),)),
            (demand("^A$", "^B$", 8), demand("^A$", "^B$", 8, priority=1)),
        )
        assert [row.result.unadmitted for row in state.rows] == [0, 6]
        assert state.totals.reference_shortfall_units == 6 and not state.totals.feasible


class TestRouteChoicesUnderContention:
    @pytest.fixture
    def detour(self):
        return network_of((("A", "B", 10, 1), ("A", "C", 100, 5), ("C", "B", 100, 5)))

    @pytest.mark.parametrize("preset", [ECMP, WCMP, LOSSY])
    def test_shortest_policy_does_not_use_longer_detour(self, detour, preset):
        prepared, state = matrix(
            detour, (demand("^A$", "^B$", 50, preset),), details=True
        )
        assert state.rows[0].result.delivered == 10
        assert named_flows(prepared, state.rows[0]) == {("A|B|0", "forward"): 10}

    def test_controller_uses_longer_detour(self, detour):
        prepared, state = matrix(detour, (demand("^A$", "^B$", 50, TE),), details=True)
        assert state.rows[0].result.delivered == 50
        assert named_flows(prepared, state.rows[0]) == {
            ("A|B|0", "forward"): 10,
            ("A|C|0", "forward"): 40,
            ("C|B|0", "forward"): 40,
        }

    def test_failure_rebuilds_native_shortest_support(self, detour):
        prepared, state = matrix(
            detour, (demand("^A$", "^B$", 50),), excluded_links=("A|B|0",), details=True
        )
        assert state.rows[0].result.delivered == 50
        assert named_flows(prepared, state.rows[0]) == {
            ("A|C|0", "forward"): 50,
            ("C|B|0", "forward"): 50,
        }


class TestUnservedDemands:
    def test_positive_quantized_request_that_places_nothing_is_infeasible(self):
        network = network_of((("A", "B", 10, 1),), nodes=("C",))
        specs = (demand("^A$", "^B$", 1e-6), demand("^A$", "^C$", 1e-6))
        _, state = matrix(network, specs, q=2**-32)
        assert [row.reference_request_units for row in state.rows] == [4295, 4295]
        assert [row.result.delivered for row in state.rows] == [4295, 0]
        assert not state.totals.feasible and state.totals.delivery_ratio == Fraction(
            1, 2
        )
        _, rounded_zero = matrix(network, specs, q=1)
        assert (
            rounded_zero.totals.reference_request_units == 0
            and rounded_zero.totals.feasible
        )


class TestLossyExplicitRoutes:
    def test_pinned_routes_carry_what_fits(self):
        network = network_of(
            (("A", "B", 10, 1), ("A", "C", 100, 1), ("C", "B", 100, 1))
        )
        routes = {
            "direct": RouteSpec("A", nodes=("A", "B")),
            "detour": RouteSpec("A", nodes=("A", "C", "B")),
        }
        spec = demand(
            "^A$",
            "^B$",
            50,
            PinnedRoutes(("direct", "detour"), admission=ngc.Admission.LOSSY),
        )
        prepared = prepare(
            Scenario(
                network,
                demand_sets={"load": DemandSet("load", (spec,))},
                routes=routes,
                units=UnitsSettings(1),
            ),
            demand_sets=("load",),
        )
        (row,) = (
            place(
                prepared,
                PlacementQuery(
                    prepared.demand_sets["load"],
                    workers=1,
                    export_cost_distribution=True,
                ),
            )
            .cases[0]
            .states["converged"]
            .rows
        )
        assert row.result.delivered == 35
        assert sum(units for _, units in row.result.edge_drops) == 15
        assert [
            (bin.cost, bin.delivered_units) for bin in row.cost_distribution.bins
        ] == [(1, 10), (2, 25)]
        lossless_spec = replace(spec, policy=PinnedRoutes(("direct", "detour")))
        lossless_prepared = prepare(
            Scenario(
                network,
                demand_sets={"load": DemandSet("load", (lossless_spec,))},
                routes=routes,
                units=UnitsSettings(1),
            ),
            demand_sets=("load",),
        )
        assert (
            place(
                lossless_prepared,
                PlacementQuery(lossless_prepared.demand_sets["load"], workers=1),
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 20
        )


def test_pooled_sources_split_together_at_a_shared_router():
    # U and V send one unit each into M, which has two parallel unit links to T (q = 1).
    # One pooled context splits M's two units 1 and 1. Separate per-source contexts would
    # each give their single unit to the first member (highest averages, (1, 0)), so
    # M|T|0 would be asked for 2 and one unit lost.
    network = network_of(
        (("U", "M", 5, 1), ("V", "M", 5, 1), ("M", "T", 1, 1), ("M", "T", 1, 1))
    )
    prepared, state = matrix(network, (demand("^(U|V)$", "^T$", 2),), details=True)
    (row,) = state.rows
    assert row.result.delivered == 2
    assert named_flows(prepared, row) == {
        ("U|M|0", "forward"): 1,
        ("V|M|0", "forward"): 1,
        ("M|T|0", "forward"): 1,
        ("M|T|1", "forward"): 1,
    }


@pytest.mark.parametrize(("dead", "expected"), [("A", 0), ("B", 1)])
def test_a_reachable_zero_capacity_source_keeps_its_equal_share(dead, expected):
    # A->T and B->T, cost 1, one of capacity 0, the other 10; one lossless ECMP demand of 2
    # over the roster A, B (q = 1). Equal source shares by highest averages: unit 1 to A,
    # unit 2 to B. Lossless admission takes the largest request delivered whole: with A
    # dead, 1 already fails (0); with B dead, 1 succeeds and 2 fails (1). Leaving the dead
    # source out of the roster would deliver 2 in both orders.
    network = network_of(tuple((s, "T", 0 if s == dead else 10, 1) for s in ("A", "B")))
    _, state = matrix(network, (demand("^[AB]$", "^T$", 2),))
    (row,) = state.rows
    assert row.result.delivered == expected
    assert [source.delivered for source in row.result.by_source] == (
        [0, 0] if dead == "A" else [1, 0]
    )
