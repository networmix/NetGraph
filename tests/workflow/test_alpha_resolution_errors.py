"""Placement accepts only a tested feasible alpha from an earlier MSD step."""

from dataclasses import replace

import pytest

from ngraph.analysis.units import UnitsSettings
from ngraph.model.demand import DemandSet, DemandSpec
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from ngraph.results import MSDAnalysis, StepContext
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.build_graph import BuildGraph
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement


def _scenario(workflow, *, failure_policies=None):
    network = Network()
    network.add_node(Node("A"))
    network.add_node(Node("B"))
    network.add_link(Link("A", "B", capacity=4, cost=3))
    demands = DemandSet("load", (DemandSpec(Selector("^A$"), Selector("^B$"), 4),))
    return Scenario(
        network,
        workflow,
        demand_sets={"load": demands},
        failure_policies=failure_policies,
        units=UnitsSettings(1),
    )


def _producer():
    return MaximumSupportedDemand(name="msd", demand_set="load", alpha_tolerance=1)


def _consumer():
    return TrafficMatrixPlacement(
        name="tm", demand_set="load", alpha_from_step="msd", workers=1
    )


@pytest.mark.parametrize(
    "workflow",
    [
        (_consumer(),),
        (_consumer(), _producer()),
        (BuildGraph(name="msd"), _consumer()),
    ],
)
def test_missing_producer_step_reports_step_error(workflow):
    with pytest.raises(ValueError, match="alpha_from_step 'msd'.*earlier MSD"):
        prepare(_scenario(workflow))
    result = run(prepare(_scenario((_producer(), _consumer()))))
    producer, consumer = result.steps
    assert isinstance(producer.result, MSDAnalysis)
    assert producer.result.alpha_feasible.value == 1
    assert consumer.question.alpha == producer.result.alpha_feasible.value
    assert consumer.question.alpha_from_step == "msd"
    assert consumer.result.cases[0].states["converged"].totals.delivered_units == 4


def test_producer_without_tested_feasible_alpha_refuses():
    prepared = prepare(_scenario((_producer(), _consumer())))
    producer = run(prepare(_scenario((_producer(),)))).steps[0]
    context = StepContext(prepared, {"msd": producer}, "tm", 1, None, "none")
    assert _consumer().execute(context).question.alpha == 1
    absent = replace(producer, result=replace(producer.result, alpha_feasible=None))
    with pytest.raises(ValueError, match="no tested feasible alpha"):
        _consumer().execute(replace(context, prior_results={"msd": absent}))
    with pytest.raises(ValueError, match="expected an earlier MSD result"):
        _consumer().execute(replace(context, prior_results={}))


def test_alpha_and_alpha_from_step_are_exclusive():
    with pytest.raises(ValueError, match="alpha and alpha_from_step are exclusive"):
        TrafficMatrixPlacement(
            name="tm", demand_set="load", alpha=2, alpha_from_step="msd"
        )
    assert TrafficMatrixPlacement(demand_set="load", alpha=2).alpha == 2
