"""Nominal disabled components and sampled exclusions share one native mask."""

import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.units import UnitsSettings
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Condition, Selector
from ngraph.scenario import Scenario, prepare
from tests.conftest import make_asymmetric_diamond


def _prepare(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


def _query(*, nodes=(), links=(), costs=False, source="^A$", target="^D$"):
    rules = [
        FailureRule(scope, [Condition(field, "in", list(names))])
        for scope, field, names in (("node", "name", nodes), ("link", "id", links))
        if names
    ]
    failures = (
        FailureRequest(FailurePolicy(modes=[FailureMode(1, rules)]), 1, 42)
        if rules
        else None
    )
    return CapacityQuery(
        Selector(source),
        Selector(target),
        failures=failures,
        workers=1,
        export_cost_distribution=costs,
    )


def _row(prepared, **kwargs):
    return capacity(prepared, _query(**kwargs)).cases[-1].states["converged"].rows[0]


class TestDisabledNodes:
    @pytest.mark.parametrize("reuse", [False, True])
    def test_disabled_node_blocks_path(self, reuse):
        network = make_asymmetric_diamond(disable_node_b=True)
        prepared = _prepare(network)
        assert _row(prepared).result.delivered == 3
        assert _row(prepared if reuse else _prepare(network)).result.delivered == 3

    def test_disabled_node_in_only_path_yields_zero_flow(self):
        network = Network(
            nodes={name: Node(name, disabled=name == "B") for name in "ABC"}
        )
        network.add_link(Link("A", "B", 10, 1))
        network.add_link(Link("B", "C", 10, 1))
        assert _row(_prepare(network), target="^C$").result.delivered == 0
        network.enable_node("B")
        assert _row(_prepare(network), target="^C$").result.delivered == 10

    def test_costs_respect_disabled_node(self):
        row = _row(_prepare(make_asymmetric_diamond(disable_node_b=True)), costs=True)
        assert row.result.delivered == 3
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(4, 3)]

    def test_sensitivity_disabled_node(self):
        prepared = _prepare(make_asymmetric_diamond(disable_node_b=True))
        topology = prepared.topology
        value = edge_sensitivity(
            prepared,
            SensitivityQuery(
                Selector("^A$"),
                Selector("^D$"),
                _query().config,
                workers=1,
            ),
        )
        assert value.result.baseline.delivered == 3
        assert {
            (
                topology.edge_refs[entry.edge].link,
                topology.edge_refs[entry.edge].direction,
            ): entry.delivery_reduction
            for entry in value.result.entries
            if entry.delivery_reduction
        } == {("A|C|0", "forward"): 3, ("C|D|0", "forward"): 3}


class TestDisabledLinks:
    @pytest.mark.parametrize("reuse", [False, True])
    def test_disabled_link_blocks_path(self, reuse):
        network = make_asymmetric_diamond(disable_link_a_b=True)
        prepared = _prepare(network)
        assert _row(prepared).result.delivered == 3
        assert _row(prepared if reuse else _prepare(network)).result.delivered == 3

    def test_disabled_link_in_only_path_yields_zero_flow(self):
        network = Network(nodes={name: Node(name) for name in "AB"})
        link = Link("A", "B", 10, 1, disabled=True)
        network.add_link(link)
        assert _row(_prepare(network), target="^B$").result.delivered == 0
        network.enable_link(link.id)
        assert _row(_prepare(network), target="^B$").result.delivered == 10

    def test_costs_respect_disabled_link(self):
        row = _row(_prepare(make_asymmetric_diamond(disable_link_a_b=True)), costs=True)
        assert row.result.delivered == 3
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(4, 3)]


class TestCombinedExclusions:
    def test_disabled_node_plus_explicit_node_exclusion(self):
        prepared = _prepare(make_asymmetric_diamond(disable_node_b=True))
        assert _row(prepared, nodes=("C",)).result.delivered == 0
        assert _row(prepared).result.delivered == 3

    def test_disabled_link_plus_explicit_link_exclusion(self):
        prepared = _prepare(make_asymmetric_diamond(disable_link_a_b=True))
        assert _row(prepared, links=("A|C|0",)).result.delivered == 0
        assert _row(prepared).result.delivered == 3

    def test_explicit_exclusion_without_disabled_topology(self):
        prepared = _prepare(make_asymmetric_diamond())
        assert _row(prepared, nodes=("B",)).result.delivered == 3
        assert _row(prepared).result.delivered == 8


class TestNominalTopology:
    def test_no_disabled_topology_full_flow(self):
        assert _row(_prepare(make_asymmetric_diamond())).result.delivered == 8


class TestPairwiseMode:
    def test_disabled_node_pairwise_mode(self):
        network = Network(
            nodes={
                name: Node(name, disabled=name == "S2")
                for name in ("S1", "S2", "M", "T1", "T2")
            }
        )
        for source, target in (("S1", "M"), ("S2", "M"), ("M", "T1"), ("M", "T2")):
            network.add_link(Link(source, target, 5, 1))
        value = capacity(
            _prepare(network),
            CapacityQuery(
                Selector("^S", group_by="name"),
                Selector("^T", group_by="name"),
                mode="pairwise",
                workers=2,
            ),
        )
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.result.delivered)
            for row in value.cases[0].states["converged"].rows
        ] == [
            (("S1",), ("T1",), 5),
            (("S1",), ("T2",), 5),
        ]


class TestPreparedReuse:
    def test_multiple_exclusion_scenarios(self):
        prepared = _prepare(make_asymmetric_diamond())
        assert [
            _row(prepared, nodes=nodes).result.delivered
            for nodes in (
                (),
                ("B",),
                ("C",),
                ("B", "C"),
                (),
            )
        ] == [8, 3, 5, 0, 8]


def test_sensitivity_combines_nominal_and_supplied_mask():
    prepared = _prepare(make_asymmetric_diamond(disable_node_b=True))
    topology = prepared.topology
    query = SensitivityQuery(
        Selector("^A$"),
        Selector("^D$"),
        _query().config,
        eligibility=topology.graph.eligibility(
            excluded_nodes=[topology.node_id_by_name["C"]]
        ),
        workers=2,
    )
    value = edge_sensitivity(prepared, query)
    assert value.result.baseline.delivered == 0
    assert all(entry.delivery_reduction == 0 for entry in value.result.entries)
    assert (
        edge_sensitivity(
            prepared,
            SensitivityQuery(
                query.source,
                query.target,
                query.config,
                workers=2,
            ),
        ).result.baseline.delivered
        == 3
    )
