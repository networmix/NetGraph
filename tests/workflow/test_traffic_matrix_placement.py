from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.model.demand.spec import TrafficDemand
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.results.store import Results
from ngraph.workflow.traffic_matrix_placement_step import (
    TrafficMatrixPlacement,
)


def _iteration(
    placed: float = 10.0, demand: float = 10.0, data: dict | None = None
) -> FlowIterationResult:
    """One A->B placement iteration as FailureManager returns it."""
    entry = FlowEntry(
        source="A",
        destination="B",
        priority=0,
        demand=demand,
        placed=placed,
        dropped=demand - placed,
        data=data or {},
    )
    return FlowIterationResult(
        flows=[entry],
        summary=FlowSummary(
            total_demand=demand,
            total_placed=placed,
            overall_ratio=placed / demand,
            dropped_flows=int(placed < demand),
            num_flows=1,
        ),
    )


def _raw(results: list[FlowIterationResult]) -> dict:
    """FailureManager Monte Carlo output around the given failure iterations."""
    return {
        "baseline": _iteration(),
        "results": results,
        "metadata": {"iterations": len(results), "unique_patterns": len(results)},
    }


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_stores_core_outputs(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = TrafficDemand(
        source="A",
        target="B",
        volume=10.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Mock FailureManager return value: baseline separate, failure iterations in results
    mock_raw = _raw([_iteration(placed=8.0), _iteration()])
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

    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_step"]["data"]
    assert isinstance(data, dict)
    assert "flow_results" in data and isinstance(data["flow_results"], list)
    for it in data["flow_results"]:
        assert "summary" in it


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_flow_details_edges(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = TrafficDemand(
        source="A",
        target="B",
        volume=10.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Mock FailureManager return value with edges used (baseline separate)
    mock_raw = _raw(
        [
            _iteration(placed=8.0, data={"edges": ["(u,v,k1)", "(x,y,k2)"]}),
            _iteration(data={"edges": ["(u,v,k1)"]}),
        ]
    )
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

    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_step"]["data"]
    flow_results = data["flow_results"]
    entries = flow_results[0].get("flows", []) if flow_results else []
    assert any("edges" in e.get("data", {}) for e in entries)


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_scales_demands(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = TrafficDemand(
        source="S",
        target="T",
        volume=10.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    # Mock FailureManager return value (minimal valid structure)
    mock_raw = _raw([_iteration()])
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_raw

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
    mock_td = TrafficDemand(
        source="A",
        target="B",
        volume=1.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [mock_td]

    mock_raw = _raw([_iteration()])
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

    exported = mock_scenario.results.to_dict()
    ctx = exported["steps"]["tm_step_meta"]["data"]["context"]
    assert ctx.get("alpha") == 3.0


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_alpha_auto_uses_msd(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    td = TrafficDemand(
        source="S",
        target="T",
        volume=4.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [td]

    # Data from a prior MSD step in the results store
    mock_scenario.results = Results()
    mock_scenario.results.enter_step("msd1")
    mock_scenario.results.put("metadata", {})
    mock_scenario.results.put(
        "data",
        {
            "alpha_star": 2.0,
            "context": {"demand_set": "default"},
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
    mock_raw = _raw([_iteration()])
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
    td = TrafficDemand(
        source="S",
        target="T",
        volume=4.0,
        mode="pairwise",
    )
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
    mock_td = TrafficDemand(
        source="A",
        target="B",
        volume=10.0,
        mode="pairwise",
    )
    mock_scenario.demand_set.get_set.return_value = [mock_td]

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
        "expansion": {"nodes": [], "links": []},
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

    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_patterns"]["data"]

    assert len(data["flow_results"]) == 1
    result = data["flow_results"][0]
    assert result["failure_id"] == "abc123"
    assert result["failure_trace"]["mode_index"] == 0
    assert result["occurrence_count"] == 2

    # Baseline is stored separately from flow_results
    assert "baseline" in data
    assert data["baseline"]["failure_id"] == ""


@patch("ngraph.workflow.traffic_matrix_placement_step.FailureManager")
def test_traffic_matrix_placement_no_trace_when_disabled(
    mock_failure_manager_class,
) -> None:
    """Test that failure_trace is None when store_failure_patterns=False."""
    mock_scenario = MagicMock()
    mock_td = TrafficDemand(
        source="A",
        target="B",
        volume=10.0,
        mode="pairwise",
    )
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
        "baseline": _iteration(),
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

    exported = mock_scenario.results.to_dict()
    data = exported["steps"]["tm_no_patterns"]["data"]
    assert len(data["flow_results"]) == 1
    assert data["flow_results"][0]["failure_trace"] is None
