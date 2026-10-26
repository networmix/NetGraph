"""One prepared scenario: analyses return their own misses, steps state their needs."""

from dataclasses import dataclass, fields

import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
    run,
)
from ngraph.analysis.preparation import StepNeeds
from ngraph.analysis.topology import PreparedTopology
from ngraph.results import StepOutput, UnitsReport
from ngraph.workflow.base import WorkflowStep
from ngraph.workflow.max_flow_step import MaxFlow


def network():
    value = Network(nodes={name: Node(name) for name in ("s", "a", "b", "c", "t")})
    for middle in ("a", "b", "c"):
        value.add_link(Link("s", middle, 1, 1))
        value.add_link(Link(middle, "t", 1, 1))
    return value


def ecmp(name):
    return MaxFlow(
        name=name,
        source=Selector("^s$"),
        target=Selector("^t$"),
        preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        workers=1,
    )


def test_each_analysis_returns_only_its_own_misses():
    prepared = prepare(Scenario(network(), units=UnitsSettings(0.5, 0.25)))
    assert prepared.units_report.misses == ()
    query = CapacityQuery(
        Selector("^s$"),
        Selector("^t$"),
        ecmp("x").query(prepared).config,
        workers=1,
    )
    first, second = capacity(prepared, query), capacity(prepared, query)
    assert len(first.misses) == len(second.misses) == 1
    assert first.misses == second.misses
    assert first.prepared is prepared and first.topology is prepared.topology
    assert first.units_report == prepared.units_report.with_misses(first.misses)
    assert second.units_report.misses == first.misses
    assert prepared.units_report.misses == ()


def test_run_labels_each_steps_misses_and_composes_the_report_once(monkeypatch):
    prepared = prepare(
        Scenario(
            network(), [ecmp("first"), ecmp("second")], units=UnitsSettings(0.5, 0.25)
        )
    )
    composed = []
    original = UnitsReport.with_misses

    def counted(report, misses):
        composed.append(misses)
        return original(report, misses)

    monkeypatch.setattr(UnitsReport, "with_misses", counted)
    result = run(prepared)
    assert len(composed) == 1
    assert [miss.location.step for miss in result.units_report.misses] == [
        "first",
        "second",
    ]
    assert [step.result.misses[0].location.step for step in result.steps] == [
        None,
        None,
    ]
    assert result.prepared is prepared and result.topology is prepared.topology


@dataclass
class Needs(WorkflowStep):
    """A custom step that asks preparation to bind one demand set."""

    demand_set: str = ""

    def needs(self):
        return StepNeeds(numerical=True, demand_set=self.demand_set)

    def run(self, context):
        bound = context.prepared.demand_sets[self.demand_set]
        return StepOutput({"demands": len(bound.demands)}, None)


def test_custom_step_needs_bind_its_demand_set_and_refuse_unknown_names():
    load = DemandSet("load", (DemandSpec(Selector("^s$"), Selector("^t$"), 1),))
    scenario = Scenario(
        network(), [Needs(name="custom", demand_set="load")], demand_sets={"load": load}
    )
    prepared = prepare(scenario)
    assert set(prepared.demand_sets) == {"load"}
    assert prepared.units_report.scope.workflow_steps == ("custom",)
    assert prepared.units_report.scope.workflow_demand_sets == ("load",)
    assert run(prepared).steps[0].question == {"demands": 1}
    unknown = Scenario(
        network(), [Needs(name="custom", demand_set="nope")], demand_sets={"load": load}
    )
    with pytest.raises(ValueError, match="demand_set = 'nope': unknown demand set"):
        prepare(unknown)


def test_a_step_without_needs_binds_nothing():
    class Plain(WorkflowStep):
        def run(self, context):
            return StepOutput({}, None)

    load = DemandSet("load", (DemandSpec(Selector("^s$"), Selector("^t$"), 1),))
    prepared = prepare(Scenario(network(), [Plain()], demand_sets={"load": load}))
    assert Plain().needs() is None
    assert dict(prepared.demand_sets) == {}
    assert prepared.units_report.scope.workflow_steps == ()


def test_prepared_topology_holds_the_graph_and_its_labels_only():
    assert [field.name for field in fields(PreparedTopology)] == [
        "graph",
        "node_names",
        "node_id_by_name",
        "edge_refs",
        "edges_by_link",
        "disabled",
        "q",
        "pool_heads",
        "pool_budgets",
        "_edge_id_by_ref",
    ]
