"""Each rule of the q recipe, by a hand-derived scenario (precision p = 0.001).

A split of ``n`` members carrying ``x`` asks ``q <= p * x / (n - 1)``; an input
amount ``x`` asks ``q <= 2 * p * x``. q is the coarsest power of two meeting
every bound, so each case names the bound that decides it.
"""

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pytest

import ngraph.analysis.preparation as preparation
from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    StepOutput,
    WorkflowStep,
    prepare,
)
from ngraph.analysis.preparation import StepNeeds


def splits(prepared):
    return {
        (c.kind, c.label, c.incoming_physical, c.members)
        for c in prepared.units_report.nominal_splits
    }


def test_a_split_inside_an_expansion_uses_its_share_of_the_parent():
    # Pairwise to t1 and t2: two leaves of 1/2, each across a two-way router
    # at s: p * 1/2 = 5e-4 -> 2^-11 (the whole volume would give 2^-10).
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, m1: {}, m2: {}, t1: {}, t2: {}, j: {}}
  links:
    - {source: s, target: m1, capacity: 100}
    - {source: s, target: m2, capacity: 100}
    - {source: m1, target: j, capacity: 100}
    - {source: m2, target: j, capacity: 100}
    - {source: j, target: t1, capacity: 100}
    - {source: j, target: t2, capacity: 100}
demands:
  d: [{source: "^s$", target: "^t[12]$", volume: 1, mode: pairwise}]
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    assert prepared.topology.q == 2**-11
    assert splits(prepared) == {
        ("expansion", "demands.d[0](d|0).pairs", Fraction(1), 2),
        ("router", "demand.d|0|0.router.s", Fraction(1, 2), 2),
        ("router", "demand.d|0|1.router.s", Fraction(1, 2), 2),
    }


def test_a_pinned_dag_entry_receives_its_weighted_share_of_the_head():
    # Two entries of weight 1 at s: the DAG entry carries 1/2 and splits it
    # at a: p * 1/2 -> 2^-11 (the head's whole amount would give 2^-10).
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, a: {}, b: {}, c: {}, d: {}, t: {}}
  links:
    - {source: s, target: a, capacity: 100}
    - {source: a, target: c, capacity: 100}
    - {source: a, target: d, capacity: 100}
    - {source: c, target: t, capacity: 100}
    - {source: d, target: t, capacity: 100}
    - {source: s, target: b, capacity: 100}
    - {source: b, target: t, capacity: 100}
supports:
  split_at_a:
    edges:
      - {link: "s|a|0", direction: forward}
      - {link: "a|c|0", direction: forward}
      - {link: "a|d|0", direction: forward}
      - {link: "c|t|0", direction: forward}
      - {link: "d|t|0", direction: forward}
routes:
  r1: {head: s, support: split_at_a, weight: 1}
  r2: {head: s, nodes: [s, b, t], weight: 1}
demands:
  d:
    - source: "^s$"
      target: "^t$"
      volume: 1
      model: {routing: {type: pinned, routes: [r1, r2], allocation: equal}}
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    assert prepared.topology.q == 2**-11
    assert splits(prepared) == {
        ("tunnel", "demand.d|0|0.entries.s", Fraction(1), 2),
        ("router", "demand.d|0|0.entry[0].router.a", Fraction(1, 2), 2),
    }


def test_a_weighted_dag_passes_each_router_its_weighted_share():
    # WCMP by capacity at s: a receives 300/400 and splits it two ways:
    # p * 3/4 = 7.5e-4 -> 2^-11; the incoming amounts name each share.
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, a: {}, b: {}, c: {}, d: {}, e: {}, t: {}}
  links:
    - {source: s, target: a, capacity: 300}
    - {source: s, target: b, capacity: 100}
    - {source: a, target: c, capacity: 100}
    - {source: a, target: d, capacity: 100}
    - {source: b, target: e, capacity: 100}
    - {source: c, target: t, capacity: 100}
    - {source: d, target: t, capacity: 100}
    - {source: e, target: t, capacity: 100}
demands:
  d: [{source: "^s$", target: "^t$", volume: 1, preset: SHORTEST_PATHS_WCMP}]
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    assert prepared.topology.q == 2**-11
    assert splits(prepared) == {
        ("router", "demand.d|0|0.router.s", Fraction(1), 2),
        ("router", "demand.d|0|0.router.a", Fraction(3, 4), 2),
    }


def test_a_placed_demand_shares_its_volume_only_among_sources_that_reach():
    # s2 reaches no destination, so s1 carries the whole volume across its
    # two-way router: p * 1 -> 2^-10 (counting s2 would halve it: 2^-11).
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s1: {}, s2: {}, a: {}, b: {}, t: {}, x: {}}
  links:
    - {source: s1, target: a, capacity: 100}
    - {source: s1, target: b, capacity: 100}
    - {source: a, target: t, capacity: 100}
    - {source: b, target: t, capacity: 100}
    - {source: s2, target: x, capacity: 100}
demands:
  d: [{source: "^s[12]$", target: "^t$", volume: 1}]
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    assert prepared.topology.q == 2**-10
    assert splits(prepared) == {("router", "demand.d|0|0.router.s1", Fraction(1), 2)}


def test_a_capacity_question_shares_only_among_sources_that_reach():
    # Equal source allocation over s1 (reaches t, capacity 1) and s2 (does
    # not): one live source, no split; the inputs decide: 2p * 1 -> 2^-9.
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s1: {}, s2: {}, t: {}, x: {}}
  links:
    - {source: s1, target: t, capacity: 1}
    - {source: s2, target: x, capacity: 1}
workflow:
  - type: MaxFlow
    name: cap
    source: "^s[12]$"
    target: "^t$"
    workers: 1
    model: {routing: {type: centralized_te, source_allocation: equal}}
"""
        )
    )
    assert prepared.topology.q == 2**-9
    assert splits(prepared) == set()


def test_the_range_screen_counts_the_private_pool_ingress():
    # Link capacity C = 1.5 * 2^40, both directions, and the pool ingress C:
    # 4.5 * 2^40 / q < 2^62 holds from 2^-19 (the physical sum alone allows
    # 2^-20). The 16-tunnel split cannot meet p, so the finest valid q wins.
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 1649267441664}]
demands:
  d: [{source: "^s$", target: "^t$", volume: 0.0143, preset: TE_ECMP_16_LSP}]
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    report = prepared.units_report
    assert prepared.topology.q == 2**-19 and not report.target_met
    assert report.augmented_capacity_sum_units == 9 * 2**40 * 2**18


def test_a_minimum_unreserved_bandwidth_is_an_input_amount():
    # min_unreserved_bandwidth 0.001: 2p * 0.001 = 2e-6 -> 2^-19.
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 10}]
demands:
  d:
    - source: "^s$"
      target: "^t$"
      volume: 1
      model:
        routing:
          type: distributed_te
          tunnel_count: {per_head: 1}
          min_unreserved_bandwidth: 0.001
workflow:
  - {type: TrafficMatrixPlacement, name: tmp, demand_set: d, workers: 1}
"""
        )
    )
    report = prepared.units_report
    assert prepared.topology.q == 2**-19 and report.input_count == 3
    assert [c.label for c in report.binding_constraints] == [
        "demand.d|0.min_unreserved"
    ]


def one_link():
    network = Network(nodes={"s": Node("s"), "t": Node("t")})
    network.add_link(Link("s", "t", 1))
    return network


T1 = "{routing: {type: distributed_te, tunnel_count: {per_head: 1}EXTRA}}"


@pytest.mark.parametrize(
    "fields,label,q",
    [
        # 2p * 0.2505 = 5.01e-4 -> 2^-11; the capacity alone gives 2^-9.
        ("offer: 0.2505", "workflow.ask.offer", 2**-11),
        (
            f"design_demand: 0.2505, model: {T1.replace('EXTRA', '')}",
            "workflow.ask.design_demand",
            2**-11,
        ),
        # 2p * 0.001 = 2e-6 -> 2^-19.
        (
            "design_demand: 1, "
            f"model: {T1.replace('EXTRA', ', min_unreserved_bandwidth: 0.001')}",
            "workflow.ask.min_unreserved",
            2**-19,
        ),
    ],
    ids=["offer", "design", "minimum"],
)
def test_preparation_collects_every_capacity_step_amount(fields, label, q):
    prepared = prepare(
        Scenario.from_yaml(
            f"""
network:
  nodes: {{s: {{}}, t: {{}}}}
  links: [{{source: s, target: t, capacity: 1}}]
workflow:
  - {{type: MaxFlow, name: ask, source: "^s$", target: "^t$", workers: 1, {fields}}}
"""
        )
    )
    report = prepared.units_report
    assert prepared.topology.q == q and report.target_met
    assert [c.label for c in report.binding_constraints] == [label]


@dataclass
class Custom(WorkflowStep):
    """A custom capacity step that declares one amount of its own."""

    def needs(self):
        return StepNeeds(
            numerical=True,
            capacity=lambda prepared: CapacityQuery(
                Selector("^s$"), Selector("^t$"), workers=1
            ),
            inputs={"amount": ("offer", 0.2505)},
        )

    def run(self, context):
        return StepOutput({}, None)


def test_a_custom_step_amount_determines_q_and_the_report():
    prepared = prepare(Scenario(one_link(), (Custom(name="custom"),)))
    report = prepared.units_report
    assert prepared.topology.q == 2**-11 and report.input_count == 2
    assert [c.label for c in report.binding_constraints] == ["workflow.custom.amount"]


def test_candidates_above_the_declared_split_bounds_are_never_compiled(monkeypatch):
    compiled = []
    original = preparation.compile_topology

    def counted(network, q, **kwargs):
        compiled.append(q)
        return original(network, q, **kwargs)

    monkeypatch.setattr(preparation, "compile_topology", counted)
    text = Path("scenarios/square_mesh.yaml").read_text()
    prepared = prepare(Scenario.from_yaml(text))
    # The splits declared on square_mesh already rule out 2^-9 and 2^-10.
    assert compiled == [prepared.topology.q] == [2**-11]
