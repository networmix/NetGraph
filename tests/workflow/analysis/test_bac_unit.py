from __future__ import annotations

import pandas as pd
import pytest

from ngraph.workflow.analysis.bac import BACAnalyzer


def _mk_results(
    step_name: str,
    series: list[list[tuple[str, str, float]]],
    *,
    step_type: str = "TrafficMatrixPlacement",
) -> dict:
    fr = []
    for i, flows in enumerate(series):
        iteration = {"failure_id": "baseline" if i == 0 else f"it{i}", "flows": []}
        for s, d, placed in flows:
            iteration["flows"].append({"source": s, "destination": d, "placed": placed})
        fr.append(iteration)
    return {
        "workflow": {step_name: {"step_type": step_type}},
        "steps": {step_name: {"data": {"flow_results": fr}}},
    }


def test_bac_analyzer_basic_series_and_quantiles_smoke() -> None:
    step = "s"
    results = _mk_results(step, [[("A", "B", 2.0)], [("A", "B", 4.0)]])
    a = BACAnalyzer()
    analysis = a.analyze(results, step_name=step)
    assert analysis["status"] == "success"
    s: pd.Series = analysis["delivered_series"]
    assert isinstance(s, pd.Series) and len(s) == 2
    qs = analysis["quantiles"]
    # Smoke: quantiles mapping contains typical keys
    for p in (0.50, 0.90, 0.95, 0.99):
        assert p in qs


def test_bac_overlay_when_sibling_matches_failure_ids_smoke() -> None:
    step_a = "placement"
    step_b = "maxflow"
    # Same failure ids across steps -> overlay should be computed
    results = _mk_results(
        step_a,
        [[("A", "B", 1.0)], [("A", "B", 2.0)]],
        step_type="TrafficMatrixPlacement",
    )
    mf = _mk_results(
        step_b, [[("A", "B", 3.0)], [("A", "B", 5.0)]], step_type="MaxFlow"
    )
    # Merge both steps into one doc
    results["steps"][step_b] = mf["steps"][step_b]
    results["workflow"][step_b] = mf["workflow"][step_b]
    a = BACAnalyzer()
    analysis = a.analyze(results, step_name=step_a)
    # Smoke: overlay exists and has comparable length
    ov = analysis["overlay_series"]
    assert ov is not None
    assert len(ov) == len(analysis["delivered_series"])  # type: ignore[arg-type]


def test_bac_requires_flow_results() -> None:
    a = BACAnalyzer()
    with pytest.raises(ValueError):
        a.analyze({"steps": {"x": {"data": {}}}}, step_name="x")


def test_bac_offered_demand_detected_smoke() -> None:
    # Demand present -> offered demand should be detected and positive
    step = "s"
    fr = [
        {
            "failure_id": "baseline",
            "flows": [
                {"source": "A", "destination": "B", "placed": 1.0, "demand": 5.0},
                {"source": "B", "destination": "C", "placed": 2.0, "demand": 7.0},
            ],
        },
        {
            "failure_id": "it1",
            "flows": [
                {"source": "A", "destination": "B", "placed": 3.0, "demand": 5.0},
                {"source": "B", "destination": "C", "placed": 4.0, "demand": 7.0},
            ],
        },
    ]
    results = {
        "workflow": {step: {"step_type": "TrafficMatrixPlacement"}},
        "steps": {step: {"data": {"flow_results": fr}}},
    }
    a = BACAnalyzer()
    analysis = a.analyze(results, step_name=step)
    assert "total_offered" in analysis and float(analysis["total_offered"]) > 0.0
