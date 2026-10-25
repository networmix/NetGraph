"""Physical expansion and exact candidate selection, independent expected bounds."""

from fractions import Fraction

import pytest

from ngraph.analysis.demands import resolve_demands, scaled_expansion
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare


def line():
    network = Network()
    for name in ("s", "t"):
        network.add_node(Node(name))
    network.add_link(Link("s", "t", 1, 3))
    return network


def prepared(network, sets, units, **declared):
    """Prepare the named demand sets as a library caller asks for them."""
    scenario = Scenario(
        network,
        demand_sets={value.name: value for value in sets},
        units=units,
        **declared,
    )
    return prepare(scenario, demand_sets=tuple(value.name for value in sets))


def spec(volume=0.25, *, name="load", policy=FlowPolicyPreset.SHORTEST_PATHS_ECMP):
    return DemandSet(
        name, (DemandSpec(Selector("^s$"), Selector("^t$"), volume, policy),)
    )


def test_auto_candidate_is_coarsest_legal_power_with_exact_input_target():
    # For capacity1 and volume1/4, precision1/1000 demands q<=1/2000.
    # The largest legal power is2^-11; the next coarser2^-10 fails.
    result = prepared(line(), [spec()], UnitsSettings())
    topology, sets = result.topology, result.demand_sets
    assert topology.q == 2**-11
    report = result.units_report
    assert report.target_met
    assert report.input_count == 2
    assert report.nominal_split_count == 0
    assert report.augmented_capacity_sum_units == 4096
    assert report.augmented_cost_sum == 6
    assert report.scope.library_demand_sets == ("load",)
    assert sets["load"].demands[0].nominal_units == 512
    bound = [
        constraint
        for constraint in report.binding_constraints
        if constraint.kind == "input"
    ]
    assert len(bound) == 1
    assert bound[0].label == "demand.load|0.volume"
    assert bound[0].q_upper_bound == 2 * Fraction(float(0.001)) * Fraction(1, 4)
    assert Fraction(topology.q) <= bound[0].q_upper_bound < Fraction(topology.q * 2)


def test_alpha_scales_physical_total_and_preserves_zero_policy_identity():
    result = prepared(line(), [spec()], UnitsSettings(1))
    demands = result.demand_sets["load"]
    assert len(demands.demands) == 1
    assert demands.demands[0].nominal_units == 0
    assert demands.expansion_template[0].physical_volume == 0.25
    assert not result.units_report.target_met
    amounts, accounting = scaled_expansion(demands, 4, 1)
    assert dict(amounts) == {"load|0|0": 1}
    assert accounting[0].declared_units == accounting[0].resolved_units == 1
    assert accounting[0].discarded_units == 0
    assert resolve_demands(result, spec()).demands[0].id == "load|0|0"


def test_nested_expansion_uses_one_parent_round_then_declared_rr():
    network = Network()
    for name, group in (
        ("s0", "a"),
        ("s1", "b"),
        ("s2", "b"),
        ("s3", "b"),
        ("t", "target"),
    ):
        network.add_node(Node(name, attrs={"group": group}))
    # Add links after all endpoints are present.
    for name in ("s0", "s1", "s2", "s3"):
        network.add_link(Link(name, "t", 100, 1))
    demands = DemandSet(
        "nested",
        (
            DemandSpec(
                Selector("^s", group_by="group"),
                Selector("^t$"),
                10,
                mode="pairwise",
                group_mode="group_pairwise",
            ),
        ),
    )
    result = prepared(network, [demands], UnitsSettings(1))
    resolved = result.demand_sets
    assert [d.nominal_units for d in resolved["nested"].demands] == [5, 2, 2, 1]
    assert [d.id for d in resolved["nested"].demands] == [
        f"nested|0|{i}" for i in range(4)
    ]
    assert resolved["nested"].accounting[0].declared_units == 10
    assert result.units_report.nominal_split_count >= 2


def test_duplicate_explicit_and_generated_ids_across_sets_refuse_with_control():
    network = line()
    first = spec(name="a")
    second = DemandSet(
        "b", (DemandSpec(Selector("^s$"), Selector("^t$"), 1, id="a|0"),)
    )
    with pytest.raises(ValueError, match="a\\|0.*duplicate across sets.*a.*b"):
        prepared(network, [first, second], UnitsSettings(1))
    resolved = prepared(network, [first, spec(name="b")], UnitsSettings(1)).demand_sets
    assert set(resolved) == {"a", "b"}


def test_zero_parent_counts_but_does_not_constrain_auto_resolution():
    result = prepared(line(), [spec(0)], UnitsSettings())
    # Capacity1 is the only positive input: q<=.002, hence2^-9.
    assert result.topology.q == 2**-9
    assert result.units_report.input_count == 2
    assert result.units_report.zeroed_inputs == 0
    assert result.demand_sets["load"].demands[0].nominal_units == 0


def test_equal_zero_capacity_member_and_capacity_weighted_member_count_differ():
    network = Network()
    for name in ("s", "a", "b", "t"):
        network.add_node(Node(name))
    for source, target, capacity in (
        ("s", "a", 0),
        ("a", "t", 5),
        ("s", "b", 5),
        ("b", "t", 5),
    ):
        network.add_link(Link(source, target, capacity, 1))
    source = Selector("^s$")
    target = Selector("^t$")
    reports = []
    for preset in (
        FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        FlowPolicyPreset.SHORTEST_PATHS_WCMP,
    ):
        demands = DemandSet("load", (DemandSpec(source, target, 10, preset),))
        reports.append(prepared(network, [demands], UnitsSettings(1)).units_report)
    assert [
        (split.members, split.incoming_physical)
        for split in reports[0].nominal_splits
        if split.kind == "router"
    ] == [(2, Fraction(10))]
    assert not [split for split in reports[1].nominal_splits if split.kind == "router"]


@pytest.mark.parametrize("zero_link", [("s", "a"), ("a", "t")])
def test_explicit_positive_weight_on_zero_capacity_prunes_the_dead_branch(zero_link):
    import netgraph_core as ngc

    from ngraph.model.demand import (
        EdgeWeight,
        WeightSpec,
        _ParsedModel,
        _ShortestPathsInput,
    )
    from ngraph.model.network import DirectedLink

    network = Network()
    for name in ("s", "a", "b", "t"):
        network.add_node(Node(name))
    for source, target in (("s", "a"), ("a", "t"), ("s", "b"), ("b", "t")):
        network.add_link(
            Link(source, target, 0 if (source, target) == zero_link else 5, 1)
        )
    weights = WeightSpec(
        tuple(
            EdgeWeight(DirectedLink(link.id, "forward"), 1)
            for link in network.links.values()
        )
    )
    model = _ParsedModel(
        _ShortestPathsInput(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights="configured",
        )
    )
    demands = DemandSet(
        "load", (DemandSpec(Selector("^s$"), Selector("^t$"), 10, model),)
    )
    result = prepared(
        network, [demands], UnitsSettings(1), weights={"configured": weights}
    )
    resolved = result.demand_sets
    assert not [
        split for split in result.units_report.nominal_splits if split.kind == "router"
    ]
    assert resolved["load"].demands[0].config.routing.edge_weights is not None


def test_observation_miss_counts_its_active_capacity_inputs_too():
    from ngraph.analysis.placement import PlacementQuery, place

    network = line()
    network.replace_link("s|t|0", capacity=0.25)
    preparation = prepared(network, [spec()], UnitsSettings(1))
    result = place(
        preparation,
        PlacementQuery(preparation.demand_sets["load"], alpha=4, workers=1),
    )
    (miss,) = result.misses
    assert result.units_report.misses == (*preparation.units_report.misses, miss)
    assert miss.location.case_id == "baseline" and miss.location.probe_index is None
    assert miss.inexact_inputs == miss.zeroed_inputs == 1
    assert [sample.label for sample in miss.examples] == ["link.s|t|0.capacity"]
    assert miss.examples[0].error == Fraction(-1, 4)
    assert {
        constraint.label
        for constraint in miss.constraints
        if constraint.kind == "input"
    } == {"demand.load|0.volume", "link.s|t|0.capacity"}


def test_totals_above_2_53_are_summed_in_exact_units_not_physical_floats():
    # At q = 1/2, volumes 2^52 and 0.5 are 2^53 and 1 units: the exact total is 2^53 + 1.
    # Summed as physical floats first, 2^52 + 0.5 is a binary64 tie that rounds to even
    # (2^52), which quantizes to 2^53.
    import io
    import json

    from ngraph.export import write_json
    from ngraph.scenario import run

    text = """
units: {resolution: 0.5}
network:
  nodes: {A: {}, B: {}, T: {}}
  links:
    - {source: A, target: T, capacity: 1, cost: 1}
    - {source: B, target: T, capacity: 1, cost: 1}
demands:
  d:
    - {source: ^A$, target: ^T$, volume: 4503599627370496}
    - {source: ^B$, target: ^T$, volume: 0.5}
workflow:
  - {type: TrafficMatrixPlacement, name: p, demand_set: d, workers: 1}
"""
    prep = prepare(Scenario.from_yaml(text))
    accounting = prep.demand_sets["d"].accounting
    assert [a.declared_units for a in accounting] == [2**53, 1]
    result = run(prep)
    totals = result.steps[0].result.cases[0].states["converged"].totals
    assert totals.reference_request_units == 2**53 + 1
    assert type(totals.reference_request_units) is int
    output = io.StringIO()
    write_json(result, output)
    exported = json.loads(output.getvalue())["steps"][0]["result"]
    (state,) = exported["cases"][0]["states"].values()
    assert state["totals"]["reference_request_units"] == 2**53 + 1
    leaves = exported["accounting"]
    assert [leaf["declared_units"] for leaf in leaves] == [2**53, 1]
