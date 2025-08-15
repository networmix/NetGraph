from __future__ import annotations

from typing import Any

import pandas as pd

from ngraph.workflow.analysis.bac import BACAnalyzer
from ngraph.workflow.analysis.capacity_matrix import CapacityMatrixAnalyzer
from ngraph.workflow.analysis.latency import LatencyAnalyzer
from ngraph.workflow.analysis.msd import MSDAnalyzer


def _nop_show(*args: Any, **kwargs: Any) -> None:  # pragma: no cover - utility
    return None


def test_bac_display_and_analyze_and_display_smoke(monkeypatch) -> None:
    # Prepare small results doc
    step = "s"
    results = {
        "workflow": {step: {"step_type": "TrafficMatrixPlacement"}},
        "steps": {
            step: {
                "data": {
                    "flow_results": [
                        {
                            "failure_id": "baseline",
                            "flows": [
                                {"source": "A", "destination": "B", "placed": 1.0}
                            ],
                        },
                        {
                            "failure_id": "it1",
                            "flows": [
                                {"source": "A", "destination": "B", "placed": 2.0}
                            ],
                        },
                    ]
                }
            }
        },
    }
    a = BACAnalyzer()
    analysis = a.analyze(results, step_name=step)
    # Patch matplotlib show
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", _nop_show)
    a.display_analysis(analysis)
    # BACAnalyzer has no analyze_and_display_step; smoke only for display


def test_latency_display_smoke(monkeypatch) -> None:
    # Build analysis dict with a small DataFrame
    step = "lat"
    a = LatencyAnalyzer()
    df = pd.DataFrame(
        [
            {
                "failure_id": "baseline",
                "mean_km_per_gbps": 1.0,
                "stretch": float("nan"),
                "total_delivered_gbps": 1.0,
            },
            {
                "failure_id": "it1",
                "mean_km_per_gbps": 2.0,
                "stretch": 1.0,
                "total_delivered_gbps": 2.0,
            },
        ]
    )
    analysis = {
        "status": "success",
        "step_name": step,
        "metrics": df,
        "lower_bounds": {},
    }
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", _nop_show)
    a.display_analysis(analysis)


def test_msd_display_smoke(monkeypatch) -> None:
    a = MSDAnalyzer()
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", _nop_show)
    analysis = {
        "status": "success",
        "step_name": "msd",
        "alpha_star": 0.9,
        "acceptance_rule": "rule",
        "trace": pd.DataFrame(
            [
                {"alpha": 0.5, "feasible": False, "min_placement_ratio": 0.6},
                {"alpha": 0.9, "feasible": True, "min_placement_ratio": 1.0},
            ]
        ),
    }
    a.display_analysis(analysis)


def test_capacity_matrix_display_and_wrapper(monkeypatch) -> None:
    step = "cap"
    results = {
        "steps": {
            step: {
                "data": {
                    "flow_results": [
                        {
                            "failure_id": "baseline",
                            "flows": [
                                {"source": "A", "destination": "B", "placed": 2.0},
                                {"source": "B", "destination": "C", "placed": 3.0},
                            ],
                        }
                    ]
                }
            }
        }
    }
    a = CapacityMatrixAnalyzer()
    analysis = a.analyze(results, step_name=step)
    import matplotlib.pyplot as plt

    monkeypatch.setattr(plt, "show", _nop_show)
    a.display_analysis(analysis)
    a.analyze_and_display_step(results, step_name=step)
