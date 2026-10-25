"""Complete A inputs execute on one graph; deferred and removed keys refuse."""

import json
from fractions import Fraction
from io import StringIO

import netgraph_core as ngc
import pytest
import yaml

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.units import UnitsSettings
from ngraph.export import write_json
from ngraph.model.demand import FlowPolicyPreset
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.max_flow_step import MaxFlow
from tests.question import asked

EXPLICIT = """
seed: 42
units: {resolution: 1, precision: 0.001}
network:
  nodes: {A: {}, B: {}, T: {}}
  links:
    - {source: A, target: B, capacity: 10, cost: 1}
    - {source: A, target: B, capacity: 10, cost: 2}
    - {source: B, target: T, capacity: 10, cost: 1}
supports:
  route_dag:
    edges: [{link: 'A|B|0', direction: forward}, {link: 'B|T|0', direction: forward}]
weights:
  route_weights:
    entries:
      - {edge: {link: 'A|B|0', direction: forward}, value: 2}
      - {edge: {link: 'B|T|0', direction: forward}, value: 1}
routes:
  cheap: {head: A, nodes: [A, B, T]}
  dag_entry: {head: A, support: route_dag, weight: 1}
demands:
  explicit:
    - id: pinned
      source: '^A$'
      target: '^T$'
      volume: 8
      model: {routing: {type: pinned, routes: [cheap]}, admission: lossless}
    - id: weighted
      source: '^A$'
      target: '^T$'
      volume: 2
      model:
        routing: {type: shortest_paths, allocation: weighted, weight_basis: explicit, edge_weights: route_weights}
        admission: lossless
workflow:
  - {type: TrafficMatrixPlacement, name: explicit, demand_set: explicit, workers: 1, outputs: {edge_flows: true}}
  - type: MaxFlow
    name: pinned_capacity
    source: '^A$'
    target: '^T$'
    workers: 1
    model: {routing: {type: pinned, routes: [dag_entry], allocation: weighted, weight_basis: explicit, edge_weights: route_weights}, admission: lossless}
"""


def test_complete_named_route_weight_and_support_workflow_native_and_wire():
    prepared = prepare(Scenario.from_yaml(EXPLICIT))
    assert prepared.units_report.scope.workflow_steps == (
        "explicit",
        "pinned_capacity",
    )
    assert prepared.units_report.scope.workflow_demand_sets == ("explicit",)
    assert len(prepared.demand_sets["explicit"].demands) == 2
    result = run(prepared)
    placement, bound = (step.result for step in result.steps)
    rows = placement.cases[0].states["converged"].rows
    assert [row.result.delivered for row in rows] == [8, 2]
    for row, amount in zip(rows, (8, 2), strict=True):
        flows = dict(
            zip(prepared.topology.edge_refs, row.result.edge_flows, strict=True)
        )
        assert {
            (ref.link, ref.direction): int(units)
            for ref, units in flows.items()
            if units
        } == {("A|B|0", "forward"): amount, ("B|T|0", "forward"): amount}
    assert bound.cases[0].states["converged"].rows[0].result.delivered == 10
    assert asked(result.steps[1])["model"]["route_names"] == ["dag_entry"]
    assert not asked(result.steps[1])["model"]["supplied_program"]
    output = StringIO()
    write_json(result, output)
    wire = json.loads(output.getvalue())
    assert wire["steps"][0]["question"]["demand_set"] == "explicit"
    assert wire["steps"][1]["question"]["model"]["route_names"] == ["dag_entry"]
    assert set(wire["steps"][0]["result"]["cases"][0]["states"]) == {"converged"}


@pytest.mark.parametrize(
    "key",
    [
        "states",
        "counts",
        "up_to",
        "parallelism",
        "shortest_path",
        "require_capacity",
        "flow_placement",
        "edge_priority",
        "include_flow_details",
        "include_min_cut",
        "store_failure_patterns",
        "alpha_from_field",
    ],
)
def test_deferred_and_removed_step_keys_refuse_by_name_with_control(key):
    data = yaml.safe_load(EXPLICIT)
    data["workflow"][0][key] = True
    with pytest.raises(ValueError, match=key):
        Scenario.from_yaml(yaml.safe_dump(data))
    assert len(Scenario.from_yaml(EXPLICIT).workflow) == 2


def test_yaml_policy_double_prefix_seed_and_step_recipe_are_independently_pinned():
    scenario = Scenario.from_yaml("""
seed: 42
failures: {random_link: {modes: [{weight: 1, rules: []}]}}
workflow: [{type: BuildGraph, name: graph}]
""")
    assert scenario.failure_policies["random_link"].seed == 2099469712
    # SHA256('42:workflow_step:graph'), first four bytes &0x7fffffff.
    import hashlib

    expected = (
        int.from_bytes(hashlib.sha256(b"42:workflow_step:graph").digest()[:4], "big")
        & 0x7FFFFFFF
    )
    step = run(prepare(scenario)).steps[0]
    assert step.step_seed == expected and step.seed_source == "scenario-derived"


def test_expansion_ids_keep_source_ordinal_and_leaf_index_without_double_append():
    scenario = Scenario.from_yaml("""
units: {resolution: 1}
network: {nodes: {s1: {}, s2: {}, t: {}}}
demands:
  x:
    - {source: 's${i}', target: t, volume: 2, expand: {vars: {i: [1, 2]}}}
    - {source: s1, target: t, volume: 3}
""")
    resolved = prepare(scenario, demand_sets=("x",)).demand_sets["x"]
    assert [
        (p.base_id, p.declaration_ordinal, p.expand_leaf_index)
        for p in resolved.expansion_template
    ] == [("x|0|0", 0, 0), ("x|0|1", 0, 1), ("x|1", 1, None)]
    assert [d.id for d in resolved.demands] == ["x|0|0|0", "x|0|1|0", "x|1|0"]


def test_uncapped_observed_router_bound_refines_candidate_after_input_screen():
    network = Network()
    # At q=1/2 every capacity input meets precision=1/4. Three equal members
    # deliver3, but q<=precision*3/(3-1)=3/8 fails. q=1/4 meets it.
    for name in ("s", "a", "b", "c", "t"):
        network.add_node(Node(name))
    for middle in ("a", "b", "c"):
        network.add_link(Link("s", middle, 1, 1))
        network.add_link(Link(middle, "t", 1, 1))
    step = MaxFlow(
        name="capacity",
        source=Selector("^s$"),
        target=Selector("^t$"),
        preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        workers=1,
    )
    prepared = prepare(Scenario(network, [step], units=UnitsSettings(precision=0.25)))
    assert prepared.topology.q == 0.25
    (split,) = [c for c in prepared.units_report.nominal_splits if c.kind == "router"]
    assert split.basis == "observed" and split.incoming_physical == Fraction(3)
    assert split.members == 3 and split.q_upper_bound == Fraction(3, 8) and split.met
    coarse = prepare(Scenario(network, [step], units=UnitsSettings(0.5, 0.25)))
    assert coarse.topology.q == 0.5 and not coarse.units_report.target_met
    assert any(
        c.basis == "observed" and not c.met for c in coarse.units_report.nominal_splits
    )
    analysis = capacity(
        coarse,
        CapacityQuery(
            Selector("^s$"),
            Selector("^t$"),
            ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
            workers=1,
        ),
    )
    assert analysis.cases[0].states["converged"].rows[0].result.delivered == 6
    assert analysis.units_report.misses[0].constraints[0].basis == "observed"


def test_default_equal_source_bound_keeps_reachable_zero_capacity_heads():
    network = Network()
    for name in ("h1", "h2", "h3", "t"):
        network.add_node(Node(name))
    for head, amount in (("h1", 1), ("h2", 0), ("h3", 0)):
        network.add_link(Link(head, "t", amount, 1))
    config = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
    )
    step = MaxFlow(
        name="heads",
        source=Selector("^h"),
        target=Selector("^t$"),
        model=config,
        offer=1,
        workers=1,
    )
    prepared = prepare(Scenario(network, [step], units=UnitsSettings(precision=0.25)))
    assert prepared.topology.q == 0.125
    (split,) = [c for c in prepared.units_report.nominal_splits if c.kind == "source"]
    assert (
        split.members == 3
        and split.incoming_physical == 1
        and split.q_upper_bound == Fraction(1, 8)
    )
    assert split.basis == "declared" and split.met
    value = run(prepared).steps[0].result
    assert value.cases[0].states["converged"].rows[0].result.delivered == 3


def test_finite_tunnel_design_split_is_bounded_separately_from_large_offer():
    scenario = Scenario.from_yaml("""
units: {precision: 0.25}
network: {nodes: {s: {}, t: {}}, links: [{source: s, target: t, capacity: 1000, cost: 1}]}
workflow:
 - type: MaxFlow
   name: tunnels
   source: s
   target: t
   offer: 1000
   design_demand: 1
   workers: 1
   model: {routing: {type: distributed_te, tunnel_count: {per_head: 4}}, admission: lossy}
""")
    prepared = prepare(scenario)
    assert prepared.topology.q == 0.0625
    (split,) = [
        c for c in prepared.units_report.nominal_splits if ".design." in c.label
    ]
    assert (
        split.basis == "declared"
        and split.incoming_physical == 1
        and split.members == 4
    )
    assert split.q_upper_bound == Fraction(1, 12)
