"""Completed failure cases own no masks; only active solves own dense masks."""

import gc
import io
import weakref
from copy import copy
from dataclasses import FrozenInstanceError, fields, replace
from threading import Lock

import netgraph_core as ngc
import pytest

import ngraph.analysis.capacity as capacity_module
import ngraph.analysis.failures as failures
import ngraph.analysis.placement as placement_module
from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.counts import TunnelCountQuery, tunnel_counts
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.sensitivity import SensitivityQuery, edge_sensitivity
from ngraph.analysis.topology import eligibility
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


def without_mask(case):
    assert "eligibility" not in vars(case)
    assert "eligibility" not in dir(case)
    assert not hasattr(case, "eligibility")


def mask_for(prepared, case):
    return eligibility(
        prepared.topology, case.pattern.excluded_nodes, case.pattern.excluded_links
    )


def test_factory_and_record_operations_need_no_masks(monkeypatch):
    prepared = triangle()

    def fail(*args, **kwargs):
        raise AssertionError("record operation built a mask")

    monkeypatch.setattr(ngc.Graph, "eligibility", fail)
    baseline, case = failures.failure_cases(prepared, request(iterations=2))
    assert [f.name for f in fields(case)] == [
        "id",
        "kind",
        "pattern",
        "occurrences",
        "trace",
    ]
    assert baseline.kind == "baseline" and baseline.occurrences == 0
    assert case.pattern.excluded_nodes == ("b",) and case.occurrences == 2
    explicit = FailureCase(case.id, case.kind, case.pattern, 2, None)
    for record in (baseline, case, explicit, copy(case), replace(case)):
        without_mask(record)
        assert "eligibility" not in repr(record)
        hash(record)
    assert explicit == case == copy(case) == replace(case)
    assert replace(case, occurrences=3).occurrences == 3
    with pytest.raises(AttributeError, match="has no attribute 'eligibility'"):
        _ = case.eligibility
    with pytest.raises(TypeError, match="unexpected keyword argument 'eligibility'"):
        FailureCase(case.id, case.kind, case.pattern, 2, None, eligibility=None)
    with pytest.raises(FrozenInstanceError):
        case.occurrences = 3


@pytest.mark.parametrize("trace", [False, True])
def test_detached_case_and_copy_do_not_retain_preparation(trace):
    prepared = triangle()
    scenario = weakref.ref(prepared)
    topology = weakref.ref(prepared.topology)
    graph = weakref.ref(prepared.topology.graph)
    case = failures.failure_cases(prepared, replace(request(), failure_trace=trace))[1]
    duplicate = copy(case)
    del prepared, case
    gc.collect()
    assert scenario() is topology() is graph() is None
    without_mask(duplicate)
    assert duplicate.pattern.excluded_nodes == ("b",)
    assert (duplicate.trace is not None) == trace
    assert duplicate == replace(duplicate)


@pytest.mark.parametrize("workers", [1, 2])
@pytest.mark.parametrize("path, expected", [("^b$", 3), (".*", 0)])
def test_failure_mask_preserves_capacity_results(workers, path, expected):
    prepared = triangle()
    result = capacity(
        prepared,
        CapacityQuery(
            Selector("^a$"),
            Selector("^t$"),
            failures=request(path=path),
            workers=workers,
        ),
    )
    assert [c.states["converged"].rows[0].result.delivered for c in result.cases] == [
        5,
        expected,
    ]
    for completed in result.cases:
        without_mask(completed.case)


@pytest.mark.parametrize("te", [False, True])
def test_disabled_and_failed_nodes_rebuilt_on_physical_and_augmented_graph(te):
    prepared = triangle(disabled=True, te=te)
    assert bool(prepared.topology.pool_heads) == te
    baseline, failed = failures.failure_cases(prepared, request(path="^a$"))
    for case, excluded in [(baseline, {"b"}), (failed, {"a", "b"})]:
        mask = mask_for(prepared, case)
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
    assert mask_for(prepared, baseline) is prepared.topology.disabled


def test_empty_topology_and_inert_already_disabled_failure():
    empty = prepare(Scenario(Network(), units=UnitsSettings(1)))
    case = failures.failure_cases(empty, None)[0]
    assert mask_for(empty, case).node_allowed().tolist() == []
    assert mask_for(empty, case).edge_allowed().tolist() == []
    prepared = triangle(disabled=True)
    baseline, failed = failures.failure_cases(prepared, request())
    assert failed.pattern.excluded_nodes == ("b",)
    assert (
        mask_for(prepared, failed)
        is mask_for(prepared, baseline)
        is prepared.topology.disabled
    )


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
        assert mask_for(prepared, case).node_allowed().tolist() == [True, True]
        assert mask_for(prepared, case).edge_allowed().tolist() == [
            ref.link not in blocked for ref in prepared.topology.edge_refs
        ]


def test_rebuilt_masks_remain_native_inputs_to_sensitivity_and_tunnel_counts():
    prepared = triangle()
    mask = mask_for(prepared, failures.failure_cases(prepared, request())[1])
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
    mask = mask_for(prepared, failures.failure_cases(prepared, request())[1])
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
    build = eligibility

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
        context.setattr(capacity_module, "eligibility", fail)
        context.setattr(placement_module, "eligibility", fail)
        with pytest.raises(MemoryError, match="^mask b$"):
            ask()
    result = ask()
    assert len(result.cases) == 3
    for value in result.cases:
        without_mask(value.case)


@pytest.mark.parametrize("analysis", ["capacity", "placement", "replay"])
@pytest.mark.parametrize("workers", [1, 2])
def test_only_running_cases_hold_masks_and_export_retains_no_masks(
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
    build = eligibility
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

    monkeypatch.setattr(capacity_module, "eligibility", observe)
    monkeypatch.setattr(placement_module, "eligibility", observe)
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
        without_mask(value.case)
    write_json(result, io.StringIO())
    for value in result.cases:
        without_mask(value.case)
        mask = mask_for(prepared, value.case)
        expected = [name not in value.case.pattern.excluded_nodes for name in "abt"]
        assert mask.node_allowed().tolist() == expected
        row = value.states["converged"].rows[0]
        if value.case.pattern.excluded_nodes == ("a", "b", "t"):
            assert row.result.delivered == 0
