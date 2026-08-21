"""Regression tests for the deprecated placement_rounds parameter.

placement_rounds never affected placement (the core engine handles
optimization internally). It must remain accepted for YAML backward
compatibility but emit a deprecation warning, must not be forwarded to
FailureManager, and must not be exported in result contexts as if it
influenced the run.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from ngraph.results.store import Results
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement


def test_msd_placement_rounds_warns_when_set(caplog) -> None:
    with caplog.at_level(
        logging.WARNING, logger="ngraph.workflow.maximum_supported_demand_step"
    ):
        MaximumSupportedDemand(name="msd", demand_set="default", placement_rounds=2)
    assert any("placement_rounds" in rec.message for rec in caplog.records)


def test_tm_placement_rounds_warns_when_set(caplog) -> None:
    with caplog.at_level(
        logging.WARNING, logger="ngraph.workflow.traffic_matrix_placement_step"
    ):
        TrafficMatrixPlacement(name="tm", demand_set="default", placement_rounds=2)
    assert any("placement_rounds" in rec.message for rec in caplog.records)


def test_default_placement_rounds_does_not_warn(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="ngraph.workflow"):
        MaximumSupportedDemand(name="msd", demand_set="default")
        TrafficMatrixPlacement(name="tm", demand_set="default")
    assert not any("placement_rounds" in rec.message for rec in caplog.records)


@patch.object(MaximumSupportedDemand, "_evaluate_alpha")
@patch.object(MaximumSupportedDemand, "_build_cache")
def test_msd_context_omits_placement_rounds(
    mock_build_cache: MagicMock, mock_eval: MagicMock
) -> None:
    mock_build_cache.return_value = MagicMock()
    mock_eval.side_effect = lambda cache, alpha: (
        alpha <= 1.0,
        {"placement_ratio": 1.0},
    )

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

    step = MaximumSupportedDemand(name="msd", demand_set="default", placement_rounds=3)
    step.execute(mock_scenario)

    context = mock_scenario.results.to_dict()["steps"]["msd"]["data"]["context"]
    assert "placement_rounds" not in context


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_tm_does_not_forward_placement_rounds(mock_fm_class) -> None:
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

    mock_fm = MagicMock()
    mock_fm_class.return_value = mock_fm
    mock_fm.run_demand_placement_monte_carlo.return_value = {
        "results": [],
        "metadata": {"iterations": 1, "unique_patterns": 0},
    }

    step = TrafficMatrixPlacement(
        name="tm", demand_set="default", iterations=1, placement_rounds=5
    )
    step.execute(mock_scenario)

    _, kwargs = mock_fm.run_demand_placement_monte_carlo.call_args
    assert "placement_rounds" not in kwargs

    context = mock_scenario.results.to_dict()["steps"]["tm"]["data"]["context"]
    assert "placement_rounds" not in context
