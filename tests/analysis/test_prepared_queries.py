"""Prepared physical graphs, independent endpoint queries, and one native sensitivity batch."""

from dataclasses import FrozenInstanceError

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    PathQuery,
    Scenario,
    Selector,
    SelfPair,
    SensitivityQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    paths,
    prepare,
)


def network():
    model = Network()
    for name in ("S1", "S2", "T1"):
        model.add_node(Node(name))
    model.add_link(Link("S1", "T1", 5, 1))
    model.add_link(Link("S2", "T1", 3, 1))
    return model


def prepared(model=None):
    return prepare(
        Scenario(network() if model is None else model, units=UnitsSettings(1))
    )


def test_fractional_cost_refuses_during_preparation_with_link_label_and_control():
    model = network()
    model.replace_link("S1|T1|0", cost=2.5)
    with pytest.raises(ValueError, match=r"link.S1\|T1\|0.cost.*positive integer"):
        prepared(model)
    model.replace_link("S1|T1|0", cost=2)
    assert prepared(model).topology.graph.num_edges() == 4


def test_integral_float_costs_are_preserved_as_positive_integer_native_costs():
    model = network()
    model.replace_link("S1|T1|0", cost=2.0)
    result = paths(prepared(model), PathQuery(Selector("^S1$"), Selector("^T1$")))
    assert result.rows[0].cost == 2
    assert result.rows[0].paths[0].cost() == 2


def test_pair_matrix_retains_singleton_self_and_independent_cross_rows():
    context = prepared()
    result = capacity(
        context,
        CapacityQuery(
            Selector(r"^S[12]$", group_by="name"),
            Selector(r"^(S1|T1)$", group_by="name"),
            mode="pairwise",
            workers=1,
        ),
    )
    rows = result.cases[0].states["converged"].rows
    assert [
        row.capacity_units if isinstance(row, SelfPair) else row.result.delivered
        for row in rows
    ] == [0, 5, 3, 3]
    assert rows[0].node == "S1" and [row.id for row in rows] == [
        f"pair-{i:06d}" for i in range(4)
    ]


def test_query_resolves_selectors_once_before_failure_cases(monkeypatch):
    import ngraph.analysis.demands as demands
    from ngraph import FailureMode, FailurePolicy, FailureRequest, FailureRule

    original = demands.select_nodes
    calls = []

    def select(*args, **kwargs):
        calls.append(args[1])
        return original(*args, **kwargs)

    context = prepared()
    monkeypatch.setattr(demands, "select_nodes", select)
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("link", mode="choice", count=1)])]
    )
    value = capacity(
        context,
        CapacityQuery(
            Selector("^S1$"),
            Selector("^T1$"),
            failures=FailureRequest(policy, 10, seed=42),
            workers=1,
        ),
    )
    assert len(calls) == 2 and len(value.cases) == 3
    assert sum(case.case.occurrences for case in value.cases) == 10


def test_diagonal_rows_are_distinct_immutable_values_with_success_control():
    context = prepared()
    value = capacity(
        context,
        CapacityQuery(
            Selector(".*", group_by="name"),
            Selector(".*", group_by="name"),
            mode="pairwise",
            workers=1,
        ),
    )
    rows = value.cases[0].states["converged"].rows
    diagonal = [row for row in rows if isinstance(row, SelfPair)]
    assert [row.node for row in diagonal] == ["S1", "S2", "T1"]
    assert len({id(row) for row in diagonal}) == 3
    with pytest.raises(FrozenInstanceError):
        diagonal[0].capacity_units = 1
    assert all(row.capacity_units == 0 for row in diagonal)
    assert rows[2].result.delivered == 5


def config():
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )


def test_sensitivity_native_baseline_matches_independent_capacity_question():
    context = prepared()
    source, target = Selector("^S1$"), Selector("^T1$")
    value = edge_sensitivity(
        context, SensitivityQuery(source, target, config(), workers=1)
    )
    assert value.result.baseline.delivered == 5
    assert (
        capacity(context, CapacityQuery(source, target, workers=1))
        .cases[0]
        .states["converged"]
        .rows[0]
        .result.delivered
        == 5
    )
    expected = {("S1|T1|0", "forward"): 5}
    assert {
        (
            context.topology.edge_refs[row.edge].link,
            context.topology.edge_refs[row.edge].direction,
        ): row.delivery_reduction
        for row in value.result.entries
        if row.delivery_reduction
    } == expected


def test_sensitivity_self_refuses_and_capacity_self_is_explicit_zero():
    context = prepared()
    with pytest.raises(ValueError, match="disjoint"):
        edge_sensitivity(
            context,
            SensitivityQuery(Selector("^S1$"), Selector("^S1$"), config(), workers=1),
        )
    row = (
        capacity(context, CapacityQuery(Selector("^S1$"), Selector("^S1$"), workers=1))
        .cases[0]
        .states["converged"]
        .rows[0]
    )
    assert isinstance(row, SelfPair) and row.capacity_units == 0
    assert (
        edge_sensitivity(
            context,
            SensitivityQuery(Selector("^S1$"), Selector("^T1$"), config(), workers=1),
        ).result.baseline.delivered
        == 5
    )


def test_sensitivity_requires_typed_endpoint_arguments_and_has_valid_control():
    with pytest.raises(TypeError, match="Selectors"):
        SensitivityQuery("^S1$", "^T1$", config())
    assert (
        SensitivityQuery(Selector("^S1$"), Selector("^T1$"), config()).source.path
        == "^S1$"
    )


def test_sensitivity_uses_one_native_batch_with_the_prepared_nominal_mask(monkeypatch):
    original = ngc.evaluate_edge_failures
    context = prepared()
    calls = []

    def evaluate(graph, sources, destinations, options, **kwargs):
        calls.append(options.eligibility)
        return original(graph, sources, destinations, options, **kwargs)

    def forbidden(*args, **kwargs):
        pytest.fail("a second Python baseline solve was invoked")

    monkeypatch.setattr(ngc, "evaluate_edge_failures", evaluate)
    monkeypatch.setattr(ngc, "evaluate_demand", forbidden)
    value = edge_sensitivity(
        context,
        SensitivityQuery(Selector("^S1$"), Selector("^T1$"), config(), workers=1),
    )
    assert value.result.baseline.delivered == 5
    assert len(calls) == 1 and calls[0] is context.topology.disabled


def test_group_matrix_has_exact_nine_capacities_without_pseudo_attachments():
    model = Network()
    for prefix in ("s1", "s2", "s3", "t1", "t2", "t3"):
        for suffix in ("a", "b"):
            model.add_node(Node(prefix + suffix))
    model.add_link(Link("s1a", "t1a", 1, 1))
    model.add_link(Link("s2a", "t2a", 2, 1))
    context = prepared(model)
    result = capacity(
        context,
        CapacityQuery(
            Selector(r"^(s\d)"), Selector(r"^(t\d)"), mode="pairwise", workers=1
        ),
    )
    rows = result.cases[0].states["converged"].rows
    assert [row.result.delivered for row in rows] == [1, 0, 0, 0, 2, 0, 0, 0, 0]
    assert (
        context.topology.graph.num_edges() == 4
        and context.topology.graph.num_nodes() == 12
    )
