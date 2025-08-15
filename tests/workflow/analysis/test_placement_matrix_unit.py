from __future__ import annotations

import pytest

from ngraph.workflow.analysis.placement_matrix import PlacementMatrixAnalyzer


def _mk_results(step_name: str) -> dict:
    flow_results = [
        {
            "failure_id": "baseline",
            "flows": [
                {
                    "source": "A",
                    "destination": "B",
                    "priority": 0,
                    "placed": 1.0,
                },
                {
                    "source": "A",
                    "destination": "B",
                    "priority": 0,
                    "placed": 3.0,
                },
                {
                    "source": "B",
                    "destination": "C",
                    "priority": 1,
                    "placed": 2.0,
                },
            ],
        }
    ]
    return {"steps": {step_name: {"data": {"flow_results": flow_results}}}}


def test_placement_matrix_analyzer_builds_per_priority_and_combined() -> None:
    step = "pm"
    results = _mk_results(step)
    a = PlacementMatrixAnalyzer()
    analysis = a.analyze(results, step_name=step)
    combined = analysis["placement_matrix"]
    by_prio = analysis["placement_matrices"]
    # Combined averages A->B mean placed = (1 + 3)/2 = 2.0
    assert combined.loc["A", "B"] == 2.0
    # Priority 1 B->C value 2.0 only
    assert by_prio[1].loc["B", "C"] == 2.0


def test_placement_matrix_analyzer_requires_data() -> None:
    a = PlacementMatrixAnalyzer()
    with pytest.raises(ValueError):
        a.analyze({"steps": {"x": {"data": {}}}}, step_name="x")
