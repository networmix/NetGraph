"""Canonical physical patterns, independent random draws and first traces."""

from random import Random

import pytest

from ngraph.analysis.failures import (
    FailureRequest,
    failure_cases,
    sampling_metadata,
    schedule_cases,
)
from ngraph.analysis.units import UnitsSettings
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import RiskGroup
from ngraph.scenario import Scenario, prepare


def prepared(network):
    return prepare(Scenario(network, units=UnitsSettings(1)))


def topology():
    network = Network()
    for name in ("t", "a", "b"):
        network.add_node(Node(name))
    network.add_link(Link("a", "b", 2, 1))
    network.add_link(Link("b", "t", 2, 2))
    network.add_link(Link("a", "t", 3, 5))
    return prepared(network)


def test_baseline_presence_and_counts_are_distinct():
    graph = topology()
    (baseline,) = failure_cases(graph, None)
    assert baseline.id == "baseline" and baseline.kind == "baseline"
    assert baseline.occurrences == 0 and baseline.trace is None
    assert baseline.pattern.excluded_nodes == ()
    assert baseline.pattern.excluded_links == ()
    for draws in (0, 4):
        cases = failure_cases(
            graph, FailureRequest(None, draws, seed=23, failure_trace=True)
        )
        assert len(cases) == 1
        assert cases[0].occurrences == draws
        assert (cases[0].trace is None) == (draws == 0)
        if draws:
            assert cases[0].trace.draw_index == 0
            assert cases[0].trace.mode_index is None


def test_bernoulli_oracle_uses_mode_draw_then_sorted_entities_per_draw_seed():
    graph = topology()
    rule = FailureRule("node", mode="random", probability=0.4)
    policy = FailurePolicy(modes=[FailureMode(1, [rule])], seed=7)
    request = FailureRequest(policy, 30, failure_trace=True)
    # Independent derivation: one positive mode still consumes one draw.
    expected = {(): [0, None]}
    for draw_index in range(30):
        rng = Random(7 + draw_index)
        rng.random()
        nodes = tuple(name for name in ("a", "b", "t") if rng.random() < 0.4)
        if nodes not in expected:
            expected[nodes] = [0, draw_index]
        if expected[nodes][1] is None:
            expected[nodes][1] = draw_index
        expected[nodes][0] += 1
    cases = failure_cases(graph, request)
    assert tuple(case.pattern.excluded_nodes for case in cases) == tuple(expected)
    assert tuple(case.occurrences for case in cases) == tuple(
        value[0] for value in expected.values()
    )
    assert sum(case.occurrences for case in cases) == 30
    for index, case in enumerate(cases):
        assert case.id == ("baseline" if index == 0 else f"failure-{index:06d}")
        first_draw = expected[case.pattern.excluded_nodes][1]
        assert case.trace.draw_index == first_draw
        assert case.trace.mode_index == 0
        assert case.trace.selections[0].selected == case.pattern.excluded_nodes
        assert case.trace.selections[0].rule_index == 0
        assert case.trace.selections[0].scope == "node"
        assert case.trace.expanded_nodes == ()
        assert case.trace.expanded_links == ()
        allowed = case.eligibility.node_allowed()
        for name, node in graph.topology.node_id_by_name.items():
            assert bool(allowed[node]) == (name not in case.pattern.excluded_nodes)
    metadata = sampling_metadata(request)
    assert metadata.seed == 7 and metadata.seed_source == "policy"
    assert metadata.draw_seed_rule == "base_plus_draw_index"
    assert metadata.random_rule_algorithm == "per_entity_bernoulli"
    assert sampling_metadata(FailureRequest(policy, seed=9)).seed_source == "query"
    assert sampling_metadata(FailureRequest(None)).seed_source == "unseeded"


def test_different_group_causes_deduplicate_by_expanded_physical_pattern():
    snapshot = topology().scenario.network
    network = Network(dict(snapshot.nodes), dict(snapshot.links))
    network.risk_groups.update({name: RiskGroup(name) for name in ("power", "fiber")})
    network.replace_node("b", risk_groups={"power", "fiber"})
    graph = prepared(network)
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("risk_group", mode="choice")])]
    )
    cases = failure_cases(graph, FailureRequest(policy, 20, seed=5, failure_trace=True))
    assert len(cases) == 2
    assert cases[0].occurrences == 0
    assert cases[1].occurrences == 20
    assert cases[1].pattern.excluded_nodes == ("b",)
    assert cases[1].trace.selections[0].selected in (("fiber",), ("power",))
    assert cases[1].trace.expanded_nodes == ("b",)


def test_failed_physical_link_excludes_both_native_directions():
    graph = topology()
    policy = FailurePolicy(
        modes=[FailureMode(1, [FailureRule("link", path=r"^a\|t$", mode="all")])]
    )
    cases = failure_cases(graph, FailureRequest(policy, 3, seed=11))
    baseline, failed = cases
    assert failed.pattern.excluded_links == ("a|t|0",)
    assert failed.occurrences == 3 and baseline.occurrences == 0
    forward, reverse = graph.topology.edges_by_link["a|t|0"]
    assert not failed.eligibility.edge_allowed()[forward]
    assert not failed.eligibility.edge_allowed()[reverse]
    assert baseline.eligibility.edge_allowed().all()
    assert schedule_cases(cases, lambda case: case.id, 1) == (
        "baseline",
        "failure-000001",
    )
    assert schedule_cases(cases, lambda case: case.id, 2) == (
        "baseline",
        "failure-000001",
    )


@pytest.mark.parametrize("iterations", [-1, True, 1.5])
def test_invalid_iterations_with_success_control(iterations):
    with pytest.raises(ValueError, match="iterations"):
        FailureRequest(None, iterations)
    assert len(failure_cases(topology(), FailureRequest(None, 0))) == 1


def test_lowest_case_error_is_independent_of_worker_completion_and_retry():
    graph = topology()
    policy = FailurePolicy(modes=[FailureMode(1, [FailureRule("node", mode="choice")])])
    cases = failure_cases(graph, FailureRequest(policy, 20, seed=2))
    assert len(cases) >= 3

    def fail(case):
        if case.id != "baseline":
            raise ValueError(case.id)
        return case.id

    for workers in (1, 3):
        with pytest.raises(ValueError, match="failure-000001"):
            schedule_cases(cases, fail, workers)
        assert schedule_cases(cases, lambda case: case.id, workers) == tuple(
            case.id for case in cases
        )
