from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.results.store import Results
from ngraph.workflow.traffic_matrix_placement_step import (
    TrafficMatrixPlacement,
)


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_stores_core_outputs(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with traffic matrix and results store
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.sink = "B"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value: two iterations with structured dicts
    mock_raw = {
        "results": [
            {
                "demands": [
                    {
                        "src": "A",
                        "dst": "B",
                        "priority": 0,
                        "offered_gbps": 10.0,
                        "placed_gbps": 8.0,
                        "placement_ratio": 0.8,
                    }
                ],
                "summary": {
                    "total_offered_gbps": 10.0,
                    "total_placed_gbps": 8.0,
                    "overall_ratio": 0.8,
                },
            },
            {
                "demands": [
                    {
                        "src": "A",
                        "dst": "B",
                        "priority": 0,
                        "offered_gbps": 10.0,
                        "placed_gbps": 10.0,
                        "placement_ratio": 1.0,
                    }
                ],
                "summary": {
                    "total_offered_gbps": 10.0,
                    "total_placed_gbps": 10.0,
                    "overall_ratio": 1.0,
                },
            },
        ],
        "metadata": {"iterations": 2},
        "failure_patterns": {},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step",
        matrix_name="default",
        iterations=2,
        baseline=False,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify new schema outputs exist and have expected shapes
    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_step"]["data"]
    assert isinstance(data, dict)
    assert "flow_results" in data and isinstance(data["flow_results"], list)
    # example iteration-level sanity: ensure summaries present
    for it in data["flow_results"]:
        assert "summary" in it


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_flow_details_edges(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with traffic matrix and results store
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.sink = "B"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value with edges used
    mock_raw = {
        "results": [
            {
                "failure_id": "",
                "failure_state": None,
                "flows": [
                    {
                        "source": "A",
                        "destination": "B",
                        "priority": 0,
                        "demand": 10.0,
                        "placed": 8.0,
                        "dropped": 2.0,
                        "cost_distribution": {},
                        "data": {"edges": ["(u,v,k1)", "(x,y,k2)"]},
                    }
                ],
                "summary": {
                    "total_demand": 10.0,
                    "total_placed": 8.0,
                    "overall_ratio": 0.8,
                    "dropped_flows": 1,
                    "num_flows": 1,
                },
                "data": {},
            },
            {
                "failure_id": "",
                "failure_state": None,
                "flows": [
                    {
                        "source": "A",
                        "destination": "B",
                        "priority": 0,
                        "demand": 10.0,
                        "placed": 10.0,
                        "dropped": 0.0,
                        "cost_distribution": {},
                        "data": {"edges": ["(u,v,k1)"]},
                    }
                ],
                "summary": {
                    "total_demand": 10.0,
                    "total_placed": 10.0,
                    "overall_ratio": 1.0,
                    "dropped_flows": 0,
                    "num_flows": 1,
                },
                "data": {},
            },
        ],
        "metadata": {"iterations": 2},
        "failure_patterns": {},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step",
        matrix_name="default",
        iterations=2,
        baseline=False,
        include_flow_details=True,
        include_used_edges=True,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify edges presence can be found in flow_results entries
    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_step"]["data"]
    flow_results = data["flow_results"]
    entries = flow_results[0].get("flows", []) if flow_results else []
    assert any("edges" in e.get("data", {}) for e in entries)


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_scales_demands(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with a single traffic demand
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "S"
    mock_td.sink = "T"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value (minimal valid structure)
    mock_raw = {
        "results": [
            {
                "demands": [],
                "summary": {
                    "total_offered_gbps": 0.0,
                    "total_placed_gbps": 0.0,
                    "overall_ratio": 1.0,
                },
            }
        ],
        "metadata": {"iterations": 1},
        "failure_patterns": {},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    # Run with alpha scaling
    step = TrafficMatrixPlacement(
        name="tm_step_alpha",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha=2.5,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify demands_config passed into FailureManager had scaled demand
    assert mock_failure_manager.run_demand_placement_monte_carlo.called
    _, kwargs = mock_failure_manager.run_demand_placement_monte_carlo.call_args
    dcfg = kwargs.get("demands_config")
    assert isinstance(dcfg, list) and len(dcfg) == 1
    assert dcfg[0]["source"] == "S"
    assert dcfg[0]["sink"] == "T"
    assert abs(float(dcfg[0]["demand"]) - 25.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_metadata_includes_alpha(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.sink = "B"
    mock_td.demand = 1.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    mock_raw = {
        "results": [
            {
                "demands": [],
                "summary": {
                    "total_offered_gbps": 0.0,
                    "total_placed_gbps": 0.0,
                    "overall_ratio": 1.0,
                },
            }
        ],
        "metadata": {"iterations": 1, "baseline": False},
        "failure_patterns": {},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step_meta",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha=3.0,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Find data.context and assert it contains alpha
    exported = mock_scenario.results.to_dict()
    ctx = exported["steps"]["tm_step_meta"]["data"]["context"]
    assert ctx.get("alpha") == 3.0


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_auto_uses_msd(
    mock_failure_manager_class,
) -> None:
    # Scenario with one TD
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "S"
    td.sink = "T"
    td.demand = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]

    # Populate results metadata: prior MSD step
    # Provide MSD step data in Results store
    mock_scenario.results = Results()
    mock_scenario.results.enter_step("msd1")
    mock_scenario.results.put("metadata", {})
    mock_scenario.results.put(
        "data",
        {
            "alpha_star": 2.0,
            "context": {"matrix_name": "default", "placement_rounds": "auto"},
            "base_demands": [
                {
                    "source": "S",
                    "sink": "T",
                    "demand": 4.0,
                    "mode": "pairwise",
                    "priority": 0,
                    "flow_policy_config": None,
                }
            ],
        },
    )
    mock_scenario.results.exit_step()

    # Minimal MC results
    mock_raw = {
        "results": [
            {
                "demands": [],
                "summary": {
                    "total_offered_gbps": 0.0,
                    "total_placed_gbps": 0.0,
                    "overall_ratio": 1.0,
                },
            }
        ],
        "metadata": {"iterations": 1},
        "failure_patterns": {},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_auto",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha_from_step="msd1",
        alpha_from_field="data.alpha_star",
    )
    step.execute(mock_scenario)

    # Effective demand should be scaled by alpha_star=2.0
    _, kwargs = mock_failure_manager.run_demand_placement_monte_carlo.call_args
    dcfg = kwargs.get("demands_config")
    assert isinstance(dcfg, list) and len(dcfg) == 1
    assert abs(float(dcfg[0]["demand"]) - 8.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_auto_missing_msd_raises(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "S"
    td.sink = "T"
    td.demand = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]

    # No MSD metadata
    mock_scenario.results.get_all_step_metadata.return_value = {}

    step = TrafficMatrixPlacement(
        name="tm_auto",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha_from_step="msd1",
        alpha_from_field="data.alpha_star",
    )
    mock_scenario.results = Results()
    with pytest.raises(ValueError):
        step.execute(mock_scenario)
