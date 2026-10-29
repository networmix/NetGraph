"""Evaluated tunnel plans and graph validation survive empty traffic selections."""

from dataclasses import replace

import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    DirectedLink,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    TunnelCountQuery,
    UnitsSettings,
    capacity,
    prepare,
    resolve_demands,
    run,
    tunnel_counts,
)
from ngraph.analysis.programs import dag_from_edges
from ngraph.results import SelfPair
from ngraph.workflow import MaxFlow, MaximumSupportedDemand, TrafficMatrixPlacement


def network(capacity_=100, sources=("a",)):
    n = Network(nodes={s: Node(s) for s in (*sources, "t")})
    for s in sources:
        n.add_link(Link(s, "t", capacity_))
    return n


def t2(limit, up_to=False):
    return core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(limit, up_to=up_to),
        ),
        admission=core.Admission.LOSSY,
    )


def program(p):
    graph = p.topology.graph
    edge = p.topology._edge_id_by_ref[DirectedLink("a|t|0", "forward")]
    return core.ForwardingProgram.from_dag(
        graph,
        [p.topology.node_id_by_name["a"]],
        [p.topology.node_id_by_name["t"]],
        dag_from_edges(graph, [edge]),
    )


@pytest.mark.parametrize("mode", ["combine", "pairwise"])
@pytest.mark.parametrize("foreign", [False, True])
def test_diagonal_pinned_questions_validate_the_program_graph(mode, foreign):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    origin = prepare(Scenario(network(), units=UnitsSettings(1))) if foreign else p
    config = core.FlowPolicyConfig(
        routing=core.Pinned(program(origin)), admission=core.Admission.LOSSY
    )
    query = CapacityQuery(
        Selector("a"), Selector("a"), config, mode=mode, offer=10, workers=1
    )
    if foreign:
        with pytest.raises(ValueError, match="program belongs to another graph"):
            capacity(p, query)
        with pytest.raises(ValueError, match="program belongs to another graph"):
            capacity(
                p,
                CapacityQuery(
                    Selector("a"), Selector("t"), config, offer=10, workers=1
                ),
            )
        with pytest.raises(ValueError, match="program belongs to another graph"):
            prepare(
                Scenario(
                    network(),
                    [
                        MaxFlow(
                            source=Selector("a"),
                            target=Selector("a"),
                            model=config,
                            mode=mode,
                            offer=10,
                        )
                    ],
                    units=UnitsSettings(1),
                )
            )
    else:
        rows = capacity(p, query).cases[0].states["converged"].rows
        assert len(rows) == 1 and isinstance(rows[0], SelfPair) and rows[0].node == "a"
        assert (
            capacity(
                p,
                CapacityQuery(
                    Selector("a"), Selector("t"), config, offer=10, workers=1
                ),
            )
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 10
        )


@pytest.mark.parametrize(
    "source,target", [("a", "a"), ("missing", "t"), ("disabled", "t")]
)
@pytest.mark.parametrize(
    "model_kind", ["edge_weights", "source_weights", "support", "pinned", "valid"]
)
def test_discarded_demands_still_validate_materialized_models(
    source, target, model_kind
):
    n = network()
    n.add_node(Node("disabled", disabled=True))
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    other = prepare(Scenario(network(), units=UnitsSettings(1)))
    if model_kind == "edge_weights":
        model = core.ShortestPaths(
            allocation=core.RouteAllocation.WEIGHTED,
            weight_basis=core.WeightBasis.EXPLICIT,
            edge_weights=[1],
        )
        reason = "edge_weights: expected 2 entries"
    elif model_kind == "source_weights":
        model = core.CentralizedTE(
            source_allocation=core.SourceAllocation.WEIGHTED, source_weights=[1]
        )
        reason = "source_weights: expected 3 entries"
    elif model_kind == "support":
        model = core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            support=dag_from_edges(other.topology.graph, [0]),
        )
        reason = "support belongs to another graph"
    elif model_kind == "pinned":
        model = core.Pinned(program(other))
        reason = "program belongs to another graph"
    else:
        model = core.ShortestPaths()
        reason = None
    config = core.FlowPolicyConfig(routing=model)
    d = DemandSet("load", (DemandSpec(Selector(source), Selector(target), 7, config),))
    if reason is not None:
        with pytest.raises(ValueError, match=r"demands\.load\[0\].*" + reason):
            resolve_demands(p, d)
        for steps in (
            [],
            [TrafficMatrixPlacement(demand_set="load")],
            [MaximumSupportedDemand(demand_set="load")],
        ):
            with pytest.raises(ValueError, match=r"demands\.load\[0\].*" + reason):
                prepare(
                    Scenario(n, steps, demand_sets={"load": d}, units=UnitsSettings(1)),
                    demand_sets=("load",),
                )
    else:
        resolved = resolve_demands(p, d)
        assert resolved.demands == ()
        assert (
            resolved.accounting[0].declared_units
            == resolved.accounting[0].discarded_units
            == 7
        )
        assert resolved.accounting[0].resolved_units == 0


def test_shared_demand_model_is_validated_once_before_resolution(monkeypatch):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    config = core.FlowPolicyConfig(routing=core.ShortestPaths())
    d = DemandSet(
        "d",
        tuple(
            DemandSpec(Selector("a"), Selector(target), 1, config)
            for target in ("a", "t", "missing")
        ),
    )
    original = core.evaluate_pairs
    calls = []

    def evaluate(graph, pairs, options, **kwargs):
        calls.append((tuple(pairs), options.eligibility.node_allowed().tolist()))
        return original(graph, pairs, options, **kwargs)

    monkeypatch.setattr(core, "evaluate_pairs", evaluate)
    resolved = resolve_demands(p, d)
    assert calls == [((), [False, False])]
    assert len(resolved.demands) == 1
    assert [a.discarded_units for a in resolved.accounting] == [1, 0, 1]


def test_support_and_failure_mask_intersect_in_capacity_and_counts():
    p = prepare(Scenario(network(sources=("a", "b")), units=UnitsSettings(1, 0.075)))
    support = dag_from_edges(
        p.topology.graph,
        [
            p.topology._edge_id_by_ref[DirectedLink(f"{s}|t|0", "forward")]
            for s in ("a", "b")
        ],
    )
    config = core.FlowPolicyConfig(
        routing=core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            support=support,
            tunnel_count=core.TunnelCount(1),
        ),
        admission=core.Admission.LOSSY,
    )
    failure = FailureRequest(
        FailurePolicy(modes=(FailureMode(1, (FailureRule("link", path=r"^b\|t$"),)),)),
        1,
        1,
    )
    a = capacity(
        p,
        CapacityQuery(
            Selector("a|b"),
            Selector("t"),
            config,
            offer=10,
            design_demand=10,
            failures=failure,
            workers=1,
        ),
    )
    assert [
        r.states["converged"].rows[0].result.plan.design_by_head for r in a.cases
    ] == [((0, 5), (1, 5)), ((0, 10),)]
    ds = resolve_demands(
        p, DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, config),))
    )
    baseline = tunnel_counts(p, TunnelCountQuery(ds, (1,), 10, 10, workers=1))
    failed = tunnel_counts(
        p,
        TunnelCountQuery(
            ds,
            (1,),
            10,
            10,
            eligibility=p.topology.graph.eligibility(
                excluded_edges=[
                    p.topology._edge_id_by_ref[DirectedLink("b|t|0", "forward")]
                ]
            ),
            workers=1,
        ),
    )
    assert baseline.rows[0].result.plan.design_by_head == ((0, 5), (1, 5))
    assert failed.rows[0].result.plan.design_by_head == ((0, 10),)


def test_pinned_diagonal_preparation_and_step_accept_an_own_program():
    class OwnProgram(MaxFlow):
        def query(self, prepared, failures=None):
            config = core.FlowPolicyConfig(
                routing=core.Pinned(program(prepared)), admission=core.Admission.LOSSY
            )
            return CapacityQuery(
                Selector("a"), Selector("a"), config, offer=10, workers=1
            )

    p = prepare(Scenario(network(), [OwnProgram(name="own")], units=UnitsSettings(1)))
    value = run(p)
    rows = value.steps[0].result.cases[0].states["converged"].rows
    assert len(rows) == 1 and isinstance(rows[0], SelfPair) and rows[0].node == "a"


def test_each_count_row_uses_its_own_demand_count_and_up_to_plan():
    p = prepare(Scenario(network(sources=("a", "b")), units=UnitsSettings(1, 0.075)))
    config = t2(2)
    ds = resolve_demands(
        p,
        DemandSet(
            "d",
            tuple(
                DemandSpec(Selector(s), Selector("t"), 10, config) for s in ("a", "b")
            ),
        ),
    )
    answer = tunnel_counts(p, TunnelCountQuery(ds, (2, 4), 10, 10, up_to=4, workers=1))
    assert [row.result.plan.tunnels_per_head for row in answer.rows] == [
        2,
        4,
        1,
        2,
        4,
        1,
    ]
    assert [row.result.plan.design_by_head for row in answer.rows] == [
        ((0, 10),)
    ] * 3 + [((1, 10),)] * 3


@pytest.mark.parametrize("admission", [core.Admission.LOSSLESS, core.Admission.LOSSY])
@pytest.mark.parametrize(
    "routing",
    [
        core.DistributedTE(core.TunnelCount(2)),
        core.CentralizedTE(
            source_allocation=core.SourceAllocation.EQUAL,
            tunnel_count=core.TunnelCount(2, up_to=True),
        ),
    ],
)
def test_valid_discarded_tunnel_models_need_no_offer_or_design_question(
    admission, routing
):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    d = DemandSet(
        "d",
        (
            DemandSpec(
                Selector("a"),
                Selector("a"),
                7,
                core.FlowPolicyConfig(routing=routing, admission=admission),
            ),
        ),
    )
    resolved = resolve_demands(p, d)
    assert resolved.demands == ()
    assert (
        resolved.accounting[0].declared_units
        == resolved.accounting[0].discarded_units
        == 7
    )


def test_model_validation_accepts_unhashable_configs():
    class Unhashable(core.FlowPolicyConfig):
        __hash__ = None

    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    valid = Unhashable(routing=core.ShortestPaths())
    d = DemandSet("d", (DemandSpec(Selector("a"), Selector("a"), 1, valid),))
    assert resolve_demands(p, d).accounting[0].discarded_units == 1


def test_pinned_diagonal_checks_the_original_question_options():
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    config = core.FlowPolicyConfig(
        routing=core.Pinned(program(p)), admission=core.Admission.LOSSY
    )
    query = CapacityQuery(Selector("a"), Selector("a"), config, offer=10, workers=1)
    assert isinstance(capacity(p, query).cases[0].states["converged"].rows[0], SelfPair)
    with pytest.raises(ValueError, match="Pinned does not accept design_demand"):
        capacity(p, replace(query, design_demand=10))
    with pytest.raises(
        ValueError, match="Pinned LOSSY evaluation requires a finite offer"
    ):
        capacity(p, replace(query, offer=None))


def test_discarded_own_pinned_model_is_validated_once_with_its_own_endpoints(
    monkeypatch,
):
    p = prepare(Scenario(network(), units=UnitsSettings(1)))
    prog = program(p)
    config = core.FlowPolicyConfig(
        routing=core.Pinned(prog), admission=core.Admission.LOSSY
    )
    original = core.evaluate_demand
    calls = []

    def evaluate(graph, sources, destinations, options):
        calls.append(
            (
                tuple(sources),
                tuple(destinations),
                options.eligibility.node_allowed().tolist(),
                options.offer,
            )
        )
        return original(graph, sources, destinations, options)

    monkeypatch.setattr(core, "evaluate_demand", evaluate)
    d = DemandSet(
        "d",
        tuple(DemandSpec(Selector("a"), Selector("a"), 7, config) for _ in range(2)),
    )
    r = resolve_demands(p, d)
    assert calls == [((0,), (1,), [False, False], 0)]
    assert r.demands == () and sum(a.discarded_units for a in r.accounting) == 14


def shared_link_up_to_scenario(heads, capacity_, volume, precision, resolution="auto"):
    nodes = ", ".join(f"s{i}: {{}}" for i in range(heads))
    links = "\n".join(
        f"    - {{source: s{i}, target: x, capacity: 1000}}" for i in range(heads)
    )
    return Scenario.from_yaml(
        f"""
network:
  nodes: {{{nodes}, x: {{}}, t: {{}}}}
  links:
{links}
    - {{source: x, target: t, capacity: {capacity_}}}
demands:
  d:
    - source: "^s"
      target: "^t$"
      volume: {volume}
      model:
        admission: lossy
        routing:
          type: centralized_te
          source_allocation: equal
          tunnel_count: {{per_head: 256, up_to: true}}
units: {{resolution: {resolution}, precision: {precision}}}
workflow:
  - {{type: TrafficMatrixPlacement, name: tm, demand_set: d}}
"""
    )
