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
    mock_td.target = "B"
    mock_td.volume = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Mock FailureManager return value: baseline separate, failure iterations in results
    mock_raw = {
        "baseline": {
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
        "metadata": {"iterations": 2, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step",
        demand_set="default",
        iterations=2,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify schema outputs exist and have expected shapes
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
    mock_td.target = "B"
    mock_td.volume = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Mock FailureManager return value with edges used (baseline separate)
    mock_raw = {
        "baseline": {
            "failure_id": "",
            "failure_state": None,
            "flows": [],
            "summary": {
                "total_demand": 10.0,
                "total_placed": 10.0,
                "overall_ratio": 1.0,
                "dropped_flows": 0,
                "num_flows": 0,
            },
            "data": {},
        },
        "results": [
            {
                "failure_id": "",
                "failure_state": None,
                "flows": [
                    {
                        "source": "A",
                        "destination": "B",
                        "priority": 0,
                        "volume": 10.0,
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
                        "volume": 10.0,
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
        "metadata": {"iterations": 2, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step",
        demand_set="default",
        iterations=2,
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
    mock_td.target = "T"
    mock_td.volume = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

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
        "metadata": {"iterations": 1, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    # Run with alpha scaling
    step = TrafficMatrixPlacement(
        name="tm_step_alpha",
        demand_set="default",
        iterations=1,
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
    assert dcfg[0]["target"] == "T"
    assert abs(float(dcfg[0]["volume"]) - 25.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_metadata_includes_alpha(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.target = "B"
    mock_td.volume = 1.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

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
        "metadata": {"iterations": 1, "baseline": False, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_step_meta",
        demand_set="default",
        iterations=1,
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
    td.target = "T"
    td.volume = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy = None
    mock_scenario.demand_set.get_set.return_value = [td]

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
                    "target": "T",
                    "volume": 4.0,
                    "mode": "pairwise",
                    "priority": 0,
                    "flow_policy": None,
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
        "metadata": {"iterations": 1, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_auto",
        demand_set="default",
        iterations=1,
        alpha_from_step="msd1",
        alpha_from_field="data.alpha_star",
    )
    step.execute(mock_scenario)

    # Effective demand should be scaled by alpha_star=2.0
    _, kwargs = mock_failure_manager.run_demand_placement_monte_carlo.call_args
    dcfg = kwargs.get("demands_config")
    assert isinstance(dcfg, list) and len(dcfg) == 1
    assert abs(float(dcfg[0]["volume"]) - 8.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_auto_missing_msd_raises(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "S"
    td.target = "T"
    td.volume = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy = None
    mock_scenario.demand_set.get_set.return_value = [td]

    # No MSD metadata
    mock_scenario.results.get_all_step_metadata.return_value = {}

    step = TrafficMatrixPlacement(
        name="tm_auto",
        demand_set="default",
        iterations=1,
        alpha_from_step="msd1",
        alpha_from_field="data.alpha_star",
    )
    mock_scenario.results = Results()
    with pytest.raises(ValueError):
        step.execute(mock_scenario)


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_failure_trace_on_results(
    mock_failure_manager_class,
) -> None:
    """Test that failure_trace is present on flow_results when store_failure_patterns=True."""
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.target = "B"
    mock_td.volume = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Create mock result with failure_trace and occurrence_count
    mock_result = MagicMock()
    mock_result.failure_id = "abc123"
    mock_result.failure_state = {"excluded_nodes": [], "excluded_links": ["L1"]}
    mock_result.failure_trace = {
        "mode_index": 0,
        "mode_attrs": {"category": "link_failure"},
        "selections": [
            {
                "rule_index": 0,
                "scope": "link",
                "mode": "choice",
                "matched_count": 5,
                "selected_ids": ["L1"],
            }
        ],
        "expansion": {"nodes": [], "links": [], "risk_groups": []},
    }
    mock_result.occurrence_count = 2
    mock_result.summary = MagicMock()
    mock_result.summary.total_placed = 8.0
    mock_result.to_dict.return_value = {
        "failure_id": "abc123",
        "failure_state": {"excluded_nodes": [], "excluded_links": ["L1"]},
        "failure_trace": mock_result.failure_trace,
        "occurrence_count": 2,
        "flows": [],
        "summary": {
            "total_demand": 10.0,
            "total_placed": 8.0,
            "overall_ratio": 0.8,
            "dropped_flows": 0,
            "num_flows": 1,
        },
    }

    # Mock baseline
    mock_baseline = MagicMock()
    mock_baseline.to_dict.return_value = {
        "failure_id": "",
        "failure_state": {"excluded_nodes": [], "excluded_links": []},
        "failure_trace": None,
        "occurrence_count": 1,
        "flows": [],
        "summary": {
            "total_demand": 10.0,
            "total_placed": 10.0,
            "overall_ratio": 1.0,
            "dropped_flows": 0,
            "num_flows": 1,
        },
    }

    mock_raw = {
        "baseline": mock_baseline,
        "results": [mock_result],
        "metadata": {"iterations": 2, "parallelism": 1, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_patterns",
        demand_set="default",
        iterations=2,
        store_failure_patterns=True,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify flow_results contains failure_trace
    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_patterns"]["data"]

    assert len(data["flow_results"]) == 1
    result = data["flow_results"][0]
    assert result["failure_id"] == "abc123"
    assert result["failure_trace"]["mode_index"] == 0
    assert result["occurrence_count"] == 2

    # Verify baseline is stored separately in data
    assert "baseline" in data
    assert data["baseline"]["failure_id"] == ""


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_no_trace_when_disabled(
    mock_failure_manager_class,
) -> None:
    """Test that failure_trace is None when store_failure_patterns=False."""
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source = "A"
    mock_td.target = "B"
    mock_td.volume = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    mock_result = MagicMock()
    mock_result.failure_trace = None  # No trace when disabled
    mock_result.occurrence_count = 1
    mock_result.summary = MagicMock()
    mock_result.summary.total_placed = 10.0
    mock_result.to_dict.return_value = {
        "failure_id": "",
        "failure_state": None,
        "failure_trace": None,
        "occurrence_count": 1,
        "flows": [],
        "summary": {
            "total_demand": 10.0,
            "total_placed": 10.0,
            "overall_ratio": 1.0,
            "dropped_flows": 0,
            "num_flows": 1,
        },
    }

    mock_raw = {
        "results": [mock_result],
        "metadata": {"iterations": 1, "parallelism": 1, "unique_patterns": 1},
    }
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

    step = TrafficMatrixPlacement(
        name="tm_no_patterns",
        demand_set="default",
        iterations=1,
        store_failure_patterns=False,
    )
    mock_scenario.results = Results()
    step.execute(mock_scenario)

    # Verify flow_results exist but have no trace
    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_no_patterns"]["data"]
    assert len(data["flow_results"]) == 1
    assert data["flow_results"][0]["failure_trace"] is None
