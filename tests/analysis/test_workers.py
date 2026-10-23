"""Public worker defaults have one CPU-count rule across native models."""

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    SensitivityQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    place,
    prepare,
)


@pytest.mark.parametrize(
    "model",
    [
        ngc.ShortestPaths(),
        ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
    ],
)
@pytest.mark.parametrize("workers,expected", [("auto", 3), (1, 1), (2, 2)])
def test_worker_resolution_and_native_semantic_control(
    model, workers, expected, monkeypatch
):
    import ngraph.analysis.failures as failures

    monkeypatch.setattr(failures.os, "cpu_count", lambda: 3)
    network = Network()
    for name in ("s", "t"):
        network.add_node(Node(name))
    network.add_link(Link("s", "t", 4, 2))
    config = ngc.FlowPolicyConfig(routing=model)
    demands = DemandSet(
        "load", (DemandSpec(Selector("^s$"), Selector("^t$"), 3, config),)
    )
    prepared = prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    cap = capacity(
        prepared,
        CapacityQuery(Selector("^s$"), Selector("^t$"), config, workers=workers),
    )
    placed = place(
        prepared, PlacementQuery(prepared.demand_sets["load"], workers=workers)
    )
    sensitivity = edge_sensitivity(
        prepared,
        SensitivityQuery(Selector("^s$"), Selector("^t$"), config, workers=workers),
    )
    assert [value.metadata.workers for value in (cap, placed, sensitivity)] == [
        expected
    ] * 3
    assert (
        cap.cases[0].states["converged"].rows[0].result.delivered
        == sensitivity.result.baseline.delivered
        == 4
    )
    assert placed.cases[0].states["converged"].totals.delivered_units == 3


@pytest.mark.parametrize("workers", [True, False, 0, -1, 1.0, "many"])
def test_invalid_worker_values_refuse_on_all_public_queries_with_valid_control(workers):
    source, target = Selector("^s$"), Selector("^t$")
    config = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    for build in (
        lambda value: CapacityQuery(source, target, workers=value),
        lambda value: SensitivityQuery(source, target, config, workers=value),
    ):
        with pytest.raises(ValueError, match="workers"):
            build(workers)
        assert build(1).workers == 1
