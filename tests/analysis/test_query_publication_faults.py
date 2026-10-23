"""Read analyses publish no partial batch and retry after each growing boundary."""

import importlib
from functools import partial

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
    SensitivityQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    paths,
    prepare,
)
from tests.results.test_analysis_wire import project
from tests.scenario.test_publication_faults import fail_after

CASES = [
    ("capacity", "ngraph.analysis.capacity", "selected_pairs", 1),
    ("capacity", "netgraph_core", "evaluate_pairs", 1),
    ("capacity", "ngraph.analysis.capacity", "CapacityRow", 5),
    ("capacity", "ngraph.analysis.capacity", "CaseState", 1),
    ("capacity", "ngraph.analysis.capacity", "CaseResult", 1),
    ("capacity", "ngraph.analysis.capacity", "query_miss", 1),
    ("capacity", "ngraph.analysis.capacity", "CapacityAnalysis", 1),
    ("spf", "netgraph_core", "spf", 5),
    ("spf", "netgraph_core", "resolve_to_paths", 5),
    ("spf", "ngraph.analysis.paths", "PathRow", 5),
    ("spf", "ngraph.analysis.paths", "PathAnalysis", 1),
    ("ksp", "netgraph_core", "ksp", 5),
    ("ksp", "ngraph.analysis.paths", "PathRow", 5),
    ("ksp", "ngraph.analysis.paths", "PathAnalysis", 1),
    ("sensitivity", "netgraph_core", "evaluate_edge_failures", 1),
    ("sensitivity", "ngraph.analysis.sensitivity", "query_miss", 1),
    ("sensitivity", "ngraph.analysis.sensitivity", "SensitivityAnalysis", 1),
]


def fixture(kind, workers):
    network = Network()
    for name in ("m", *(f"s{i}" for i in range(8)), *(f"t{i}" for i in range(8))):
        network.add_node(Node(name))
    for i in range(8):
        network.add_link(Link(f"s{i}", "m", 10, 1))
        network.add_link(Link("m", f"t{i}", 10, 2))
    prepared = prepare(Scenario(network, units=UnitsSettings(1)))
    source, target = Selector("^s", group_by="name"), Selector("^t", group_by="name")
    if kind == "capacity":
        query = CapacityQuery(
            source,
            target,
            mode="pairwise",
            workers=workers,
            outputs=ngc.OutputOptions(edge_flows=True),
        )
        call = partial(capacity, prepared, query)
    elif kind == "sensitivity":
        query = SensitivityQuery(
            source,
            target,
            ngc.FlowPolicyConfig(
                routing=ngc.CentralizedTE(
                    source_allocation=ngc.SourceAllocation.OPTIMIZED
                )
            ),
            workers=workers,
        )
        call = partial(edge_sensitivity, prepared, query)
    else:
        query = PathQuery(
            source,
            target,
            mode="pairwise",
            options=ngc.KspOptions(2)
            if kind == "ksp"
            else ngc.SpfOptions(ngc.Direction.FORWARD),
        )
        call = partial(paths, prepared, query)
    return prepared, call


@pytest.mark.parametrize("grown", [False, True])
@pytest.mark.parametrize(
    "workers,kind,module,attribute,occurrence",
    [
        (workers, *case)
        for case in CASES
        for workers in ((1,) if case[0] in ("spf", "ksp") else (1, 2))
    ],
)
def test_query_publication_failure_keeps_previous_result_and_same_thread_retry(
    monkeypatch, grown, workers, kind, module, attribute, occurrence
):
    prepared, call = fixture(kind, workers)
    previous = call()
    expected = project(previous)
    capacities = tuple(int(v) for v in prepared.topology.graph.edge_capacity_units())
    observations = prepared._input_observations
    if grown:
        assert project(call()) == expected
    with monkeypatch.context() as patch:
        calls = fail_after(
            patch, importlib.import_module(module), attribute, occurrence
        )
        published = []
        with pytest.raises(MemoryError, match="injected"):
            published.append(call())
        assert not published and len(calls) == occurrence
    assert (
        tuple(int(v) for v in prepared.topology.graph.edge_capacity_units())
        == capacities
    )
    assert prepared._input_observations is observations
    assert project(previous) == expected
    assert project(call()) == expected
