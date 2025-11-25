"""Scenario snapshot helpers.

Build a concise dictionary snapshot of failure policies and traffic matrices for
export into results without keeping heavy domain objects.
"""

from __future__ import annotations

from typing import Any, Dict


def build_scenario_snapshot(
    *,
    seed: int | None,
    failure_policy_set,
    traffic_matrix_set,
) -> Dict[str, Any]:
    snapshot_failure_policies: Dict[str, Any] = {}
    for name, policy in getattr(failure_policy_set, "policies", {}).items():
        modes_list: list[dict[str, Any]] = []
        for mode in getattr(policy, "modes", []) or []:
            mode_dict = {
                "weight": float(getattr(mode, "weight", 0.0)),
                "rules": [],
                "attrs": dict(getattr(mode, "attrs", {}) or {}),
            }
            for rule in getattr(mode, "rules", []) or []:
                mode_dict["rules"].append(
                    {
                        "entity_scope": getattr(rule, "entity_scope", "node"),
                        "logic": getattr(rule, "logic", "or"),
                        "rule_type": getattr(rule, "rule_type", "all"),
                        "probability": float(getattr(rule, "probability", 1.0)),
                        "count": int(getattr(rule, "count", 1)),
                        "conditions": [
                            {
                                "attr": c.attr,
                                "operator": c.operator,
                                "value": c.value,
                            }
                            for c in getattr(rule, "conditions", []) or []
                        ],
                    }
                )
            modes_list.append(mode_dict)
        snapshot_failure_policies[name] = {
            "attrs": dict(getattr(policy, "attrs", {}) or {}),
            "modes": modes_list,
        }

    snapshot_tms: Dict[str, list[dict[str, Any]]] = {}
    for mname, demands in getattr(traffic_matrix_set, "matrices", {}).items():
        entries: list[dict[str, Any]] = []
        for d in demands:
            entries.append(
                {
                    "source_path": getattr(d, "source_path", ""),
                    "sink_path": getattr(d, "sink_path", ""),
                    "demand": float(getattr(d, "demand", 0.0)),
                    "priority": int(getattr(d, "priority", 0)),
                    "mode": getattr(d, "mode", "pairwise"),
                    "flow_policy_config": getattr(d, "flow_policy_config", None),
                    "attrs": dict(getattr(d, "attrs", {}) or {}),
                }
            )
        snapshot_tms[mname] = entries

    return {
        "seed": seed,
        "failure_policy_set": snapshot_failure_policies,
        "traffic_matrices": snapshot_tms,
    }
