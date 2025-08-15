from __future__ import annotations

import pytest

from ngraph.workflow.analysis.capacity_matrix import CapacityMatrixAnalyzer


def _mk_results(step_name: str) -> dict:
    flow_results = [
        {
            "failure_id": "baseline",
            "flows": [
                {"source": "A", "destination": "B", "placed": 2.0},
                {"source": "B", "destination": "C", "placed": 3.0},
            ],
        },
        {
            "failure_id": "it1",
            "flows": [
                {"source": "A", "destination": "B", "placed": 5.0},
                {"source": "B", "destination": "C", "placed": 1.0},
            ],
        },
    ]
    return {"steps": {step_name: {"data": {"flow_results": flow_results}}}}


def test_capacity_matrix_analyzer_happy() -> None:
    step = "s"
    results = _mk_results(step)
    a = CapacityMatrixAnalyzer()
    analysis = a.analyze(results, step_name=step)
    mat = analysis["capacity_matrix"]
    # Smoke: matrix contains expected nodes and positive capacities
    assert "A" in mat.index and "B" in mat.columns
    assert "B" in mat.index and "C" in mat.columns
    assert float(mat.loc["A", "B"]) >= 0.0
    assert float(mat.loc["B", "C"]) >= 0.0


def test_capacity_matrix_analyzer_errors() -> None:
    a = CapacityMatrixAnalyzer()
    with pytest.raises(ValueError):
        a.analyze({"steps": {"x": {"data": {}}}}, step_name="x")
