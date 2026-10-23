"""Capacity defaults ask maximum flow while finite demands retain static ECMP."""

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    place,
    prepare,
    run,
)
from ngraph.workflow.max_flow_step import MaxFlow
from tests.question import asked

BASE = """
units: {resolution: 1}
network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: B, capacity: 10, cost: 1}
    - {source: A, target: C, capacity: 10, cost: 1}
    - {source: C, target: B, capacity: 10, cost: 1}
"""


def network():
    result = Network(nodes={name: Node(name) for name in ("A", "B", "C")})
    for source, target in (("A", "B"), ("A", "C"), ("C", "B")):
        result.add_link(Link(source, target, 10, 1))
    return result


@pytest.mark.parametrize("boundary", ["python", "yaml"])
def test_bare_maxflow_matches_explicit_unrestricted_capacity(boundary):
    if boundary == "yaml":
        scenario = Scenario.from_yaml(
            BASE
            + """
workflow:
  - {type: MaxFlow, name: bare, source: ^A$, target: ^B$, workers: 1, outputs: {edge_flows: true}}
  - {type: MaxFlow, name: explicit, source: ^A$, target: ^B$, workers: 1, preset: TE_MAXFLOW_UNLIM, outputs: {edge_flows: true}}
  - type: MaxFlow
    name: model
    source: ^A$
    target: ^B$
    workers: 1
    outputs: {edge_flows: true}
    model: {routing: {type: centralized_te, source_allocation: optimized}, admission: lossless}
"""
        )
    else:
        scenario = Scenario(
            network(),
            tuple(
                MaxFlow(
                    name=name,
                    source=Selector("^A$"),
                    target=Selector("^B$"),
                    workers=1,
                    outputs=ngc.OutputOptions(edge_flows=True),
                    **declaration,
                )
                for name, declaration in (
                    ("bare", {}),
                    ("explicit", {"preset": FlowPolicyPreset.TE_MAXFLOW_UNLIM}),
                    (
                        "model",
                        {
                            "model": ngc.FlowPolicyConfig(
                                routing=ngc.CentralizedTE(
                                    source_allocation=ngc.SourceAllocation.OPTIMIZED
                                )
                            )
                        },
                    ),
                )
            ),
            units=UnitsSettings(1),
        )
    prepared = prepare(scenario)
    answers = run(prepared).steps
    for answer in answers:
        model = asked(answer)["model"]
        assert (model["routing"], model["source_allocation"], model["admission"]) == (
            "centralized_te",
            "optimized",
            "lossless",
        )
        (row,) = answer.result.cases[0].states["converged"].rows
        # Source cut 10+10 bounds the optimum by20; these feasible flows attain it.
        assert row.result.delivered == 20
        flows = {
            (ref.link, ref.direction): value
            for ref, value in zip(
                prepared.topology.edge_refs, row.result.edge_flows, strict=True
            )
        }
        assert flows == {
            ("A|B|0", "forward"): 10,
            ("A|B|0", "reverse"): 0,
            ("A|C|0", "forward"): 10,
            ("A|C|0", "reverse"): 0,
            ("C|B|0", "forward"): 10,
            ("C|B|0", "reverse"): 0,
        }
    assert asked(answers[0])["model"] == asked(answers[1])["model"]


@pytest.mark.parametrize("boundary", ["python", "yaml"])
def test_demand_without_preset_keeps_shortest_paths_ecmp(boundary):
    if boundary == "yaml":
        scenario = Scenario.from_yaml(
            BASE + "demands:\n  d:\n    - {source: ^A$, target: ^B$, volume: 20}\n"
        )
    else:
        scenario = Scenario(
            network(),
            demand_sets={
                "d": DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^B$"), 20),))
            },
            units=UnitsSettings(1),
        )
    assert (
        scenario.demand_sets["d"].demands[0].policy
        == FlowPolicyPreset.SHORTEST_PATHS_ECMP
    )
    prepared = prepare(scenario, demand_sets=("d",))
    result = place(prepared, PlacementQuery(prepared.demand_sets["d"], workers=1))
    # Direct cost1 is the only shortest path; the cost2 detour is not ECMP support.
    assert result.cases[0].states["converged"].totals.delivered_units == 10
