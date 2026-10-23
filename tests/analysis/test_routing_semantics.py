"""Native shortest-path splitting and controller route choices have distinct bounds."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.units import UnitsSettings
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare
from tests.placement_fixture import demand, matrix, network_of


def _parallel(capacities=(10, 30, 50), costs=(1, 1, 1)):
    return network_of(
        [
            edge
            for index, (amount, cost) in enumerate(zip(capacities, costs, strict=True))
            for edge in (
                ("S", f"M{index}", amount, cost),
                (f"M{index}", "T", amount, cost),
            )
        ]
    )


def _multi_tier():
    return _parallel((20, 40, 30, 60), (5, 5, 10, 10))


def _config(model):
    if model == "ecmp":
        routing = ngc.ShortestPaths()
    elif model == "wcmp":
        routing = ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.CAPACITY,
        )
    elif model == "shortest_controller":
        routing = ngc.ShortestPaths(allocation=ngc.RouteAllocation.OPTIMIZED)
    else:
        assert model == "controller"
        routing = ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    return ngc.FlowPolicyConfig(routing=routing)


def _prepare(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


def _row(prepared, model, *, costs=False, exclude=None):
    failures = (
        None
        if exclude is None
        else FailureRequest(
            FailurePolicy(
                modes=[FailureMode(1, [FailureRule("node", path=f"^{exclude}$")])]
            ),
            1,
            42,
        )
    )
    value = capacity(
        prepared,
        CapacityQuery(
            Selector("^S$"),
            Selector("^T$"),
            _config(model),
            workers=1,
            failures=failures,
            export_cost_distribution=costs,
        ),
    )
    return value.cases[-1].states["converged"].rows[0]


class TestECMPvsWCMPSemantics:
    def test_ecmp_equal_split_on_unbalanced_paths(self):
        row = _row(_prepare(_parallel()), "ecmp", costs=True)
        assert row.result.delivered == 30
        assert [
            (bin.cost, bin.delivered_units) for bin in row.cost_distribution.bins
        ] == [(2, 30)]

    def test_wcmp_proportional_split_on_unbalanced_paths(self):
        assert _row(_prepare(_parallel()), "wcmp").result.delivered == 90

    def test_ecmp_vs_wcmp_utilization_gap(self):
        prepared = _prepare(_parallel())
        assert _row(prepared, "ecmp").result.delivered == 30
        assert _row(prepared, "wcmp").result.delivered == 90


class TestShortestAndController:
    def test_shortest_models_use_only_lowest_cost_support(self):
        prepared = _prepare(_multi_tier())
        assert _row(prepared, "ecmp").result.delivered == 40
        assert _row(prepared, "wcmp").result.delivered == 60
        assert _row(prepared, "shortest_controller").result.delivered == 60

    def test_controller_uses_all_available_path_costs(self):
        row = _row(_prepare(_multi_tier()), "controller", costs=True)
        assert row.result.delivered == 150
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(10, 60), (20, 90)]


class TestCombinedSemantics:
    @pytest.mark.parametrize(
        "model,expected",
        [("ecmp", 40), ("wcmp", 60), ("shortest_controller", 60), ("controller", 150)],
    )
    def test_semantic_combinations_on_multi_tier(self, model, expected):
        assert _row(_prepare(_multi_tier()), model).result.delivered == expected

    @pytest.mark.parametrize(
        "model,expected",
        [("ecmp", 30), ("wcmp", 90), ("shortest_controller", 90), ("controller", 90)],
    )
    def test_semantic_combinations_on_parallel_paths(self, model, expected):
        assert _row(_prepare(_parallel()), model).result.delivered == expected


class TestCapacityBlindShortest:
    @pytest.mark.parametrize("model", ["ecmp", "wcmp"])
    def test_saturated_shortest_path(self, model):
        prepared = _prepare(_parallel((0, 100), (1, 2)))
        assert _row(prepared, model).result.delivered == 0
        assert _row(prepared, "controller").result.delivered == 100

    @pytest.mark.parametrize("model,expected", [("ecmp", 30), ("wcmp", 90)])
    def test_unbalanced_paths(self, model, expected):
        assert _row(_prepare(_parallel()), model).result.delivered == expected

    def test_available_detour_requires_controller_model(self):
        prepared = _prepare(_parallel((0, 100), (1, 2)))
        assert _row(prepared, "controller").result.delivered == 100
        assert _row(prepared, "ecmp").result.delivered == 0


class TestAccountingValidation:
    @pytest.mark.parametrize(
        "model,expected",
        [("ecmp", 40), ("wcmp", 60), ("shortest_controller", 60), ("controller", 150)],
    )
    def test_cost_distribution_sums_to_total_flow(self, model, expected):
        row = _row(_prepare(_multi_tier()), model, costs=True)
        expected_costs = (
            [(10, 60), (20, 90)] if model == "controller" else [(10, expected)]
        )
        if model == "controller":
            actual = [
                (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
            ]
        else:
            actual = [
                (bin.cost, bin.delivered_units) for bin in row.cost_distribution.bins
            ]
        assert actual == expected_costs
        assert sum(amount for _, amount in actual) == row.result.delivered == expected

    @pytest.mark.parametrize(
        "model,expected",
        [("ecmp", 30), ("wcmp", 90), ("shortest_controller", 90), ("controller", 90)],
    )
    def test_flow_results_are_deterministic(self, model, expected):
        prepared = _prepare(_parallel())
        assert [_row(prepared, model).result.delivered for _ in range(3)] == [
            expected
        ] * 3


class TestLimitedTunnels:
    @pytest.mark.parametrize(
        "capacities,count,uniform,offer",
        [
            ((10, 15, 20, 25, 30, 35, 40, 45), 4, 30, 1000),
            ((10, 20, 30, 40, 50), 2, 40, 500),
        ],
    )
    def test_count_limited_paths_have_independent_capacity_certificate(
        self, capacities, count, uniform, offer
    ):
        # With disjoint paths a candidate size is possible iff their integer
        # tunnel slots sum to at least the requested count. No solver helper.
        assert sum(amount // uniform for amount in capacities) >= count
        assert sum(amount // (uniform + 1) for amount in capacities) < count
        routing = ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.OPTIMIZED,
            tunnel_count=ngc.TunnelCount(count),
            prefer_headroom=True,
        )
        config = ngc.FlowPolicyConfig(routing=routing)
        network = _parallel(capacities, tuple(range(1, len(capacities) + 1)))
        prepared, state = matrix(
            network, [demand("^S$", "^T$", offer, config)], details=True
        )
        result = state.rows[0].result
        assert result.plan.max_bandwidth_per_tunnel == uniform
        assert result.plan.max_fractional_bandwidth_per_tunnel == Fraction(uniform)
        assert result.plan.planned_bandwidth_per_tunnel == uniform
        tunnels = result.program.tunnels
        assert len(tunnels) == result.plan.tunnels_per_head == count
        branches = [
            int(prepared.topology.edge_refs[tunnel.edges[0]].link.split("|")[1][1:])
            for tunnel in tunnels
        ]
        assert set(branches) == set(range(len(capacities) - count, len(capacities)))
        # The actual admission is the largest integer RR prefix on those paths;
        # it need not equal the fluid product count*uniform.
        feasible = []
        for amount in range(sum(capacities) + 1):
            shares = [
                amount // count + (index < amount % count) for index in range(count)
            ]
            if all(
                share <= capacities[branch]
                for share, branch in zip(shares, branches, strict=True)
            ):
                feasible.append(amount)
        expected = max(feasible)
        assert result.delivered == expected
        assert result.unadmitted == offer - expected
        assert [flow.delivered for flow in result.by_tunnel] == [
            expected // count + (index < expected % count) for index in range(count)
        ]
        assert state.totals.reference_request_units == offer
        assert state.totals.delivered_units == expected and not state.totals.feasible


class TestPreparedReuse:
    def test_multiple_flow_calls_same_prepared_topology(self):
        prepared = _prepare(_multi_tier())
        assert [
            _row(prepared, model).result.delivered
            for model in ("wcmp", "ecmp", "controller", "wcmp")
        ] == [60, 40, 150, 60]

    def test_exclusions_with_same_prepared_topology(self):
        prepared = _prepare(_multi_tier())
        assert _row(prepared, "controller").result.delivered == 150
        assert _row(prepared, "controller", exclude="M0").result.delivered == 130
        assert _row(prepared, "controller").result.delivered == 150
