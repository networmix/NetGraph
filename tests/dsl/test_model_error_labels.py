"""YAML native refusals retain the declaration path and native exception text."""

import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    prepare,
)

BASE = """
network:
  nodes: {A1: {}, A2: {}, B: {}}
  links:
    - {source: A1, target: B, capacity: 10, cost: 1}
    - {source: A2, target: B, capacity: 10, cost: 1}
"""


@pytest.mark.parametrize("owner", ["demand", "step"])
@pytest.mark.parametrize("kind", ["lossy", "t2"])
def test_illegal_native_combination_keeps_yaml_path(owner, kind):
    routing = (
        "{type: centralized_te, source_allocation: optimized"
        + (", tunnel_count: {per_head: 4}" if kind == "t2" else "")
        + "}"
    )
    model = (
        "{routing: " + routing + (", admission: lossy" if kind == "lossy" else "") + "}"
    )
    if owner == "demand":
        text = (
            BASE
            + "demands:\n  d:\n    - {source: ^A, target: ^B$, volume: 1, model: "
            + model
            + "}\nworkflow:\n  - {type: TrafficMatrixPlacement, name: t, demand_set: d}\n"
        )
        label = "demands.d[0]"
    else:
        text = (
            BASE
            + "workflow:\n  - {type: MaxFlow, name: m, source: ^A, target: ^B$, model: "
            + model
            + "}\n"
        )
        label = "workflow[0] (name 'm')"
    with pytest.raises(ValueError) as error:
        prepare(Scenario.from_yaml(text))
    assert str(error.value).startswith(label + ": ")
    assert (
        "requires admission=LOSSLESS"
        if kind == "lossy"
        else "requires source_allocation=EQUAL"
    ) in str(error.value)


def _direct_native_refusal():
    graph = ngc.Graph(3, [0, 1], [2, 2], [10, 10], [1, 1], 1)
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
        admission=ngc.Admission.LOSSY,
    )
    ledger = ngc.FlowLedger(graph)
    with pytest.raises(ValueError) as error:
        ngc.FlowPolicy(ledger, [0, 1], [2], config)
    assert (
        str(error.value)
        == "CentralizedTE without tunnel_count requires admission=LOSSLESS"
    )
    return str(error.value)


def test_python_native_config_refusal_keeps_its_reason_and_demand_label():
    native_text = _direct_native_refusal()
    n = Network(nodes={k: Node(k) for k in ("s", "t")})
    n.add_link(Link("s", "t", 10))
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
        admission=ngc.Admission.LOSSY,
    )
    ds = DemandSet("d", (DemandSpec(Selector("^s$"), Selector("^t$"), 1, config),))
    with pytest.raises(ValueError) as error:
        prepare(Scenario(n, demand_sets={"d": ds}), demand_sets=("d",))
    assert (
        native_text == "CentralizedTE without tunnel_count requires admission=LOSSLESS"
    )
    assert str(error.value) == f"demands.d[0](d|0): {native_text}"


def test_pinned_binding_refusal_keeps_demand_label_and_has_legal_control():
    text = """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 20}]
supports:
  support: {edges: [{link: 's|t|0', direction: forward}]}
routes:
  dag: {head: s, support: support}
demands:
  d:
    - source: ^s$
      target: ^t$
      volume: 1
      model: {routing: {type: pinned, routes: [dag], allocation: equal, weight_basis: capacity}}
workflow: [{type: TrafficMatrixPlacement, name: t, demand_set: d}]
"""
    with pytest.raises(ValueError) as error:
        prepare(Scenario.from_yaml(text))
    assert (
        str(error.value) == "demands.d[0]: pinned: weights require weighted allocation"
    )
    p = prepare(
        Scenario.from_yaml(text.replace("allocation: equal", "allocation: weighted"))
    )
    assert p.demand_sets["d"].demands[0].nominal_units > 0
