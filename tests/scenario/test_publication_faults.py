"""Preparation and domain publication failures leave the caller's state intact."""

import copy
import importlib
import json
from io import StringIO

import pytest

from ngraph import (
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsReport,
    UnitsSettings,
    prepare,
    run,
    write_json,
)
from ngraph.results import ReportLocation
from ngraph.workflow.build_graph import BuildGraph
from ngraph.workflow.cost_power import CostPower
from ngraph.workflow.max_flow_step import MaxFlow
from ngraph.workflow.network_stats import NetworkStats
from tests.workflow.test_cost_power import _build_simple_components


def scenario():
    network = Network()
    for i in range(48):
        network.add_node(Node(f"site/{i}", attrs={"hardware": {"component": "NodeHW"}}))
    for i in range(47):
        network.add_link(Link(f"site/{i}", f"site/{i + 1}", 10, 2))
    return Scenario(
        network,
        (BuildGraph(), NetworkStats(), CostPower()),
        components_library=_build_simple_components(),
        units=UnitsSettings(1),
    )


def project(value):
    output = StringIO()
    write_json(value, output)
    return json.loads(output.getvalue())


def fail_after(patch, owner, name, occurrence):
    if "." in name:
        parent, name = name.rsplit(".", 1)
        owner = getattr(owner, parent)
    original = getattr(owner, name)
    calls = []

    def failed(*args, **kwargs):
        value = original(*args, **kwargs)
        calls.append(value)
        if len(calls) == occurrence:
            raise MemoryError(f"injected {name}")
        return value

    patch.setattr(owner, name, failed)
    return calls


@pytest.mark.parametrize("grown", [False, True])
@pytest.mark.parametrize(
    "module,attribute,occurrence",
    [
        ("ngraph.model.network", "owned_dict", 1),
        ("ngraph.model.network", "owned_dict", 3),
        ("ngraph.model.network", "frozen_dict", 1),
        ("ngraph.model.network", "frozen_attrs", 1),
        ("ngraph.model.components", "owned_dict", 1),
        ("ngraph.scenario", "replace", 1),
        ("ngraph.scenario", "prepare_scenario", 1),
        ("ngraph.analysis.preparation", "PreparedScenario", 1),
        ("ngraph.analysis.preparation", "with_splits", 1),
        ("ngraph.analysis.topology", "MappingProxyType", 3),
        ("ngraph.analysis.preparation", "MembershipIndex.build", 1),
        ("ngraph.analysis.preparation", "make_report", 1),
        ("ngraph.analysis.units", "input_samples", 1),
        ("ngraph.analysis.units", "input_constraint", 2),
    ],
)
def test_prepare_publication_failure_and_retry(
    monkeypatch, grown, module, attribute, occurrence
):
    source = scenario()
    control = prepare(copy.deepcopy(source))
    expected = project(run(control))
    if grown:
        assert project(run(prepare(source))) == expected
    before_nodes = tuple((n, repr(v)) for n, v in source.network.nodes.items())
    before_links = tuple((n, repr(v)) for n, v in source.network.links.items())
    with monkeypatch.context() as patch:
        calls = fail_after(
            patch, importlib.import_module(module), attribute, occurrence
        )
        with pytest.raises(MemoryError, match="injected"):
            prepare(source)
        assert len(calls) == occurrence
    assert tuple((n, repr(v)) for n, v in source.network.nodes.items()) == before_nodes
    assert tuple((n, repr(v)) for n, v in source.network.links.items()) == before_links
    assert project(run(control)) == expected
    assert project(run(prepare(source))) == expected


@pytest.mark.parametrize("grown", [False, True])
@pytest.mark.parametrize(
    "module,attribute,occurrence",
    [
        ("ngraph.workflow.build_graph", "BuildGraphResult", 1),
        ("ngraph.workflow.build_graph", "StepOutput", 1),
        ("ngraph.workflow.network_stats", "NetworkStatsResult", 1),
        ("ngraph.workflow.network_stats", "StepOutput", 1),
        ("ngraph.workflow.cost_power", "HardwareRow", 5),
        ("ngraph.workflow.cost_power", "CostPowerResult", 1),
        ("ngraph.workflow.cost_power", "StepOutput", 1),
        ("ngraph.workflow.base", "owned_step_result", 2),
        ("ngraph.workflow.base", "StepResult", 2),
        ("ngraph.scenario", "StepContext", 3),
        ("ngraph.scenario", "run_metadata", 1),
        ("ngraph.scenario", "RunResult", 1),
    ],
)
def test_domain_and_run_publication_failure_and_retry(
    monkeypatch, grown, module, attribute, occurrence
):
    prepared = prepare(scenario())
    previous = run(prepared)
    expected = project(previous)
    graph = prepared.topology.graph
    capacities = list(graph.edge_capacity_units())
    if grown:
        assert project(run(prepared)) == expected
    with monkeypatch.context() as patch:
        calls = fail_after(
            patch, importlib.import_module(module), attribute, occurrence
        )
        published = []
        with pytest.raises(MemoryError, match="injected"):
            published.append(run(prepared))
        assert not published and len(calls) == occurrence
    assert prepared.topology.graph is graph
    assert list(graph.edge_capacity_units()) == capacities
    assert project(previous) == expected
    assert project(run(prepared)) == expected


@pytest.mark.parametrize("grown", [False, True])
@pytest.mark.parametrize("boundary", ["location", "merged-report"])
def test_run_units_merge_failure_after_complete_steps_and_same_thread_retry(
    monkeypatch, grown, boundary
):
    # Each step's misses are labelled with its name as it completes; the run
    # merges them into one report once, after the last step.
    import ngraph.results as records
    import ngraph.scenario as scenarios

    network = Network(nodes={name: Node(name) for name in ("s", "a", "b", "c", "t")})
    for middle in ("a", "b", "c"):
        network.add_link(Link("s", middle, 1, 1))
        network.add_link(Link(middle, "t", 1, 1))
    prepared = prepare(
        Scenario(
            network,
            [
                MaxFlow(
                    name=name,
                    source=Selector("^s$"),
                    target=Selector("^t$"),
                    preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
                    workers=1,
                )
                for name in ("first", "second")
            ],
            units=UnitsSettings(0.5, 0.25),
        )
    )
    nominal = prepared.units_report
    assert nominal.misses == () and not nominal.target_met
    previous = run(prepared)
    assert [miss.location.step for miss in previous.units_report.misses] == [
        "first",
        "second",
    ]
    expected = project(previous)
    if grown:
        assert project(run(prepared)) == expected
    owner = scenarios if boundary == "location" else records
    failing = 2 if boundary == "location" else 1
    original = owner.replace
    hits = []

    def failed(value, **kwargs):
        result = original(value, **kwargs)
        selected = (
            boundary == "location"
            and isinstance(value, ReportLocation)
            and "step" in kwargs
        ) or (
            boundary == "merged-report"
            and isinstance(value, UnitsReport)
            and kwargs.get("misses")
        )
        if selected:
            hits.append(result)
            if len(hits) == failing:
                raise MemoryError("injected units merge")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(owner, "replace", failed)
        with pytest.raises(MemoryError, match="units merge"):
            run(prepared)
    assert len(hits) == failing
    assert prepared.units_report is nominal and nominal.misses == ()
    assert project(previous) == expected
    assert project(run(prepared)) == expected
