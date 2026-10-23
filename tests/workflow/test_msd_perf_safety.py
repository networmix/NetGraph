"""Repeated MSD invocations preserve their probe history and native snapshots."""

from ngraph.scenario import run
from tests.workflow.test_maximum_supported_demand import msd_scenario


def test_msd_deterministic_evaluation():
    prepared = msd_scenario(
        5, 2, max_bracket_iters=3, max_bisect_iters=2, alpha_tolerance=0.1
    )
    first, second = (run(prepared).steps[0].result for _ in range(2))
    assert first.history == second.history
    assert first.alpha_feasible.value >= 1
    assert first.best_probe_index == second.best_probe_index
    assert first.best_rows[0].result.delivered == second.best_rows[0].result.delivered
    assert first.probe_rows is None and second.probe_rows is None
