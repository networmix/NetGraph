"""Unit tests for CostPowerAnalysis notebook analyzer."""

from __future__ import annotations

import math
from typing import Any, Dict

from ngraph.workflow.analysis.cost_power_analysis import CostPowerAnalysis
from ngraph.workflow.analysis.registry import get_default_registry


def _sample_results_doc() -> Dict[str, Any]:
    # Minimal results document containing CostPower and TrafficMatrixPlacement
    return {
        "workflow": {
            "tm": {"step_type": "TrafficMatrixPlacement", "execution_order": 0},
            "cost_power": {"step_type": "CostPower", "execution_order": 1},
        },
        "steps": {
            "tm": {
                "data": {
                    "flow_results": [
                        {
                            "failure_id": "baseline",
                            "failure_state": None,
                            "flows": [
                                # A/B <-> Z/Z, placed=5 -> counts A/B and Z/Z
                                {
                                    "source": "A/B/x",
                                    "destination": "Z/Z/y",
                                    "priority": 0,
                                    "demand": 5.0,
                                    "placed": 5.0,
                                    "dropped": 0.0,
                                    "cost_distribution": {},
                                    "data": {},
                                },
                                # C/D -> A/B, placed=3 -> counts C/D and A/B
                                {
                                    "source": "C/D/m",
                                    "destination": "A/B/n",
                                    "priority": 0,
                                    "demand": 3.0,
                                    "placed": 3.0,
                                    "dropped": 0.0,
                                    "cost_distribution": {},
                                    "data": {},
                                },
                            ],
                            "summary": {
                                "total_demand": 8.0,
                                "total_placed": 8.0,
                                "overall_ratio": 1.0,
                                "dropped_flows": 0,
                                "num_flows": 2,
                            },
                            "data": {},
                        }
                    ]
                }
            },
            "cost_power": {
                "data": {
                    "context": {"aggregation_level": 2},
                    "levels": {
                        # level 2 paths for A/B and C/D; no entry for Z/Z
                        "2": [
                            {
                                "path": "A/B",
                                "platform_capex": 10.0,
                                "platform_power_watts": 2.0,
                                "optics_capex": 5.0,
                                "optics_power_watts": 1.0,
                                "capex_total": 15.0,
                                "power_total_watts": 3.0,
                            },
                            {
                                "path": "C/D",
                                "platform_capex": 20.0,
                                "platform_power_watts": 4.0,
                                "optics_capex": 0.0,
                                "optics_power_watts": 0.0,
                                "capex_total": 20.0,
                                "power_total_watts": 4.0,
                            },
                        ]
                    },
                }
            },
        },
    }


def test_cost_power_analysis_basic() -> None:
    results = _sample_results_doc()
    analyzer = CostPowerAnalysis()
    out = analyzer.analyze(results, step_name="cost_power")

    assert out["status"] == "success"
    assert out["agg_level"] == 2
    assert out["unit"] == "Gbps"
    assert out["traffic_step_used"] == "tm"

    sites = out["site_metrics"]
    # Delivered attribution: A/B gets 5 (first flow dst) + 3 (second flow dst) + 3 (second flow src counted at C/D)
    # Specifically: A/B receives 5 (from first) and 3 (as destination) and also contributes 5 as source? No, first source is A/B/x, so A/B also gets +5 as source.
    # Flows: (A/B)->(Z/Z): both A/B and Z/Z +5; (C/D)->(A/B): both C/D and A/B +3
    assert math.isclose(sites["A/B"]["delivered_gbps"], 8.0)
    assert math.isclose(sites["C/D"]["delivered_gbps"], 3.0)
    assert "Z/Z" in sites and math.isclose(sites["Z/Z"]["delivered_gbps"], 5.0)

    # Absolute metrics preserved for known sites
    assert math.isclose(sites["A/B"]["power_total_watts"], 3.0)
    assert math.isclose(sites["C/D"]["capex_total"], 20.0)

    norm = out["normalized_metrics"]
    # Ratios in W/Gbps and $/Gbps for A/B and C/D
    assert math.isclose(norm["A/B"]["power_per_unit"], 3.0 / 8.0)
    assert math.isclose(norm["A/B"]["cost_per_unit"], 15.0 / 8.0)
    assert math.isclose(norm["C/D"]["power_per_unit"], 4.0 / 3.0)
    assert math.isclose(norm["C/D"]["cost_per_unit"], 20.0 / 3.0)

    # Site without cost/power data should have 0/0 ratios when delivered>0
    assert (
        math.isfinite(norm["Z/Z"]["power_per_unit"])
        and norm["Z/Z"]["power_per_unit"] == 0.0
    )
    assert (
        math.isfinite(norm["Z/Z"]["cost_per_unit"])
        and norm["Z/Z"]["cost_per_unit"] == 0.0
    )


def test_cost_power_registered_in_registry() -> None:
    reg = get_default_registry()
    step_types = reg.get_all_step_types()
    assert "CostPower" in step_types
