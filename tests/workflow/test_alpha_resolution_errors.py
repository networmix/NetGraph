"""Regression tests for TrafficMatrixPlacement._resolve_alpha error reporting.

A missing/misordered producer step must be reported as such, instead of a
misleading alpha_from_field error (Results.get_step returns {} for unknown
steps, so an isinstance guard alone cannot detect it).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ngraph.results.store import Results
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement


def _mock_scenario() -> MagicMock:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "A"
    td.target = "B"
    td.volume = 10.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy = None
    mock_scenario.demand_set.get_set.return_value = [td]
    mock_scenario.results = Results()
    return mock_scenario


def test_missing_producer_step_reports_step_error() -> None:
    scenario = _mock_scenario()
    step = TrafficMatrixPlacement(
        name="tm",
        demand_set="default",
        iterations=1,
        alpha_from_step="no_such_step",
    )
    with pytest.raises(
        ValueError, match="alpha_from_step 'no_such_step' has no results"
    ):
        step.execute(scenario)


def test_missing_field_in_existing_step_reports_field_error() -> None:
    scenario = _mock_scenario()
    scenario.results.enter_step("msd")
    scenario.results.put("metadata", {})
    scenario.results.put("data", {"other": 1.0})
    scenario.results.exit_step()

    step = TrafficMatrixPlacement(
        name="tm",
        demand_set="default",
        iterations=1,
        alpha_from_step="msd",
        alpha_from_field="data.alpha_star",
    )
    with pytest.raises(ValueError, match="alpha_from_field 'data.alpha_star' missing"):
        step.execute(scenario)


def test_alpha_and_alpha_from_step_are_exclusive() -> None:
    """An explicit alpha next to alpha_from_step would be ignored, so it raises."""
    with pytest.raises(ValueError, match="either alpha or alpha_from_step"):
        TrafficMatrixPlacement(
            name="tm", demand_set="default", alpha=2.0, alpha_from_step="msd"
        )
