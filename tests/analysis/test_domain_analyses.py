"""Public native analyses preserve grouped endpoints, ownership and exact totals."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


@pytest.fixture
def source_destination_network():
    network = Network(
        nodes={
            name: Node(name)
            for name in ("datacenter1", "datacenter2", "edge1", "edge2", "router")
        }
    )
    for source, target, units in (
        ("datacenter1", "router", 100),
        ("datacenter2", "router", 80),
        ("router", "edge1", 120),
        ("router", "edge2", 60),
    ):
        network.add_link(Link(source, target, units, 1))
    return prepare(Scenario(network, units=UnitsSettings(1)))


class TestCapacityAnalysis:
    def test_basic(self, source_destination_network):
        value = capacity(
            source_destination_network,
            CapacityQuery(Selector("^datacenter"), Selector("^edge"), workers=1),
        )
        (row,) = value.cases[0].states["converged"].rows
        assert row.endpoints.sources == ("datacenter1", "datacenter2")
        assert row.endpoints.destinations == ("edge1", "edge2")
        assert row.result.delivered == 180

    def test_requested_costs_and_cut(self, source_destination_network):
        topology = source_destination_network.topology
        value = capacity(
            source_destination_network,
            CapacityQuery(
                Selector("^datacenter"),
                Selector("^edge"),
                workers=1,
                outputs=ngc.OutputOptions(min_cut=True),
                export_cost_distribution=True,
            ),
        )
        (row,) = value.cases[0].states["converged"].rows
        assert (
            row.result.delivered == 180
            and row.cost_distribution.kind == "marginal_curve"
        )
        assert [
            (bin.marginal_cost, bin.units) for bin in row.cost_distribution.bins
        ] == [(2, 180)]
        assert {
            (topology.edge_refs[edge].link, topology.edge_refs[edge].direction)
            for edge in row.result.min_cut
        } == {("datacenter1|router|0", "forward"), ("datacenter2|router|0", "forward")}

    def test_pairwise_model(self, source_destination_network):
        query = CapacityQuery(
            Selector("^datacenter", group_by="name"),
            Selector("^edge", group_by="name"),
            ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
            mode="pairwise",
            workers=2,
        )
        value = capacity(source_destination_network, query)
        assert [
            (row.endpoints.sources, row.endpoints.destinations, row.result.delivered)
            for row in value.cases[0].states["converged"].rows
        ] == [
            (("datacenter1",), ("edge1",), 100),
            (("datacenter1",), ("edge2",), 60),
            (("datacenter2",), ("edge1",), 80),
            (("datacenter2",), ("edge2",), 60),
        ]

    def test_unknown_parameter(self, source_destination_network):
        with pytest.raises(TypeError, match="unexpected keyword argument"):
            CapacityQuery(
                Selector("^datacenter"), Selector("^edge"), unknown_param=True
            )
        assert (
            capacity(
                source_destination_network,
                CapacityQuery(Selector("^datacenter"), Selector("^edge"), workers=1),
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 180
        )

    def test_empty_selection(self, source_destination_network):
        with pytest.raises(ValueError, match="capacity.source: empty selection"):
            capacity(
                source_destination_network,
                CapacityQuery(Selector("^absent$"), Selector("^edge"), workers=1),
            )
        assert (
            len(
                capacity(
                    source_destination_network,
                    CapacityQuery(
                        Selector("^datacenter"), Selector("^edge"), workers=1
                    ),
                ).cases
            )
            == 1
        )


def _placement_prepared(
    network,
    *,
    source="^A$",
    target="^D$",
    mode="pairwise",
    volume=50,
    identity="stable",
):
    demands = DemandSet(
        "load",
        (
            DemandSpec(
                Selector(source), Selector(target), volume, id=identity, mode=mode
            ),
        ),
    )
    return prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )


class TestDemandPlacementAnalysis:
    def test_basic(self, diamond_network):
        prepared = _placement_prepared(diamond_network)
        value = place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
        state = value.cases[0].states["converged"]
        assert len(state.rows) == 1
        row = state.rows[0]
        assert row.endpoints.sources == ("A",) and row.endpoints.destinations == ("D",)
        assert row.result.requested == row.result.delivered == 50
        assert row.result.source_drops == row.result.unadmitted == 0
        assert (
            state.totals.reference_request_units == state.totals.delivered_units == 50
        )
        assert state.totals.delivery_ratio == Fraction(1)

    def test_zero_total_demand(self, diamond_network):
        prepared = _placement_prepared(diamond_network, target="^B$", volume=0)
        state = (
            place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
            .cases[0]
            .states["converged"]
        )
        assert len(state.rows) == 1
        assert state.rows[0].result.requested == state.rows[0].result.delivered == 0
        assert state.totals.reference_request_units == state.totals.delivered_units == 0
        assert state.totals.delivery_ratio == Fraction(1) and state.totals.feasible


class TestPreparedPlacementCalls:
    def test_pairwise_mode(self, diamond_network):
        prepared = _placement_prepared(diamond_network)
        for _ in range(2):
            state = (
                place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
                .cases[0]
                .states["converged"]
            )
            assert state.rows[0].id == "stable|0"
            assert state.totals.delivered_units == 50 and state.totals.feasible

    def test_combine_mode(self, diamond_network):
        prepared = _placement_prepared(
            diamond_network, source="^[AB]$", target="^[CD]$", mode="combine"
        )
        state = (
            place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
            .cases[0]
            .states["converged"]
        )
        assert state.totals.delivered_units == 50 and state.totals.feasible
        assert state.rows[0].endpoints.sources == ("A", "B")
        assert state.rows[0].endpoints.destinations == ("C", "D")

    def test_combine_repeated_failure_cases(self, diamond_network):
        prepared = _placement_prepared(
            diamond_network, source="^[AB]$", target="^[CD]$", mode="combine"
        )
        for name in ("B", "C"):
            policy = FailurePolicy(
                modes=[FailureMode(1, [FailureRule("node", path=f"^{name}$")])]
            )
            value = place(
                prepared,
                PlacementQuery(
                    prepared.demand_sets["load"],
                    failures=FailureRequest(policy, 1, 42),
                    workers=2,
                ),
            )
            assert len(value.cases) == 2
            assert value.cases[1].case.pattern.excluded_nodes == (name,)
            assert (
                value.cases[0].states["converged"].totals.delivered_units
                == value.cases[1].states["converged"].totals.delivered_units
                == 50
            )

    def test_absent_id_is_stable(self, diamond_network):
        first = _placement_prepared(
            diamond_network,
            source="^[AB]$",
            target="^[CD]$",
            mode="combine",
            identity=None,
        )
        second = _placement_prepared(
            diamond_network,
            source="^[AB]$",
            target="^[CD]$",
            mode="combine",
            identity=None,
        )
        assert (
            first.demand_sets["load"].demands[0].id
            == second.demand_sets["load"].demands[0].id
            == "load|0|0"
        )
        assert (
            place(first, PlacementQuery(first.demand_sets["load"], workers=1))
            .cases[0]
            .states["converged"]
            .totals.delivered_units
            == 50
        )


@pytest.fixture
def chain_prepared():
    network = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    network.add_link(Link("A", "B", 10, 1))
    network.add_link(Link("B", "C", 10, 2))
    return prepare(Scenario(network, units=UnitsSettings(1)))


def _sensitivity_query():
    return SensitivityQuery(
        Selector("^A$"),
        Selector("^C$"),
        ngc.FlowPolicyConfig(
            routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
        ),
        workers=1,
    )


class TestSensitivityAnalysis:
    def test_basic(self, chain_prepared):
        value = edge_sensitivity(chain_prepared, _sensitivity_query())
        assert value.result.baseline.delivered == 10
        assert {
            (
                chain_prepared.topology.edge_refs[row.edge].link,
                chain_prepared.topology.edge_refs[row.edge].direction,
            ): row.delivery_reduction
            for row in value.result.entries
            if row.delivery_reduction
        } == {("A|B|0", "forward"): 10, ("B|C|0", "forward"): 10}

    def test_empty_selection(self, chain_prepared):
        with pytest.raises(ValueError, match="sensitivity.source: empty selection"):
            edge_sensitivity(
                chain_prepared,
                SensitivityQuery(
                    Selector("^absent$"),
                    Selector("^C$"),
                    _sensitivity_query().config,
                    workers=1,
                ),
            )
        assert (
            edge_sensitivity(
                chain_prepared, _sensitivity_query()
            ).result.baseline.delivered
            == 10
        )

    def test_single_native_baseline(self, chain_prepared, monkeypatch):
        original = ngc.evaluate_edge_failures
        calls = []

        def evaluate(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(ngc, "evaluate_edge_failures", evaluate)
        monkeypatch.setattr(
            ngc,
            "evaluate_demand",
            lambda *args, **kwargs: pytest.fail("duplicate baseline solve"),
        )
        value = edge_sensitivity(chain_prepared, _sensitivity_query())
        assert calls == [1] and value.result.baseline.delivered == 10
        assert sum(row.delivery_reduction != 0 for row in value.result.entries) == 2
