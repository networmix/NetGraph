from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.workflow.traffic_matrix_placement_analysis import (
    TrafficMatrixPlacementAnalysis,
)


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_stores_envelopes(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with traffic matrix and results store
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source_path = "A"
    mock_td.sink_path = "B"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value (two iterations with different ratios)
    mock_results = MagicMock()
    mock_results.raw_results = {
        "results": [
            [
                {
                    "src": "A",
                    "dst": "B",
                    "priority": 0,
                    "metric": "placement_ratio",
                    "value": 0.8,
                }
            ],
            [
                {
                    "src": "A",
                    "dst": "B",
                    "priority": 0,
                    "metric": "placement_ratio",
                    "value": 1.0,
                }
            ],
        ]
    }
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 2}
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_results

    step = TrafficMatrixPlacementAnalysis(
        name="tm_step",
        matrix_name="default",
        iterations=2,
        baseline=False,
    )
    step.run(mock_scenario)

    # Verify results were stored under the new key and include an envelope dict
    put_calls = mock_scenario.results.put.call_args_list
    stored = {args[1]: args[2] for args, _ in (call for call in put_calls)}
    assert "placement_envelopes" in stored
    envelopes = stored["placement_envelopes"]
    assert isinstance(envelopes, dict)
    key = "A->B|prio=0"
    assert key in envelopes
    env = envelopes[key]
    # Envelope should be a plain dict ready for JSON export
    assert isinstance(env, dict)
    for k in [
        "source",
        "sink",
        "mode",
        "priority",
        "frequencies",
        "min",
        "max",
        "mean",
        "stdev",
        "total_samples",
    ]:
        assert k in env


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_flow_details_aggregated(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with traffic matrix and results store
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source_path = "A"
    mock_td.sink_path = "B"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value with cost_distribution data
    mock_results = MagicMock()
    mock_results.raw_results = {
        "results": [
            [
                {
                    "src": "A",
                    "dst": "B",
                    "priority": 0,
                    "metric": "placement_ratio",
                    "value": 0.8,
                    "stats": {
                        "cost_distribution": {1.0: 5.0, 2.0: 3.0},
                        "edges": ["(u,v,k1)", "(x,y,k2)"],
                        "edges_kind": "used",
                    },
                }
            ],
            [
                {
                    "src": "A",
                    "dst": "B",
                    "priority": 0,
                    "metric": "placement_ratio",
                    "value": 1.0,
                    "stats": {
                        "cost_distribution": {1.0: 7.0, 3.0: 2.0},
                        "edges": ["(u,v,k1)"],
                        "edges_kind": "used",
                    },
                }
            ],
        ]
    }
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 2}
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_results

    step = TrafficMatrixPlacementAnalysis(
        name="tm_step",
        matrix_name="default",
        iterations=2,
        baseline=False,
        include_flow_details=True,
    )
    step.run(mock_scenario)

    # Verify flow_summary_stats aggregated into envelope
    put_calls = mock_scenario.results.put.call_args_list
    stored = {args[1]: args[2] for args, _ in (call for call in put_calls)}
    envelopes = stored["placement_envelopes"]
    env = envelopes["A->B|prio=0"]
    assert "flow_summary_stats" in env
    stats = env["flow_summary_stats"]
    cds = stats.get("cost_distribution_stats", {})
    # cost 1.0 has volumes [5.0, 7.0] -> mean 6.0, min 5.0, max 7.0, samples 2
    assert 1.0 in cds
    assert abs(cds[1.0]["mean"] - 6.0) < 1e-9
    assert cds[1.0]["min"] == 5.0
    assert cds[1.0]["max"] == 7.0
    assert cds[1.0]["total_samples"] == 2
    # edge frequencies counted across iterations
    edge_freq = stats.get("edge_usage_frequencies", {})
    assert edge_freq.get("(u,v,k1)") == 2
    assert edge_freq.get("(x,y,k2)") == 1


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_alpha_scales_demands(
    mock_failure_manager_class,
) -> None:
    # Prepare mock scenario with a single traffic demand
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source_path = "S"
    mock_td.sink_path = "T"
    mock_td.demand = 10.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    # Mock FailureManager return value (minimal valid structure)
    mock_results = MagicMock()
    mock_results.raw_results = {"results": [[]]}
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 1}
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_results

    # Run with alpha scaling
    step = TrafficMatrixPlacementAnalysis(
        name="tm_step_alpha",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha=2.5,
    )
    step.run(mock_scenario)

    # Verify demands_config passed into FailureManager had scaled demand
    assert mock_failure_manager.run_demand_placement_monte_carlo.called
    _, kwargs = mock_failure_manager.run_demand_placement_monte_carlo.call_args
    dcfg = kwargs.get("demands_config")
    assert isinstance(dcfg, list) and len(dcfg) == 1
    assert dcfg[0]["source_path"] == "S"
    assert dcfg[0]["sink_path"] == "T"
    assert abs(float(dcfg[0]["demand"]) - 25.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_metadata_includes_alpha(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    mock_td = MagicMock()
    mock_td.source_path = "A"
    mock_td.sink_path = "B"
    mock_td.demand = 1.0
    mock_td.mode = "pairwise"
    mock_td.priority = 0
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [mock_td]

    mock_results = MagicMock()
    mock_results.raw_results = {"results": [[]]}
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 1, "baseline": False}
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_results

    step = TrafficMatrixPlacementAnalysis(
        name="tm_step_meta",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha=3.0,
    )
    step.run(mock_scenario)

    # Find metadata put call and assert it contains alpha
    put_calls = mock_scenario.results.put.call_args_list
    meta_values = [
        args[2] for args, _ in (call for call in put_calls) if args[1] == "metadata"
    ]
    assert meta_values, "metadata not stored"
    metadata = meta_values[-1]
    assert isinstance(metadata, dict)
    assert metadata.get("alpha") == 3.0


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_alpha_auto_uses_msd(
    mock_failure_manager_class,
) -> None:
    # Scenario with one TD
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source_path = "S"
    td.sink_path = "T"
    td.demand = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]

    # Populate results metadata: prior MSD step
    from ngraph.results.store import WorkflowStepMetadata

    msd_meta = WorkflowStepMetadata(
        step_type="MaximumSupportedDemandAnalysis", step_name="msd1", execution_order=0
    )
    tmpa_meta = WorkflowStepMetadata(
        step_type="TrafficMatrixPlacementAnalysis",
        step_name="tm_auto",
        execution_order=1,
    )
    # get_all_step_metadata returns dict
    mock_scenario.results.get_all_step_metadata.return_value = {
        "msd1": msd_meta,
        "tm_auto": tmpa_meta,
    }
    # MSD stored values
    mock_scenario.results.get.side_effect = (
        # First calls come from TrafficMatrixPlacementAnalysis logic:
        # Will call get(step_name, "context") for msd1
        {"matrix_name": "default", "placement_rounds": "auto"},
        # Then get(step_name, "base_demands")
        [
            {
                "source_path": "S",
                "sink_path": "T",
                "demand": 4.0,
                "mode": "pairwise",
                "priority": 0,
                "flow_policy_config": None,
            }
        ],
        # Then get(step_name, "alpha_star")
        2.0,
    )

    # Minimal MC results
    mock_results = MagicMock()
    mock_results.raw_results = {"results": [[]]}
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 1}
    mock_failure_manager = MagicMock()
    mock_failure_manager_class.return_value = mock_failure_manager
    mock_failure_manager.run_demand_placement_monte_carlo.return_value = mock_results

    step = TrafficMatrixPlacementAnalysis(
        name="tm_auto",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha="auto",
    )
    step.run(mock_scenario)

    # Effective demand should be scaled by alpha_star=2.0
    _, kwargs = mock_failure_manager.run_demand_placement_monte_carlo.call_args
    dcfg = kwargs.get("demands_config")
    assert isinstance(dcfg, list) and len(dcfg) == 1
    assert abs(float(dcfg[0]["demand"]) - 8.0) < 1e-12


@patch("ngraph.workflow.traffic_matrix_placement_analysis.FailureManager")
def test_traffic_matrix_placement_analysis_alpha_auto_missing_msd_raises(
    mock_failure_manager_class,
) -> None:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source_path = "S"
    td.sink_path = "T"
    td.demand = 4.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]

    # No MSD metadata
    mock_scenario.results.get_all_step_metadata.return_value = {}

    step = TrafficMatrixPlacementAnalysis(
        name="tm_auto",
        matrix_name="default",
        iterations=1,
        baseline=False,
        alpha="auto",
    )
    with pytest.raises(ValueError):
        step.run(mock_scenario)
