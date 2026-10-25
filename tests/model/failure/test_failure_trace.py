"""Typed trace ownership, deduplication and native analysis integration."""

from dataclasses import replace

import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import RiskGroup
from ngraph.model.selectors import Condition, Selector
from ngraph.scenario import Scenario, prepare
from tests.failure_fixture import draw, policy_network


class TestFailureTracePolicyLevel:
    def test_trace_captures_mode_index(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(0, []),
                FailureMode(1, [FailureRule("node")], {"name": "mode1"}),
            ]
        )
        trace = draw(policy_network(), policy, trace=True).trace
        assert trace.mode_index == 1
        assert dict(trace.mode_attrs) == {"name": "mode1"}

    def test_trace_captures_mode_attrs(self):
        attrs = {"severity": "high", "nested": {"region": "west"}}
        policy = FailurePolicy(modes=[FailureMode(1, [FailureRule("node")], attrs)])
        trace = draw(policy_network(), policy, trace=True).trace
        attrs["nested"]["region"] = "changed"
        with pytest.raises(TypeError, match="read-only"):
            policy.modes[0].attrs["nested"]["region"] = "changed-again"
        assert dict(trace.mode_attrs) == {
            "severity": "high",
            "nested": {"region": "west"},
        }

    def test_trace_captures_selection_fields(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1,
                    [
                        FailureRule(
                            "node",
                            [Condition("vendor", "==", "cisco")],
                            mode="choice",
                            count=1,
                        )
                    ],
                )
            ]
        )
        case = draw(policy_network(), policy, trace=True)
        (selection,) = case.trace.selections
        assert selection.rule_index == 0 and selection.scope == "node"
        assert len(selection.selected) == 1
        assert selection.selected == case.pattern.excluded_nodes
        assert set(selection.selected) <= {"N1", "N3"}

    def test_trace_empty_selection_when_no_match(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("node", [Condition("vendor", "==", "absent")])]
                )
            ]
        )
        case = draw(policy_network(), policy, trace=True)
        # Every declared rule keeps its ordinal, including an empty selection.
        (selection,) = case.trace.selections
        assert selection.rule_index == 0 and selection.scope == "node"
        assert selection.selected == ()
        assert case.pattern.excluded_nodes == ()

    def test_trace_captures_expansion_nodes_links(self):
        network = Network(risk_groups={"shared": RiskGroup("shared")})
        network.add_node(Node("a", risk_groups={"shared"}))
        network.add_node(Node("b", risk_groups={"shared"}))
        network.add_link(Link("a", "b", 10, 3, risk_groups={"shared"}))
        policy = FailurePolicy(
            expand_groups=True,
            modes=[FailureMode(1, [FailureRule("node", path="^a$")])],
        )
        case = draw(prepare(Scenario(network)), policy, trace=True)
        assert case.trace.selections[0].selected == ("a",)
        assert case.trace.expanded_nodes == ("b",)
        assert case.trace.expanded_links == ("a|b|0",)
        assert case.pattern.excluded_nodes == ("a", "b")

    def test_trace_without_a_policy_returns_null_mode_index(self):
        trace = draw(policy_network(), None, trace=True).trace
        assert trace.mode_index is None and dict(trace.mode_attrs) == {}
        assert trace.selections == ()
        assert trace.expanded_nodes == trace.expanded_links == ()

    def test_trace_disabled_does_not_populate(self):
        policy = FailurePolicy(modes=[FailureMode(1, [FailureRule("node")])])
        assert draw(policy_network(), policy).trace is None
        assert draw(policy_network(), policy, trace=True).trace is not None

    def test_trace_deterministic_with_seed(self):
        prepared = policy_network()
        policy = FailurePolicy(
            modes=[FailureMode(1, [FailureRule("node", mode="choice", count=1)])]
        )
        assert (
            draw(prepared, policy, trace=True).trace
            == draw(prepared, policy, trace=True).trace
        )


def _analysis(*, trace=True, iterations=5, policy=None):
    prepared = policy_network()
    if policy is None:
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("link", mode="choice", count=1)], {"test": "attr"}
                )
            ]
        )
    query = CapacityQuery(
        Selector("^N1$"),
        Selector("^N2$"),
        failures=FailureRequest(policy, iterations, 42, trace),
        workers=2,
    )
    return prepared, query, capacity(prepared, query)


class TestFailureTraceAnalysisIntegration:
    def test_results_include_trace_fields(self):
        _, _, result = _analysis()
        assert sum(case.case.occurrences for case in result.cases) == 5
        for case in result.cases[1:]:
            assert case.case.trace.mode_index == 0
            assert dict(case.case.trace.mode_attrs) == {"test": "attr"}
            assert case.case.trace.selections[0].scope == "link"
            expected = 0 if "N1|N2|0" in case.case.pattern.excluded_links else 10
            assert case.states["converged"].rows[0].result.delivered == expected

    def test_baseline_has_no_trace_fields(self):
        _, _, result = _analysis()
        assert result.cases[0].case.id == "baseline"
        assert result.cases[0].case.trace is None
        assert result.cases[0].states["converged"].rows[0].result.delivered == 10

    def test_deduplication_produces_unique_patterns(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("node", [Condition("vendor", "==", "cisco")])]
                )
            ]
        )
        prepared, query, result = _analysis(policy=policy)
        assert len(result.cases) == 2
        assert result.cases[1].case.occurrences == 5
        assert result.cases[1].case.trace.draw_index == 0
        assert result.cases[1].case.pattern.excluded_nodes == ("N1", "N3")
        assert result.cases[1].states["converged"].rows[0].result.delivered == 0
        cases = failure_cases(prepared, query.failures)
        assert len(cases) == 2 and cases[1].occurrences == 5

    def test_trace_deterministic_across_runs(self):
        prepared, query, first = _analysis()
        second = capacity(prepared, replace(query, workers=1))
        assert [
            (case.case.pattern, case.case.occurrences, case.case.trace)
            for case in first.cases
        ] == [
            (case.case.pattern, case.case.occurrences, case.case.trace)
            for case in second.cases
        ]

    def test_no_trace_when_disabled(self):
        prepared, query, result = _analysis(trace=False)
        assert all(case.case.trace is None for case in result.cases)
        control = capacity(
            prepared,
            replace(query, failures=replace(query.failures, failure_trace=True)),
        )
        assert control.cases[1].case.trace is not None
        assert [
            (case.case.pattern, case.case.occurrences) for case in control.cases
        ] == [(case.case.pattern, case.case.occurrences) for case in result.cases]


def test_untraced_draws_build_no_trace_and_keep_the_same_patterns(monkeypatch):
    import ngraph.analysis.failures as failures

    policy = FailurePolicy(
        seed=5,
        modes=[FailureMode(1, [FailureRule("node", mode="random", probability=0.5)])],
    )
    prepared = policy_network()
    traced = failure_cases(prepared, FailureRequest(policy, 40, None, True))

    def forbidden(*args, **kwargs):
        raise AssertionError("trace built without a request")

    with monkeypatch.context() as patch:
        patch.setattr(failures, "FailureTrace", forbidden)
        patch.setattr(failures, "FailureSelection", forbidden)
        plain = failure_cases(prepared, FailureRequest(policy, 40, None, False))
    assert [(c.pattern, c.occurrences) for c in plain] == [
        (c.pattern, c.occurrences) for c in traced
    ]
    assert all(c.trace is None for c in plain)
    assert all(c.trace is not None for c in traced[1:])


def test_a_failure_request_shares_its_immutable_policy():
    policy = FailurePolicy(modes=[FailureMode(1, [FailureRule("node")])])
    assert FailureRequest(policy, 2).policy is policy
