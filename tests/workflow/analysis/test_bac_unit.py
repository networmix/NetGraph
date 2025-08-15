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


def test_bac_analyzer_basic_series_and_quantiles() -> None:
    step = "s"
    results = _mk_results(step, [[("A", "B", 2.0)], [("A", "B", 4.0)]])
    a = BACAnalyzer()
    analysis = a.analyze(results, step_name=step)
    s: pd.Series = analysis["delivered_series"]
    assert list(s.values) == [2.0, 4.0]
    qs = analysis["quantiles"]
    assert qs[0.5] in (2.0, 4.0)


def test_bac_overlay_when_sibling_matches_failure_ids() -> None:
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
    assert analysis["overlay_series"] is not None
    assert len(analysis["overlay_series"]) == len(analysis["delivered_series"])


def test_bac_requires_flow_results() -> None:
    a = BACAnalyzer()
    with pytest.raises(ValueError):
        a.analyze({"steps": {"x": {"data": {}}}}, step_name="x")
