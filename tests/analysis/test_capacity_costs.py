"""Opt-in native marginal curves and shortest-path delivered-cost reports."""

import netgraph_core as ngc

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.units import UnitsSettings
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare
from tests.conftest import make_asymmetric_diamond


def _network(nodes, links):
    network = Network(nodes={name: Node(name) for name in nodes})
    for source, target, amount, cost in links:
        network.add_link(Link(source, target, amount, cost))
    return network


def _row(network, source, target, *, config=None):
    prepared = prepare(Scenario(network, units=UnitsSettings(1)))
    options = {} if config is None else {"config": config}
    query = CapacityQuery(
        Selector(source),
        Selector(target),
        workers=1,
        export_cost_distribution=True,
        **options,
    )
    (row,) = capacity(prepared, query).cases[0].states["converged"].rows
    return row


class TestCostDistributionBasic:
    def test_multi_tier_distribution(self):
        row = _row(make_asymmetric_diamond(), "^A$", "^D$")
        assert row.result.delivered == 8
        assert row.cost_distribution.kind == "marginal_curve"
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(2, 5), (4, 3)]

    def test_parallel_equal_cost_distribution(self):
        network = _network(
            ("S", "A", "B", "T"),
            (("S", "A", 5, 1), ("A", "T", 5, 1), ("S", "B", 3, 1), ("B", "T", 3, 1)),
        )
        row = _row(network, "^S$", "^T$")
        assert row.result.delivered == 8
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(2, 8)]

    def test_single_path_distribution(self):
        network = _network(("S", "A", "T"), (("S", "A", 10, 1), ("A", "T", 10, 1)))
        row = _row(network, "^S$", "^T$")
        assert row.result.delivered == 10
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(2, 10)]


class TestShortestPathModel:
    def test_shortest_path_model_uses_only_cheapest_support(self):
        row = _row(
            make_asymmetric_diamond(),
            "^A$",
            "^D$",
            config=ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
        )
        assert row.result.delivered == 5
        assert row.cost_distribution.kind == "delivered_by_path_cost"
        assert [
            (bin.cost, bin.physical_path_cost, bin.delivered_units)
            for bin in row.cost_distribution.bins
        ] == [(2, 2, 5)]


class TestPairwiseMode:
    def test_pairwise_mode_distribution(self):
        network = _network(
            ("S1", "S2", "X", "T1", "T2"),
            (
                ("S1", "X", 5, 1),
                ("S2", "X", 3, 2),
                ("X", "T1", 10, 1),
                ("X", "T2", 10, 2),
            ),
        )
        prepared = prepare(Scenario(network, units=UnitsSettings(1)))
        result = capacity(
            prepared,
            CapacityQuery(
                Selector(r"^(S\d)$"),
                Selector(r"^(T\d)$"),
                mode="pairwise",
                workers=2,
                export_cost_distribution=True,
            ),
        )
        rows = result.cases[0].states["converged"].rows
        assert [
            (
                row.endpoints.sources,
                row.endpoints.destinations,
                row.result.delivered,
                [(bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins],
            )
            for row in rows
        ] == [
            (("S1",), ("T1",), 5, [(2, 5)]),
            (("S1",), ("T2",), 5, [(3, 5)]),
            (("S2",), ("T1",), 3, [(3, 3)]),
            (("S2",), ("T2",), 3, [(4, 3)]),
        ]


class TestNativeController:
    def test_unrestricted_controller_uses_all_routes(self):
        row = _row(make_asymmetric_diamond(), "^A$", "^D$")
        assert row.result.delivered == 8
        assert sum(bin.units for bin in row.cost_distribution.bins) == 8
        assert (
            sum(bin.units * bin.marginal_cost for bin in row.cost_distribution.bins)
            == 22
        )


class TestEdgeCases:
    def test_no_flow_empty_distribution(self):
        row = _row(_network(("A", "B"), ()), "^A$", "^B$")
        assert row.result.delivered == 0
        assert row.cost_distribution.kind == "marginal_curve"
        assert row.cost_distribution.bins == ()

    def test_zero_capacity_path(self):
        network = _network(
            ("A", "B", "C"), (("A", "B", 0, 1), ("B", "C", 10, 1), ("A", "C", 5, 3))
        )
        row = _row(network, "^A$", "^C$")
        assert row.result.delivered == 5
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(3, 5)]
