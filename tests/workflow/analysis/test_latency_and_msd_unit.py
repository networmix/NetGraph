from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from ngraph.workflow.analysis.latency import LatencyAnalyzer
from ngraph.workflow.analysis.msd import MSDAnalyzer


def _results_with_flow_details(step_name: str) -> dict:
    # Two iterations; include a baseline so LB uses baseline only
    flow_results = [
        {
            "failure_id": "baseline",
            "flows": [
                {
                    "source": "A",
                    "destination": "B",
                    "placed": 2.0,
                    "cost_distribution": {"5": 2.0},
                },
                {
                    "source": "B",
                    "destination": "C",
                    "placed": 3.0,
                    "cost_distribution": {2.0: 3.0},
                },
            ],
        },
        {
            "failure_id": "iter1",
            "flows": [
                {
                    "source": "A",
                    "destination": "B",
                    "placed": 1.0,
                    "cost_distribution": {6.0: 1.0},
                },
                {
                    "source": "B",
                    "destination": "C",
                    "placed": 1.0,
                    "cost_distribution": {4.0: 1.0},
                },
            ],
        },
    ]
    return {
        "workflow": {step_name: {"step_type": "TrafficMatrixPlacement"}},
        "steps": {step_name: {"data": {"flow_results": flow_results}}},
    }


def test_latency_analyzer_computes_means_and_stretch_smoke() -> None:
    step = "tm"
    results = _results_with_flow_details(step)
    a = LatencyAnalyzer()
    analysis = a.analyze(results, step_name=step)
    df: pd.DataFrame = analysis["metrics"]
    # Smoke: two rows present, numeric columns exist and are finite or NaN where expected
    assert len(df) == 2
    assert "mean_km_per_gbps" in df.columns and "stretch" in df.columns
    assert np.isfinite(df["mean_km_per_gbps"]).all()
    assert df["stretch"].notna().any()


def test_latency_analyzer_requires_step_name_and_data() -> None:
    a = LatencyAnalyzer()
    with pytest.raises(ValueError):
        a.analyze({}, step_name="")
    with pytest.raises(ValueError):
        a.analyze({"steps": {"x": {"data": {}}}}, step_name="x")


def test_msd_analyzer_parses_trace_and_alpha() -> None:
    step = "msd"
    results = {
        "steps": {
            step: {
                "data": {
                    "alpha_star": 0.85,
                    "context": {"acceptance_rule": "min_ratio>=0.9"},
                    "probes": [
                        {"alpha": 0.5, "accepted": False, "min_placement_ratio": 0.6},
                        {"alpha": 0.8, "accepted": True, "min_placement_ratio": 0.95},
                    ],
                }
            }
        }
    }
    a = MSDAnalyzer()
    analysis = a.analyze(results, step_name=step)
    assert analysis["status"] == "success"
    assert math.isclose(analysis["alpha_star"], 0.85)
    t: pd.DataFrame = analysis["trace"]
    # Sorted by alpha
    assert list(t["alpha"]) == sorted(t["alpha"])  # type: ignore[call-arg]
