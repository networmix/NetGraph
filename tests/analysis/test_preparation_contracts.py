"""Preparation ownership, input collection, range and diagonal model validation."""

from dataclasses import dataclass

import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    StepOutput,
    UnitsSettings,
    WorkflowStep,
    capacity,
    prepare,
    run,
)
from ngraph.analysis.preparation import StepNeeds
from ngraph.results import SelfPair
from ngraph.workflow import MaxFlow


def test_the_range_screen_counts_the_private_pool_ingress():
    # Link capacity C = 1.5 * 2^40, both directions, and the pool ingress C:
    # 4.5 * 2^40 / q < 2^62 holds from 2^-19 (the physical sum alone allows
    # 2^-20). The input 0.0005 asks q<=1e-6 (2^-20); the pool forces q=2^-19.
    prepared = prepare(
        Scenario.from_yaml(
            """
network:
  nodes: {s: {}, t: {}}
  links: [{source: s, target: t, capacity: 1649267441664}]
demands:
  d: [{source: "^s$", target: "^t$", volume: 0.0005, preset: TE_ECMP_16_LSP}]
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
    assert prepared.topology.q == 2**-19
    assert report.input_bound.label == "demand.d|0.min_unreserved"


def one_link():
    network = Network(nodes={"s": Node("s"), "t": Node("t")})
    network.add_link(Link("s", "t", 1))
    return network


T1 = "{routing: {type: distributed_te, tunnel_count: {per_head: 1}EXTRA}}"


@pytest.mark.parametrize(
    "fields,label,q",
    [
        # 2p * 0.0626 = 0.0001252 -> 2^-13; the graph count alone gives 2^-12.
        ("offer: 0.0626", "workflow.ask.offer", 2**-13),
        (
            f"design_demand: 0.0626, model: {T1.replace('EXTRA', '')}",
            "workflow.ask.design_demand",
            2**-13,
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
    assert report.input_bound.label == label


@dataclass
class Custom(WorkflowStep):
    """A custom capacity step that declares one amount of its own."""

    def needs(self):
        return StepNeeds(
            numerical=True,
            capacity=lambda prepared: CapacityQuery(
                Selector("^s$"), Selector("^t$"), workers=1
            ),
            inputs={"amount": ("offer", 0.0626)},
        )

    def run(self, context):
        return StepOutput({}, None)


def test_a_custom_step_amount_determines_q_and_the_report():
    prepared = prepare(Scenario(one_link(), (Custom(name="custom"),)))
    report = prepared.units_report
    assert prepared.topology.q == 2**-13
    assert report.input_bound.label == "workflow.custom.amount"


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("valid", [False, True])
def test_diagonal_capacity_validates_the_same_model_as_other_pairs(mode, valid):
    n = Network(nodes={s: Node(s) for s in ("a", "b")})
    n.add_link(Link("a", "b", 10))
    model = core.FlowPolicyConfig(
        routing=core.ShortestPaths(
            allocation=core.RouteAllocation.WEIGHTED,
            weight_basis=core.WeightBasis.EXPLICIT,
            edge_weights=[1, 1] if valid else [1],
        )
    )
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    query = CapacityQuery(Selector("a"), Selector("a"), model, mode=mode, workers=1)
    step = MaxFlow(source=Selector("a"), target=Selector("a"), model=model, mode=mode)
    if valid:
        rows = capacity(p, query).cases[0].states["converged"].rows
        assert len(rows) == 1 and isinstance(rows[0], SelfPair)
        assert rows[0].node == "a"
        result = run(prepare(Scenario(n, [step], units=UnitsSettings(1))))
        assert isinstance(
            result.steps[0].result.cases[0].states["converged"].rows[0], SelfPair
        )
    else:
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            capacity(p, query)
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            prepare(Scenario(n, [step], units=UnitsSettings(1)))
        with pytest.raises(ValueError, match="edge_weights: expected 2 entries"):
            capacity(p, CapacityQuery(Selector("a"), Selector("b"), model, workers=1))


def network():
    value = Network(
        nodes={name: Node(name, attrs={"owned": [1]}) for name in ("a", "t")}
    )
    value.add_link(Link("a", "t", 1, 3))
    return value


def test_preparation_shares_the_input_records_without_copying_them():
    source = network()
    prepared = prepare(Scenario(source, units=UnitsSettings(1)))
    view = prepared.scenario.network
    assert view is not source and view.nodes is not source.nodes
    assert all(view.nodes[name] is node for name, node in source.nodes.items())
    assert all(view.links[name] is link for name, link in source.links.items())
    with pytest.raises(TypeError, match="read-only"):
        source.nodes["a"].attrs["owned"].append(2)
    source.replace_node("a", attrs={"owned": [1, 2]})
    assert prepared.scenario.network.nodes["a"].attrs["owned"] == [1]
    again = prepare(Scenario(source, units=UnitsSettings(1)))
    assert again.scenario.network.nodes["a"].attrs["owned"] == [1, 2]


REASON = "CentralizedTE with tunnel_count and several sources requires source_allocation=EQUAL"


def capacity_rosters(allocation, large_first=False, singletons=False):
    groups = ["z", "a", "a"] if large_first else ["a", "z", "z"]
    if singletons:
        groups = ["a", "y", "z"]
    n = Network(
        nodes={
            **{
                f"s{i}": Node(f"s{i}", attrs={"group": g}) for i, g in enumerate(groups)
            },
            "t": Node("t"),
        }
    )
    for i in range(3):
        n.add_link(Link(f"s{i}", "t", 10, 1))
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=allocation, tunnel_count=core.TunnelCount(1)
        )
    )
    step = MaxFlow(
        name="cap",
        source=Selector("^s", group_by="group"),
        target=Selector("^t$"),
        mode="pairwise",
        model=config,
        workers=1,
    )
    return Scenario(n, [step], units=UnitsSettings(1))


@pytest.mark.parametrize("large_first", [False, True])
def test_every_relevant_roster_is_validated_at_prepare(large_first):
    with pytest.raises(ValueError) as error:
        prepare(capacity_rosters(core.SourceAllocation.OPTIMIZED, large_first))
    assert type(error.value) is ValueError
    assert str(error.value) == "workflow[0] (name 'cap'): " + REASON
    assert (
        type(error.value.__cause__) is ValueError
        and str(error.value.__cause__) == REASON
    )


@pytest.mark.parametrize(
    "allocation,singletons,expected",
    [
        (core.SourceAllocation.EQUAL, False, [10, 20]),
        (core.SourceAllocation.OPTIMIZED, True, [10, 10, 10]),
    ],
)
def test_valid_rosters_prepare_and_execute(allocation, singletons, expected):
    p = prepare(capacity_rosters(allocation, singletons=singletons))
    result = run(p)
    assert [
        r.result.delivered
        for r in result.steps[0].result.cases[0].states["converged"].rows
    ] == expected


class MaterializedPinned(MaxFlow):
    def query(self, prepared, failures=None):
        from ngraph import CapacityQuery, DirectedLink
        from ngraph.analysis.programs import dag_from_edges

        t = prepared.topology
        program = core.ForwardingProgram.from_dag(
            t.graph,
            [t.node_id_by_name["s0"]],
            [t.node_id_by_name["t"]],
            dag_from_edges(
                t.graph, [t._edge_id_by_ref[DirectedLink("s0|t|0", "forward")]]
            ),
        )
        return CapacityQuery(
            self.source,
            self.target,
            core.FlowPolicyConfig(routing=core.Pinned(program)),
            mode="pairwise",
            workers=1,
        )


@pytest.mark.parametrize("multiple", [False, True])
def test_opaque_pinned_capacity_checks_each_materialized_pair(multiple):
    n = Network(nodes={x: Node(x) for x in ("s0", "s1", "t")})
    for s in ("s0", "s1"):
        n.add_link(Link(s, "t", 10, 1))
    step = MaterializedPinned(
        name="pinned",
        source=Selector("^s" if multiple else "^s0$", group_by="name"),
        target=Selector("^t$"),
        mode="pairwise",
    )
    s = Scenario(n, [step], units=UnitsSettings(1))
    if multiple:
        with pytest.raises(ValueError) as error:
            prepare(s)
        assert type(error.value) is ValueError
        assert (
            str(error.value)
            == "workflow[0] (name 'pinned'): program endpoints do not match policy endpoints"
        )
        assert type(error.value.__cause__) is ValueError
        assert (
            str(error.value.__cause__)
            == "program endpoints do not match policy endpoints"
        )
    else:
        p = prepare(s)
        assert (
            run(p).steps[0].result.cases[0].states["converged"].rows[0].result.delivered
            == 10
        )
