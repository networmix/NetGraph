"""Failure cases feed real typed analyses, with owned traces and stable demand IDs."""

from random import Random

import netgraph_core as ngc
import pytest

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.failures import FailureRequest, failure_cases
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import MembershipIndex, RiskGroup
from ngraph.model.selectors import Condition, Selector
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement
from tests.failure_fixture import draw
from tests.placement_fixture import network_of


def _network():
    return network_of([("A", "B", 10, 1), ("B", "C", 10, 1), ("A", "C", 5, 1)])


def _prepare(network=None):
    return prepare(Scenario(network or _network(), units=UnitsSettings(1)))


def _policy(*, scope="link", mode="choice", path=None, seed=None, expand=False):
    return FailurePolicy(
        modes=[FailureMode(1, [FailureRule(scope, mode=mode, path=path)])],
        seed=seed,
        expand_groups=expand,
    )


def _capacity(prepared, policy, *, iterations=5, workers=1, trace=False, seed=42):
    return capacity(
        prepared,
        CapacityQuery(
            Selector("^A$"),
            Selector("^C$"),
            failures=FailureRequest(policy, iterations, seed, trace),
            workers=workers,
        ),
    )


def test_named_policy_selection_default_and_unknown_name():
    network = _network()
    demands = {
        "load": DemandSet("load", (DemandSpec(Selector("^A$"), Selector("^C$"), 5),))
    }
    policies = {"down": _policy(mode="all")}

    def scenario(name):
        return Scenario(
            network,
            demand_sets=demands,
            failure_policies=policies,
            units=UnitsSettings(1),
            workflow=[
                TrafficMatrixPlacement(
                    name="load",
                    demand_set="load",
                    failure_policy=name,
                    iterations=3,
                    workers=1,
                )
            ],
        )

    selected = run(prepare(scenario("down"))).steps[0].result
    assert selected.cases[0].states["converged"].totals.delivered_units == 5
    assert selected.cases[1].states["converged"].totals.delivered_units == 0
    assert selected.cases[1].case.occurrences == 3
    default = run(prepare(scenario(None))).steps[0].result
    assert len(default.cases) == 1 and default.cases[0].case.kind == "baseline"
    with pytest.raises(
        ValueError, match="failure policy.*absent|failure_policy.*absent"
    ):
        prepare(scenario("absent"))
    assert len(run(prepare(scenario(None))).steps) == 1


class TestExclusions:
    def test_no_policy(self):
        cases = failure_cases(_prepare(), FailureRequest(None, 10, 42))
        assert len(cases) == 1
        assert cases[0].kind == "baseline" and cases[0].occurrences == 10
        assert cases[0].pattern.excluded_nodes == cases[0].pattern.excluded_links == ()

    def test_choice_with_policy(self):
        prepared = _prepare()
        case = draw(prepared, _policy())
        assert case.pattern.excluded_nodes == ()
        assert len(case.pattern.excluded_links) == 1
        assert set(case.pattern.excluded_links) <= {"A|B|0", "A|C|0", "B|C|0"}

    def test_seeded_exclusions_are_deterministic(self):
        prepared = _prepare()
        request = FailureRequest(_policy(), 20, 42, True)
        first, second = (
            failure_cases(prepared, request),
            failure_cases(prepared, request),
        )
        assert [(case.pattern, case.occurrences, case.trace) for case in first] == [
            (case.pattern, case.occurrences, case.trace) for case in second
        ]

    def test_node_matching_on_disabled_attribute(self):
        network = _network()
        network.disable_node("A")
        policy = FailurePolicy(
            modes=[
                FailureMode(
                    1, [FailureRule("node", [Condition("disabled", "==", True)])]
                )
            ]
        )
        case = draw(_prepare(network), policy)
        assert case.pattern.excluded_nodes == ("A",)
        assert case.pattern.excluded_links == ()

    def test_link_matching_on_capacity_attribute(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(1, [FailureRule("link", [Condition("capacity", ">", 5)])])
            ]
        )
        case = draw(_prepare(), policy)
        assert case.pattern.excluded_links == ("A|B|0", "B|C|0")
        assert case.pattern.excluded_nodes == ()


class TestFailureCapacity:
    def test_no_failure_policy_runs_one_baseline(self):
        value = _capacity(_prepare(), None, iterations=10)
        assert len(value.cases) == 1
        assert value.cases[0].states["converged"].rows[0].result.delivered == 15

    @pytest.mark.parametrize("workers", [1, 2])
    def test_sampled_capacity_and_multiplicity(self, workers):
        value = _capacity(_prepare(), _policy(), iterations=20, workers=workers)
        assert value.metadata.workers == workers
        baseline, *failed = value.cases
        assert baseline.case.id == "baseline" and baseline.case.occurrences == 0
        assert baseline.states["converged"].rows[0].result.delivered == 15
        assert sum(case.case.occurrences for case in failed) == 20
        assert len(failed) == 3
        for case in failed:
            expected = 10 if case.case.pattern.excluded_links == ("A|C|0",) else 5
            assert case.case.pattern.excluded_nodes == ()
            assert case.states["converged"].rows[0].result.delivered == expected
            assert case.case.occurrences > 0

    def test_trace_fields_are_typed_and_owned(self):
        policy = _policy()
        value = _capacity(_prepare(), policy, trace=True)
        assert value.cases[0].case.trace is None
        for case in value.cases[1:]:
            trace = case.case.trace
            assert trace is not None and trace.mode_index == 0
            assert 0 <= trace.draw_index < 5
            assert trace.mode_attrs == {}
            assert len(trace.selections) == 1
            selection = trace.selections[0]
            assert selection.rule_index == 0 and selection.scope == "link"
            assert selection.selected == case.case.pattern.excluded_links
            assert trace.expanded_nodes == trace.expanded_links == ()
            with pytest.raises(TypeError):
                trace.mode_attrs["new"] = True

    def test_trace_absent_when_unrequested(self):
        value = _capacity(_prepare(), _policy(), trace=False)
        assert len(value.cases) > 1
        assert all(case.case.trace is None for case in value.cases)

    def test_baseline_never_sampled_has_no_trace(self):
        value = _capacity(_prepare(), _policy(), trace=True)
        assert value.cases[0].case.id == "baseline"
        assert (
            value.cases[0].case.occurrences == 0 and value.cases[0].case.trace is None
        )

    def test_trace_deterministic(self):
        prepared, policy = _prepare(), _policy()
        first = _capacity(prepared, policy, trace=True)
        second = _capacity(prepared, policy, trace=True)
        assert [
            (case.case.pattern, case.case.occurrences, case.case.trace)
            for case in first.cases
        ] == [
            (case.case.pattern, case.case.occurrences, case.case.trace)
            for case in second.cases
        ]

    def test_first_trace_wins_under_dedup_collision(self):
        policy = FailurePolicy(
            modes=[
                FailureMode(1, [FailureRule("link")], attrs={"label": label})
                for label in ("mode-a", "mode-b")
            ]
        )
        value = _capacity(_prepare(), policy, iterations=16, trace=True, seed=11)
        baseline, failed = value.cases
        assert baseline.case.occurrences == 0 and failed.case.occurrences == 16
        assert failed.case.trace.draw_index == 0
        assert failed.case.trace.mode_index == 0
        assert failed.case.trace.mode_attrs == {"label": "mode-a"}
        assert failed.states["converged"].rows[0].result.delivered == 0

    def test_pairwise_fabric_with_two_failures(self):
        network = network_of(
            [(f"spine{s}", f"leaf{leaf}", 10, 1) for s in (1, 2) for leaf in (1, 2, 3)]
        )
        prepared = _prepare(network)
        policy = FailurePolicy(
            modes=[FailureMode(1, [FailureRule("link", mode="choice", count=2)])]
        )
        value = capacity(
            prepared,
            CapacityQuery(
                Selector("^spine", group_by="name"),
                Selector("^leaf", group_by="name"),
                mode="pairwise",
                workers=2,
                failures=FailureRequest(policy, 10, 123),
            ),
        )
        assert sum(case.case.occurrences for case in value.cases) == 10
        assert len(value.cases[0].states["converged"].rows) == 6
        assert all(
            row.result.delivered == 20
            for row in value.cases[0].states["converged"].rows
        )
        for case in value.cases[1:]:
            excluded = set(case.case.pattern.excluded_links)
            assert len(excluded) == 2
            for row in case.states["converged"].rows:
                source, target = row.endpoints.sources[0], row.endpoints.destinations[0]
                # Enumerate all cuts of the five-node physical graph independently.
                names = sorted(network.nodes)
                cut_values = []
                for mask in range(1 << len(names)):
                    side = {
                        name for index, name in enumerate(names) if mask & (1 << index)
                    }
                    if source in side and target not in side:
                        cut_values.append(
                            sum(
                                link.capacity
                                for identity, link in network.links.items()
                                if identity not in excluded
                                and ((link.source in side) != (link.target in side))
                            )
                        )
                assert row.result.delivered == min(cut_values)

    @pytest.mark.parametrize("workers", [1, 2])
    def test_native_failure_propagates_without_partial_result_and_retry(
        self, monkeypatch, workers
    ):
        prepared, policy = _prepare(), _policy()
        original = ngc.evaluate_demand

        def fail(*args, **kwargs):
            raise MemoryError("native result boundary")

        with monkeypatch.context() as patch:
            patch.setattr(ngc, "evaluate_demand", fail)
            with pytest.raises(MemoryError, match="native result boundary"):
                _capacity(prepared, policy, workers=workers)
        assert ngc.evaluate_demand is original
        assert (
            _capacity(prepared, policy, workers=workers)
            .cases[0]
            .states["converged"]
            .rows[0]
            .result.delivered
            == 15
        )


class TestIdlessDemands:
    def _prepared(self, specs, network=None):
        return prepare(
            Scenario(
                network or _network(),
                demand_sets={"load": DemandSet("load", tuple(specs))},
                units=UnitsSettings(1),
            ),
            demand_sets=("load",),
        )

    def test_idless_combine_under_failures(self):
        prepared = self._prepared([DemandSpec(Selector("^A$"), Selector("^C$"), 5)])
        value = place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["load"],
                failures=FailureRequest(_policy(), 3, 7),
                workers=2,
            ),
        )
        assert value.cases[0].states["converged"].totals.delivered_units == 5
        assert sum(case.case.occurrences for case in value.cases) == 3
        assert all(
            case.states["converged"].rows[0].id == "load|0|0" for case in value.cases
        )

    def test_idless_per_group_under_failures(self):
        network = network_of(
            [(name, "hub", 10, 1) for name in ("dc1/a", "dc1/b", "dc2/a", "dc2/b")]
        )
        prepared = self._prepared(
            [
                DemandSpec(
                    Selector("^(dc[0-9]+)/.*"),
                    Selector("^hub$"),
                    4,
                    group_mode="per_group",
                )
            ],
            network,
        )
        value = place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["load"],
                failures=FailureRequest(_policy(), 2, 7),
                workers=1,
            ),
        )
        baseline = value.cases[0].states["converged"]
        assert len(baseline.rows) == 2
        assert [row.reference_request_units for row in baseline.rows] == [2, 2]
        assert (
            baseline.totals.reference_request_units
            == baseline.totals.delivered_units
            == 4
        )

    def test_generated_ids_are_deterministic(self):
        specs = [
            DemandSpec(Selector("^A$"), Selector("^C$"), 5),
            DemandSpec(Selector("^B$"), Selector("^C$"), 1),
        ]
        first, second = self._prepared(specs), self._prepared(specs)
        assert (
            [item.id for item in first.demand_sets["load"].demands]
            == [item.id for item in second.demand_sets["load"].demands]
            == ["load|0|0", "load|1|0"]
        )

    def test_prepared_idless_placement(self):
        prepared = self._prepared([DemandSpec(Selector("^A$"), Selector("^C$"), 5)])
        for _ in range(2):
            state = (
                place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
                .cases[0]
                .states["converged"]
            )
            assert state.totals.delivered_units == 5 and state.rows[0].id == "load|0|0"

    def test_unresolved_inputs_are_refused(self):
        with pytest.raises(TypeError, match="expected ResolvedDemandSet"):
            PlacementQuery((DemandSpec(Selector("^A$"), Selector("^C$"), 5),))
        prepared = self._prepared([DemandSpec(Selector("^A$"), Selector("^C$"), 5)])
        assert (
            place(prepared, PlacementQuery(prepared.demand_sets["load"], workers=1))
            .cases[0]
            .states["converged"]
            .totals.delivered_units
            == 5
        )


class TestPolicySeedFallback:
    def test_varied_iteration_draws_from_policy_seed(self):
        prepared = _prepare(
            network_of([(f"n{i}", f"n{i + 1}", 1, 1) for i in range(6)])
        )
        request = FailureRequest(_policy(seed=42), 20)
        cases = failure_cases(prepared, request)
        assert len(cases) > 2 and sum(case.occurrences for case in cases) == 20
        expected = {(): 0}
        candidates = tuple(f"n{i}|n{i + 1}|0" for i in range(6))
        for index in range(20):
            rng = Random(42 + index)
            rng.random()
            pattern = tuple(rng.sample(candidates, 1))
            expected[pattern] = expected.get(pattern, 0) + 1
        assert [
            (case.pattern.excluded_links, case.occurrences) for case in cases
        ] == list(expected.items())

    def test_fallback_reproducible(self):
        prepared = _prepare()
        request = FailureRequest(_policy(scope="node", seed=13), 20, failure_trace=True)
        assert [
            (case.pattern, case.occurrences, case.trace)
            for case in failure_cases(prepared, request)
        ] == [
            (case.pattern, case.occurrences, case.trace)
            for case in failure_cases(prepared, request)
        ]


def _hierarchy():
    network = Network(
        nodes={
            name: Node(name) for name in ("n_top", "n_mid", "n_leaf", "n_lat", "other")
        }
    )
    network.risk_groups["top"] = RiskGroup(
        "top", children=[RiskGroup("mid", children=[RiskGroup("leaf")])]
    )
    network.risk_groups["shared"] = RiskGroup("shared")
    for name, groups in (
        ("n_top", {"top"}),
        ("n_mid", {"mid"}),
        ("n_leaf", {"leaf", "shared"}),
        ("n_lat", {"shared"}),
    ):
        network.replace_node(name, risk_groups=groups)
    network.add_link(Link("n_leaf", "other", 10, 1, risk_groups={"leaf"}))
    return network


class TestFailureMembership:
    def test_grandchild_members_excluded_when_top_fails(self):
        case = draw(
            _prepare(_hierarchy()),
            _policy(scope="risk_group", mode="all", path="^top$"),
        )
        assert case.pattern.excluded_nodes == ("n_leaf", "n_mid", "n_top")
        assert case.pattern.excluded_links == ("n_leaf|other|0",)

    def test_expansion_preserves_direct_trace(self):
        case = draw(
            _prepare(_hierarchy()),
            _policy(scope="risk_group", mode="all", path="^top$"),
            trace=True,
        )
        assert case.trace.selections[0].selected == ("top",)
        assert case.trace.expanded_nodes == ("n_leaf", "n_mid", "n_top")
        assert case.trace.expanded_links == ("n_leaf|other|0",)
        assert case.trace.mode_attrs == {}

    def test_deep_hierarchy_rule_scope_symmetry(self):
        prepared = _prepare(_hierarchy())
        via_group = draw(
            prepared, _policy(scope="risk_group", mode="all", path="^top$", expand=True)
        )
        via_nodes = draw(
            prepared,
            _policy(scope="node", mode="all", path="^n_(top|mid|leaf)$", expand=True),
        )
        assert via_group.pattern == via_nodes.pattern
        assert via_group.pattern.excluded_nodes == ("n_lat", "n_leaf", "n_mid", "n_top")

    @pytest.mark.parametrize("expand", [False, True])
    def test_draws_reuse_prepared_membership(self, monkeypatch, expand):
        prepared = _prepare(_hierarchy())

        def unexpected(*args, **kwargs):
            pytest.fail("membership rebuilt during failure draws")

        monkeypatch.setattr(MembershipIndex, "build", unexpected)
        cases = failure_cases(
            prepared,
            FailureRequest(
                _policy(scope="node", mode="all", path="^n_leaf$", expand=expand),
                10,
                42,
            ),
        )
        assert len(cases) == 2 and cases[1].occurrences == 10
        assert cases[1].pattern.excluded_nodes == (
            ("n_lat", "n_leaf") if expand else ("n_leaf",)
        )
