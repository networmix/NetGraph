from __future__ import annotations

from unittest.mock import MagicMock, patch

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
