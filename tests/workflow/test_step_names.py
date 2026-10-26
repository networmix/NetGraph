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
    assert str(exc.value) == "workflow[0].demand_set = 'nope': unknown demand set"


def test_a_subclass_labels_its_failure_states_refusal_with_its_class():
    class MyTMP(TrafficMatrixPlacement):
        pass

    with pytest.raises(ValueError, match=r"^workflow\.MyTMP\.failure_states"):
        MyTMP(demand_set="d", failure_states=("nope",))  # type: ignore[arg-type]


def _unnamed_steps():
    """Each built-in step without a name, and one field it refuses."""
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
        (build_graph.BuildGraph, {}, "add_reverse"),
        (cost_power.CostPower, {}, "include_disabled"),
        (max_flow_step.MaxFlow, {}, "failure_trace"),
        (
            maximum_supported_demand_step.MaximumSupportedDemand,
            {"demand_set": "d"},
            "export_details",
        ),
        (network_stats.NetworkStats, {}, "include_disabled"),
        (
            traffic_matrix_placement_step.TrafficMatrixPlacement,
            {"demand_set": "d"},
            "failure_trace",
        ),
        (
            tunnel_count_step.TunnelCountAnalysis,
            {"demand_set": "d", "counts": (1,), "design_demand": 1.0, "offer": 1.0},
            "export_details",
        ),
    ]


@pytest.mark.parametrize(
    ("kind", "fields", "flag"),
    _unnamed_steps(),
    ids=lambda v: getattr(v, "__name__", ""),
)
def test_an_unnamed_steps_field_refusals_use_its_class_name(kind, fields, flag):
    kind(**fields)  # control: the fields alone build the step
    with pytest.raises(ValueError) as error:
        kind(**fields, **{flag: "yes"})
    where = str(error.value).split(": ")[0]
    assert kind.__name__ in where and str(error.value).endswith("got 'yes'")


def test_an_unnamed_max_flows_query_refusals_use_its_class_name():
    from ngraph import PinnedRoutes, RouteSpec, Selector, UnitsSettings
    from ngraph.workflow.max_flow_step import MaxFlow

    net = Network(nodes={k: Node(k) for k in ("s1", "s2", "t")})
    for source in ("s1", "s2"):
        net.add_link(Link(source, "t", 20))
    empty = MaxFlow(source=Selector("^z"), target=Selector("^t$"))
    with pytest.raises(ValueError) as exc:
        run(prepare(Scenario(net, (empty,))))
    assert str(exc.value) == "workflow[0].source: empty selection"
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
    assert str(exc.value) == "workflow[0]: pinned model requires one endpoint pair"


def test_an_unnamed_tunnel_counts_query_refusal_uses_its_class_name():
    from ngraph.workflow.tunnel_count_step import TunnelCountAnalysis

    with pytest.raises(ValueError) as exc:
        TunnelCountAnalysis(demand_set="d", design_demand=1.0, offer=1.0)
    assert str(exc.value) == (
        "workflow step TunnelCountAnalysis: "
        "tunnel_counts.counts: give at least one count or up_to, got ()"
    )
