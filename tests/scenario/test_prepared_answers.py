"""One prepared scenario: analyses share its report, steps state their needs."""

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
from ngraph.results import StepOutput
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


def test_every_analysis_and_run_keep_the_prepared_report():
    import netgraph_core as ngc

    from ngraph import (
        MSDQuery,
        PathQuery,
        PlacementQuery,
        SensitivityQuery,
        TunnelCountQuery,
        edge_sensitivity,
        maximum_supported_demand,
        paths,
        place,
        tunnel_counts,
    )

    load = DemandSet(
        "load",
        (
            DemandSpec(
                Selector("^s$"),
                Selector("^t$"),
                1,
                ngc.FlowPolicyConfig(
                    routing=ngc.CentralizedTE(
                        source_allocation=ngc.SourceAllocation.EQUAL,
                        tunnel_count=ngc.TunnelCount(16),
                    )
                ),
            ),
        ),
    )
    p = prepare(
        Scenario(
            network(),
            [ecmp("cap")],
            demand_sets={"load": load},
            units=UnitsSettings(0.5, 0.25),
        ),
        demand_sets=("load",),
    )
    source, target = Selector("^s$"), Selector("^t$")
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    ds = p.demand_sets["load"]
    values = (
        capacity(p, CapacityQuery(source, target, workers=1)),
        place(p, PlacementQuery(ds, workers=1)),
        edge_sensitivity(p, SensitivityQuery(source, target, config, workers=1)),
        paths(p, PathQuery(source, target)),
        maximum_supported_demand(p, MSDQuery(ds, alpha_max=1)),
        tunnel_counts(p, TunnelCountQuery(ds, (1,), 1, 1, workers=1)),
        run(p),
    )
    assert all(value.units_report is p.units_report for value in values)
    assert all(value.prepared is p and value.topology is p.topology for value in values)
