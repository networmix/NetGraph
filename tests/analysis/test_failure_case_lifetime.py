"""Failure cases own patterns until read; only active solves own dense masks."""

import gc
import io
import rlcompleter
import weakref
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from dataclasses import FrozenInstanceError, fields, replace
from threading import Event, Lock

import netgraph_core as ngc
import pytest

import ngraph.analysis.failures as failures
from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.counts import TunnelCountQuery, tunnel_counts
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.units import UnitsSettings
from ngraph.export import write_json
from ngraph.model.demand import DemandSet, DemandSpec, FlowPolicyPreset
from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Condition, Selector
from ngraph.results import FailureCase
from ngraph.scenario import Scenario, prepare
from ngraph.workflow.tunnel_count_step import TunnelCountAnalysis


def triangle(*, disabled=False, te=False):
    network = Network(
        nodes={name: Node(name, disabled=disabled and name == "b") for name in "abt"}
    )
    for a, b, amount, cost in [("a", "b", 2, 1), ("b", "t", 2, 2), ("a", "t", 3, 5)]:
        network.add_link(Link(a, b, amount, cost))
    policy = (
        FlowPolicyPreset.TE_ECMP_16_LSP
        if te
        else ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    )
    return prepare(
        Scenario(
            network,
            workflow=(
                [
                    TunnelCountAnalysis(
                        "counts", demand_set="d", counts=(1,), design_demand=1, offer=1
                    )
                ]
                if te
                else []
            ),
            units=UnitsSettings(1),
            demand_sets={
                "d": DemandSet(
                    "d", (DemandSpec(Selector("^a$"), Selector("^t$"), 1, policy),)
                )
            },
        ),
        demand_sets=("d",),
    )


def request(scope="node", path="^b$", iterations=1):
    return failures.FailureRequest(
        FailurePolicy(modes=[FailureMode(1, [FailureRule(scope, path=path)])]),
        iterations,
        11,
    )


def unread(case):
    assert "eligibility" not in vars(case)


def test_factory_defers_masks_and_preserves_native_constructor_and_replace(monkeypatch):
    prepared = triangle()
    build = failures.eligibility
    calls = []

    def observe(*args):
        calls.append(args[1:])
        return build(*args)

    monkeypatch.setattr(failures, "eligibility", observe)
    baseline, case = failures.failure_cases(prepared, request())
    assert calls == []
    unread(baseline)
    unread(case)
    assert [f.name for f in fields(case)] == [
        "id",
        "kind",
        "pattern",
        "occurrences",
        "eligibility",
        "trace",
    ]
    explicit = FailureCase(
        case.id, case.kind, case.pattern, 1, prepared.topology.disabled, None
    )
    assert explicit.eligibility is prepared.topology.disabled
    assert calls == []
    cloned = replace(case)
    assert calls == [(("b",), ())]
    assert cloned.eligibility is case.eligibility
    assert case.eligibility.node_allowed().tolist() == [True, False, True]
    assert (
        replace(case, eligibility=explicit.eligibility).eligibility
        is explicit.eligibility
    )
    assert baseline.eligibility is prepared.topology.disabled
    for operation in (setattr, delattr):
        with pytest.raises(FrozenInstanceError):
            operation(
                case, "eligibility", explicit.eligibility
            ) if operation is setattr else operation(case, "eligibility")


@pytest.mark.parametrize("operation", [repr, hash, lambda c: c == copy(c)])
def test_record_operations_read_the_public_mask(operation):
    case = failures.failure_cases(triangle(), request())[1]
    unread(case)
    operation(case)
    assert isinstance(vars(case)["eligibility"], ngc.Eligibility)


def test_unread_mask_is_discoverable_in_interactive_completion():
    case = failures.failure_cases(triangle(), request())[1]
    assert "eligibility" in dir(case)
    unread(case)
    assert (
        rlcompleter.Completer({"case": case}).complete("case.elig", 0)
        == "case.eligibility"
    )
    assert isinstance(vars(case)["eligibility"], ngc.Eligibility)


@pytest.mark.parametrize("read_before_copy", [False, True])
def test_detached_copy_owns_topology_until_read_then_only_native_arrays(
    read_before_copy,
):
    prepared = triangle()
    scenario = weakref.ref(prepared)
    topology = weakref.ref(prepared.topology)
    graph = weakref.ref(prepared.topology.graph)
    case = failures.failure_cases(prepared, request())[1]
    if read_before_copy:
        assert isinstance(case.eligibility, ngc.Eligibility)
    duplicate = copy(case)
    del prepared, case
    gc.collect()
    assert scenario() is None
    assert (topology() is None) == read_before_copy
    mask = duplicate.eligibility
    assert topology() is None and graph() is None
    assert mask.node_allowed().tolist() == [True, False, True]
    view = mask.node_allowed()
    del mask, duplicate
    gc.collect()
    assert view.tolist() == [True, False, True]
    assert not view.flags.writeable


@pytest.mark.parametrize("fail_first", [False, True])
def test_first_read_is_published_once_across_threads_and_retry(monkeypatch, fail_first):
    case = failures.failure_cases(triangle(), request())[1]
    build = failures.eligibility
    entered, release, second_waiting = Event(), Event(), Event()
    calls = []
    original_lock = vars(case)["_eligibility"].lock

    class ObservedLock:
        attempts = 0

        def __enter__(self):
            self.attempts += 1
            if self.attempts == 2:
                second_waiting.set()
            return original_lock.__enter__()

        def __exit__(self, *args):
            return original_lock.__exit__(*args)

    vars(case)["_eligibility"].lock = ObservedLock()

    def slow_build(*args):
        calls.append(1)
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
            if fail_first:
                raise MemoryError("mask allocation")
        return build(*args)

    monkeypatch.setattr(failures, "eligibility", slow_build)
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(lambda: case.eligibility)
        try:
            assert entered.wait(5)
            later = pool.submit(lambda: case.eligibility)
            assert second_waiting.wait(5)
        finally:
            release.set()
        if fail_first:
            with pytest.raises(MemoryError, match="^mask allocation$"):
                first.result(timeout=5)
        else:
            assert first.result(timeout=5) is later.result(timeout=5)
        mask = later.result(timeout=5)
    assert len(calls) == (2 if fail_first else 1)
    assert case.eligibility is mask
    assert mask.node_allowed().tolist() == [True, False, True]


def test_failed_build_keeps_recipe_and_releases_temporary_mask(monkeypatch):
    case = failures.failure_cases(triangle(), request())[1]
    build = failures.eligibility
    temporaries = []

    def fail(*args):
        temporaries.append(weakref.ref(build(*args)))
        raise MemoryError("publication failed")

    with monkeypatch.context() as context:
        context.setattr(failures, "eligibility", fail)
        with pytest.raises(MemoryError, match="^publication failed$"):
            _ = case.eligibility
    gc.collect()
    unread(case)
    assert all(ref() is None for ref in temporaries)
    assert case.eligibility.node_allowed().tolist() == [True, False, True]


@pytest.mark.parametrize("stage", ["graph", "intersection"])
def test_native_build_failure_does_not_publish_and_can_retry(monkeypatch, stage):
    case = failures.failure_cases(triangle(), request())[1]

    def fail(*args, **kwargs):
        raise MemoryError(stage)

    with monkeypatch.context() as context:
        if stage == "graph":
            context.setattr(ngc.Graph, "eligibility", fail)
        else:
            context.setattr(ngc.Eligibility, "intersect", staticmethod(fail))
        with pytest.raises(MemoryError, match=f"^{stage}$"):
            _ = case.eligibility
        unread(case)
        assert vars(case)["_eligibility"].mask is None
        assert vars(case)["_eligibility"].topology is not None
    assert case.eligibility.node_allowed().tolist() == [True, False, True]


@pytest.mark.parametrize("te", [False, True])
def test_disabled_and_failed_nodes_rebuilt_on_physical_and_augmented_graph(te):
    prepared = triangle(disabled=True, te=te)
    assert bool(prepared.topology.pool_heads) == te
    baseline, failed = failures.failure_cases(prepared, request(path="^a$"))
    for case, excluded in [(baseline, {"b"}), (failed, {"a", "b"})]:
        mask = case.eligibility
        assert mask.node_allowed().tolist() == [
            name not in excluded for name in "abt"
        ] + [True] * len(prepared.topology.pool_heads)
        expected = []
        for ref in prepared.topology.edge_refs:
            if hasattr(ref, "link"):
                link = prepared.scenario.network.links[ref.link]
                expected.append(
                    link.source not in excluded and link.target not in excluded
                )
            else:
                expected.append(ref.source not in excluded)
        assert mask.edge_allowed().tolist() == expected
    assert baseline.eligibility is prepared.topology.disabled


def test_empty_topology_and_inert_already_disabled_failure():
    empty = prepare(Scenario(Network(), units=UnitsSettings(1)))
    case = failures.failure_cases(empty, None)[0]
    assert case.eligibility.node_allowed().tolist() == []
    assert case.eligibility.edge_allowed().tolist() == []
    prepared = triangle(disabled=True)
    baseline, failed = failures.failure_cases(prepared, request())
    assert failed.pattern.excluded_nodes == ("b",)
    assert failed.eligibility is baseline.eligibility is prepared.topology.disabled


def test_link_rebuild_preserves_disabled_links_and_parallel_directions():
    network = Network(nodes={name: Node(name) for name in "at"})
    for disabled in (False, False, True):
        network.add_link(Link("a", "t", 3, 1, disabled=disabled))
    prepared = prepare(Scenario(network, units=UnitsSettings(1)))
    sampled = failures.FailureRequest(
        FailurePolicy(
            modes=[
                FailureMode(1, [FailureRule("link", [Condition("id", "==", "a|t|0")])])
            ]
        )
    )
    baseline, failed = failures.failure_cases(prepared, sampled)
    for case, blocked in [(baseline, {"a|t|2"}), (failed, {"a|t|0", "a|t|2"})]:
        assert case.eligibility.node_allowed().tolist() == [True, True]
        assert case.eligibility.edge_allowed().tolist() == [
            ref.link not in blocked for ref in prepared.topology.edge_refs
        ]


def test_rebuilt_masks_remain_native_inputs_to_sensitivity_and_tunnel_counts():
    prepared = triangle()
    mask = failures.failure_cases(prepared, request())[1].eligibility
    result = edge_sensitivity(
        prepared,
        SensitivityQuery(
            Selector("^a$"),
            Selector("^t$"),
            ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
            eligibility=mask,
            workers=2,
        ),
    ).result
    assert result.baseline.delivered == 3
    assert {
        prepared.topology.edge_refs[row.edge].link: row.delivery_reduction
        for row in result.entries
        if row.delivery_reduction
    } == {"a|t|0": 3}
    prepared = triangle(te=True)
    mask = failures.failure_cases(prepared, request())[1].eligibility
    rows = tunnel_counts(
        prepared,
        TunnelCountQuery(
            prepared.demand_sets["d"], (1,), 1, 1, eligibility=mask, workers=2
        ),
    ).rows
    assert len(rows) == 1 and rows[0].result.delivered == 1


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("analysis", ["capacity", "placement"])
def test_case_build_error_leaves_no_partial_analysis_and_retry_succeeds(
    monkeypatch, analysis, workers
):
    prepared = triangle()
    sampled = replace(
        request(),
        policy=FailurePolicy(
            modes=[
                FailureMode(1, [FailureRule("node", path="^b$")]),
                FailureMode(1, [FailureRule("node", path="^t$")]),
            ]
        ),
        iterations=12,
    )
    build = failures.eligibility

    def fail(topology, nodes, links):
        if nodes:
            raise MemoryError("mask " + nodes[0])
        return build(topology, nodes, links)

    def ask():
        if analysis == "capacity":
            return capacity(
                prepared,
                CapacityQuery(
                    Selector("^a$"), Selector("^t$"), failures=sampled, workers=workers
                ),
            )
        return place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["d"], failures=sampled, workers=workers
            ),
        )

    with monkeypatch.context() as context:
        context.setattr(failures, "eligibility", fail)
        with pytest.raises(MemoryError, match="^mask b$"):
            ask()
    result = ask()
    assert len(result.cases) == 3
    for value in result.cases:
        unread(value.case)


@pytest.mark.parametrize("analysis", ["capacity", "placement", "replay"])
@pytest.mark.parametrize("workers", [1, 2])
def test_only_running_cases_hold_masks_and_export_does_not_warm_results(
    monkeypatch, analysis, workers
):
    prepared = triangle()
    sampled = request(path=".*")
    # More distinct patterns than workers, including an all-physical-nodes failure.
    sampled = replace(
        sampled,
        policy=FailurePolicy(
            modes=[
                FailureMode(1, [FailureRule("node", mode="choice")]),
                FailureMode(1, [FailureRule("node", mode="all")]),
            ]
        ),
        iterations=30,
    )
    build = failures.eligibility
    live, peak = 0, 0
    gate = Lock()

    def released():
        nonlocal live
        with gate:
            live -= 1

    def observe(*args):
        nonlocal live, peak
        mask = build(*args)
        if mask is not prepared.topology.disabled:
            with gate:
                live += 1
                peak = max(peak, live)
            weakref.finalize(mask, released)
        return mask

    monkeypatch.setattr(failures, "eligibility", observe)
    if analysis == "capacity":
        result = capacity(
            prepared,
            CapacityQuery(
                Selector("^a$"),
                Selector("^t$"),
                failures=sampled,
                workers=workers,
                export_cost_distribution=True,
            ),
        )
    else:
        result = place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["d"],
                failures=sampled,
                workers=workers,
                states=("converged", "stale", "repair")
                if analysis == "replay"
                else ("converged",),
                export_cost_distribution=True,
            ),
        )
    assert len(result.cases) > workers
    assert live == 0 and 0 < peak <= (1 if analysis == "capacity" else workers)
    for value in result.cases:
        unread(value.case)
    write_json(result, io.StringIO())
    for value in result.cases:
        unread(value.case)
        mask = value.case.eligibility
        expected = [name not in value.case.pattern.excluded_nodes for name in "abt"]
        assert mask.node_allowed().tolist() == expected
        row = value.states["converged"].rows[0]
        if value.case.pattern.excluded_nodes == ("a", "b", "t"):
            assert row.result.delivered == 0
