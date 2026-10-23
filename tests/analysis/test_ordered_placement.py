"""Independent ordered native placements, accounting, masks and cost choices."""

from fractions import Fraction

import pytest

from ngraph.model.demand import FlowPolicyPreset
from tests.placement_fixture import demand, matrix, named_flows, network_of

TE = FlowPolicyPreset.TE_MAXFLOW_UNLIM


@pytest.fixture
def multi_source_network():
    return network_of(
        (
            ("S1", "R1", 100, 1),
            ("S2", "R1", 100, 1),
            ("S3", "R1", 100, 1),
            ("R1", "D1", 200, 1),
            ("R1", "D2", 200, 1),
        )
    )


class TestOrderedShortestPlacements:
    def test_single_demand_ecmp(self, diamond_network):
        _, state = matrix(diamond_network, (demand("^A$", "^D$", 50),))
        (row,) = state.rows
        assert row.endpoints.sources == ("A",) and row.endpoints.destinations == ("D",)
        assert row.result.delivered == 50 and state.totals.feasible

    def test_multiple_demands_same_source(self, multi_source_network):
        _, state = matrix(
            multi_source_network,
            (demand("^S1$", "^D1$", 30), demand("^S1$", "^D2$", 30)),
        )
        assert [row.result.delivered for row in state.rows] == [30, 30]
        assert state.totals.delivered_units == 60 and state.totals.feasible

    def test_demands_from_multiple_sources(self, multi_source_network):
        _, state = matrix(
            multi_source_network,
            (
                demand("^S1$", "^D1$", 50),
                demand("^S2$", "^D1$", 50),
                demand("^S3$", "^D2$", 50),
            ),
        )
        assert [row.result.delivered for row in state.rows] == [50, 50, 50]
        assert state.totals.delivered_units == 150 and state.totals.feasible


@pytest.fixture
def constrained_network():
    return network_of(
        (("A", "B", 50, 1), ("B", "D", 50, 1), ("A", "C", 50, 2), ("C", "D", 50, 2))
    )


class TestOrderedController:
    def test_basic_placement(self, constrained_network):
        prepared, state = matrix(
            constrained_network, (demand("^A$", "^D$", 40, TE),), details=True
        )
        assert state.rows[0].result.delivered == 40
        assert named_flows(prepared, state.rows[0]) == {
            ("A|B|0", "forward"): 40,
            ("B|D|0", "forward"): 40,
        }

    def test_uses_longer_route_when_cheapest_saturates(self, constrained_network):
        prepared, state = matrix(
            constrained_network, (demand("^A$", "^D$", 80, TE),), details=True
        )
        assert state.rows[0].result.delivered == 80
        assert named_flows(prepared, state.rows[0]) == {
            ("A|B|0", "forward"): 50,
            ("B|D|0", "forward"): 50,
            ("A|C|0", "forward"): 30,
            ("C|D|0", "forward"): 30,
        }
        assert [
            (bin.marginal_cost, bin.units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(2, 50), (4, 30)]

    def test_multiple_demands_same_source(self, constrained_network):
        prepared, state = matrix(
            constrained_network,
            (demand("^A$", "^D$", 30, TE), demand("^A$", "^D$", 30, TE, priority=1)),
            details=True,
        )
        assert [row.result.delivered for row in state.rows] == [30, 30]
        assert named_flows(prepared, state.rows[1]) == {
            ("A|B|0", "forward"): 20,
            ("B|D|0", "forward"): 20,
            ("A|C|0", "forward"): 10,
            ("C|D|0", "forward"): 10,
        }
        assert state.totals.delivered_units == 60


class TestOrderedEdgeCases:
    def test_unreachable_destination(self):
        _, state = matrix(
            network_of((("A", "B", 100, 1), ("C", "D", 100, 1))),
            (demand("^A$", "^D$", 50),),
        )
        assert state.rows[0].result.delivered == 0
        assert (
            state.totals.reference_shortfall_units == 50 and not state.totals.feasible
        )

    def test_zero_demand(self):
        _, state = matrix(network_of((("A", "B", 100, 1),)), (demand("^A$", "^B$", 0),))
        assert state.rows[0].result.requested == state.rows[0].result.delivered == 0
        assert state.totals.delivery_ratio == Fraction(1) and state.totals.feasible

    def test_partial_placement_due_to_capacity(self):
        _, state = matrix(network_of((("A", "B", 30, 1),)), (demand("^A$", "^B$", 50),))
        assert state.rows[0].result.delivered == 30
        assert state.rows[0].result.unadmitted == 20
        assert state.totals.delivery_ratio == Fraction(3, 5)

    def test_cost_distribution_absent_when_not_requested(self):
        _, state = matrix(
            network_of((("A", "B", 100, 1),)), (demand("^A$", "^B$", 50),)
        )
        assert state.rows[0].result.delivered == 50
        assert state.rows[0].cost_distribution is None
        assert not state.rows[0].unavailable_outputs

    def test_edge_arrays_absent_when_not_requested(self):
        _, state = matrix(
            network_of((("A", "B", 100, 1),)), (demand("^A$", "^B$", 50),)
        )
        assert state.rows[0].result.delivered == 50
        assert state.rows[0].result.edge_flows is None


@pytest.fixture
def triangle_network():
    return network_of((("A", "B", 100, 1), ("B", "C", 100, 1), ("A", "C", 100, 2)))


class TestOrderedExclusions:
    def test_placement_with_excluded_link(self, triangle_network):
        prepared, state = matrix(
            triangle_network,
            (demand("^A$", "^C$", 50),),
            excluded_links=("A|C|0",),
            details=True,
        )
        assert state.rows[0].result.delivered == 50
        assert named_flows(prepared, state.rows[0]) == {
            ("A|B|0", "forward"): 50,
            ("B|C|0", "forward"): 50,
        }
        assert [
            (bin.cost, bin.delivered_units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(2, 50)]

    def test_placement_with_excluded_node(self, triangle_network):
        prepared, state = matrix(
            triangle_network,
            (demand("^A$", "^C$", 50),),
            excluded_nodes=("B",),
            details=True,
        )
        assert state.rows[0].result.delivered == 50
        assert named_flows(prepared, state.rows[0]) == {("A|C|0", "forward"): 50}


class TestOrderedCostDistribution:
    def test_cost_distribution_single_tier(self, multi_tier_network):
        _, state = matrix(multi_tier_network, (demand("^A$", "^D$", 25),), details=True)
        assert state.rows[0].result.delivered == 25
        assert [
            (bin.cost, bin.delivered_units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(2, 25)]

    def test_cost_distribution_multiple_tiers_controller(self, multi_tier_network):
        _, state = matrix(
            multi_tier_network, (demand("^A$", "^D$", 50, TE),), details=True
        )
        assert state.rows[0].result.delivered == 50
        assert [
            (bin.marginal_cost, bin.units)
            for bin in state.rows[0].cost_distribution.bins
        ] == [(2, 30), (4, 20)]


class TestOrderedSharedRoutes:
    def test_controllers_use_residual_routes_without_moving_prior_traffic(self):
        network = network_of(
            (
                ("A", "B", 50, 1),
                ("B", "D", 50, 1),
                ("B", "E", 50, 1),
                ("A", "C", 50, 2),
                ("C", "D", 50, 2),
            )
        )
        prepared, state = matrix(
            network,
            (demand("^A$", "^D$", 60, TE), demand("^A$", "^E$", 30, TE)),
            details=True,
        )
        assert [row.result.delivered for row in state.rows] == [60, 30]
        assert named_flows(prepared, state.rows[0]) == {
            ("A|B|0", "forward"): 50,
            ("B|D|0", "forward"): 50,
            ("A|C|0", "forward"): 10,
            ("C|D|0", "forward"): 10,
        }
        # A-B is occupied by the first owner; physical D-B remains available in
        # reverse, so the second owner takes A-C-D-B-E, at unit cost6.
        assert named_flows(prepared, state.rows[1]) == {
            ("A|C|0", "forward"): 30,
            ("C|D|0", "forward"): 30,
            ("B|D|0", "reverse"): 30,
            ("B|E|0", "forward"): 30,
        }
        assert state.rows[1].result.total_cost == 180


def test_mixed_models_same_endpoints_keep_separate_native_owners():
    network = network_of(
        (("A", "M1", 5, 1), ("M1", "B", 5, 1), ("A", "M2", 5, 1), ("M2", "B", 5, 1))
    )
    _, state = matrix(
        network,
        (
            demand("^A$", "^B$", 5, id="d1"),
            demand("^A$", "^B$", 5, FlowPolicyPreset.TE_ECMP_16_LSP, id="d2"),
            demand("^A$", "^B$", 5, TE, id="d3", priority=1),
        ),
    )
    assert [row.id for row in state.rows] == ["d1|0", "d2|0", "d3|0"]
    assert [row.result.delivered for row in state.rows] == [5, 0, 5]
    assert state.rows[1].result.plan.insufficient_resolution
    assert state.totals.delivered_units == 10


def test_distinct_ids_allow_same_model_endpoints_and_priority():
    _, state = matrix(
        network_of((("A", "B", 10, 1),)),
        (
            demand("^A$", "^B$", 5, FlowPolicyPreset.TE_ECMP_16_LSP, id="p1"),
            demand("^A$", "^B$", 5, FlowPolicyPreset.TE_ECMP_16_LSP, id="p2"),
        ),
        q=1 / 1024,
    )
    assert [row.id for row in state.rows] == ["p1|0", "p2|0"]
    assert [row.result.delivered for row in state.rows] == [5120, 5120]
    assert state.totals.feasible and state.totals.delivered_units == 10240
