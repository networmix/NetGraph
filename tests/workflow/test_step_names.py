"""One run-name rule for steps built in Python: the name, or the class name when unnamed."""

from __future__ import annotations

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.base import step_name
from ngraph.workflow.network_stats import NetworkStats
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement


def _network() -> Network:
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", 1))
    return net


def test_step_name_is_the_name_or_the_class_name():
    assert step_name(NetworkStats(name="s")) == "s"
    assert step_name(NetworkStats()) == "NetworkStats"


def test_an_unnamed_step_runs_and_publishes_under_its_class_name():
    result = run(prepare(Scenario(_network(), (NetworkStats(),))))
    assert [step.name for step in result.steps] == ["NetworkStats"]


def test_preparation_refusals_name_an_unnamed_step_by_its_class():
    scenario = Scenario(_network(), (TrafficMatrixPlacement(demand_set="nope"),))
    with pytest.raises(ValueError) as exc:
        prepare(scenario)
    assert str(exc.value) == "step TrafficMatrixPlacement: unknown demand set 'nope'"


def test_a_subclass_labels_its_failure_states_refusal_with_its_class():
    class MyTMP(TrafficMatrixPlacement):
        pass

    with pytest.raises(ValueError, match=r"^workflow\.MyTMP\.failure_states"):
        MyTMP(demand_set="d", failure_states=("nope",))  # type: ignore[arg-type]


def _unnamed_steps():
    from ngraph.workflow import (
        build_graph,
        cost_power,
        max_flow_step,
        maximum_supported_demand_step,
        network_stats,
        traffic_matrix_placement_step,
        tunnel_count_step,
    )

    return [
        (build_graph, lambda: build_graph.BuildGraph()),
        (cost_power, lambda: cost_power.CostPower()),
        (max_flow_step, lambda: max_flow_step.MaxFlow()),
        (
            maximum_supported_demand_step,
            lambda: maximum_supported_demand_step.MaximumSupportedDemand(
                demand_set="d"
            ),
        ),
        (network_stats, lambda: network_stats.NetworkStats()),
        (
            traffic_matrix_placement_step,
            lambda: traffic_matrix_placement_step.TrafficMatrixPlacement(
                demand_set="d"
            ),
        ),
        (
            tunnel_count_step,
            lambda: tunnel_count_step.TunnelCountAnalysis(
                demand_set="d", counts=(1,), design_demand=1.0, offer=1.0
            ),
        ),
    ]


@pytest.mark.parametrize(
    ("module", "build"),
    _unnamed_steps(),
    ids=lambda v: getattr(v, "__name__", "").rpartition(".")[2],
)
def test_an_unnamed_steps_field_labels_use_its_class_name(monkeypatch, module, build):
    labels = []
    monkeypatch.setattr(
        module, "own_scalars", lambda record, label, names: labels.append(label)
    )
    step = build()
    assert labels == [f"workflow step {type(step).__name__}"]


def test_an_unnamed_max_flows_query_refusals_use_its_class_name():
    from ngraph import PinnedRoutes, RouteSpec, Selector, UnitsSettings
    from ngraph.workflow.max_flow_step import MaxFlow

    net = Network(nodes={k: Node(k) for k in ("s1", "s2", "t")})
    for source in ("s1", "s2"):
        net.add_link(Link(source, "t", 20))
    empty = MaxFlow(source=Selector("^z"), target=Selector("^t$"))
    with pytest.raises(ValueError) as exc:
        run(prepare(Scenario(net, (empty,))))
    assert str(exc.value) == "step MaxFlow.source: empty selection"
    pinned = MaxFlow(
        source=Selector(r"^(s\d)$"),
        target=Selector("^t$"),
        mode="pairwise",
        model=PinnedRoutes(("r",)),
    )
    scenario = Scenario(
        net,
        (pinned,),
        routes={"r": RouteSpec("s1", nodes=("s1", "t"))},
        units=UnitsSettings(1),
    )
    with pytest.raises(ValueError) as exc:
        run(prepare(scenario))
    assert str(exc.value) == "step MaxFlow: pinned model requires one endpoint pair"


def test_an_unnamed_tunnel_counts_query_refusal_uses_its_class_name():
    from ngraph.workflow.tunnel_count_step import TunnelCountAnalysis

    with pytest.raises(ValueError) as exc:
        TunnelCountAnalysis(demand_set="d", design_demand=1.0, offer=1.0)
    assert str(exc.value) == (
        "workflow step TunnelCountAnalysis: "
        "tunnel_counts.counts: give at least one count or up_to"
    )
