"""A complete placement step retains one native result per ordered demand."""

from ngraph.results import PlacementAnalysis
from ngraph.scenario import prepare, run
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement
from tests.workflow.test_alpha_resolution_errors import _scenario


def test_tm_basic_behavior_unchanged():
    prepared = prepare(
        _scenario(
            (
                TrafficMatrixPlacement(
                    name="tm", demand_set="load", iterations=2, workers=1
                ),
            )
        )
    )
    value = run(prepared).steps[0]
    assert isinstance(value.result, PlacementAnalysis)
    assert value.question.demands.name == "load"
    assert len(value.result.cases) == 1
    case = value.result.cases[0]
    assert case.case.occurrences == 2
    assert case.states["converged"].totals.delivered_units == 4
    assert case.states["converged"].rows[0].result.edge_flows is None
