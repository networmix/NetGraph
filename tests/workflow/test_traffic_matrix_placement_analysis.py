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

    # Mock FailureManager return value
    mock_results = MagicMock()
    mock_results.raw_results = {
        "results": [
            {
                "demand_results": [
                    {
                        "src": "A",
                        "dst": "B",
                        "priority": 0,
                        "offered_demand": 10.0,
                        "placed_demand": 8.0,
                        "unplaced_demand": 2.0,
                        "placement_ratio": 0.8,
                    }
                ]
            },
            {
                "demand_results": [
                    {
                        "src": "A",
                        "dst": "B",
                        "priority": 0,
                        "offered_demand": 10.0,
                        "placed_demand": 10.0,
                        "unplaced_demand": 0.0,
                        "placement_ratio": 1.0,
                    }
                ]
            },
        ]
    }
    mock_results.failure_patterns = {}
    mock_results.metadata = {"iterations": 1}
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

    # Verify results were stored under the new key and include an envelope object
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
