"""Physical expansion and exact candidate selection, independent expected bounds."""

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
    # Zero volume remains an in-scope leaf: floor3 gives q<=.001/3.
    assert result.topology.q == 2**-12
    assert result.units_report.input_bound.label == "link.s|t|0.capacity"
    assert result.demand_sets["load"].demands[0].nominal_units == 0


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
    assert resolved["load"].demands[0].config.routing.edge_weights is not None


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
