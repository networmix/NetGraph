"""Scenario snapshot helpers.

Build a concise dictionary snapshot of failure policies and demand sets for
export into results without keeping heavy domain objects.
"""

from __future__ import annotations

from typing import Any, Dict


def build_scenario_snapshot(
    *,
    seed: int | None,
    failure_policy_set,
    demand_set,
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
                        "scope": getattr(rule, "scope", "node"),
                        "logic": getattr(rule, "logic", "or"),
                        "mode": getattr(rule, "mode", "all"),
                        "probability": float(getattr(rule, "probability", 1.0)),
                        "count": int(getattr(rule, "count", 1)),
                        "path": getattr(rule, "path", None),
                        "conditions": [
                            {
                                "attr": c.attr,
                                "op": c.op,
                                "value": c.value,
                            }
                            for c in getattr(rule, "conditions", []) or []
                        ],
                    }
                )
            modes_list.append(mode_dict)
        snapshot_failure_policies[name] = {
            "attrs": dict(getattr(policy, "attrs", {}) or {}),
            "expand_groups": getattr(policy, "expand_groups", False),
            "expand_children": getattr(policy, "expand_children", False),
            "modes": modes_list,
        }

    snapshot_demands: Dict[str, list[dict[str, Any]]] = {}
    for sname, demands in getattr(demand_set, "sets", {}).items():
        entries: list[dict[str, Any]] = []
        for d in demands:
            entries.append(
                {
                    "id": getattr(d, "id", None),
                    "source": getattr(d, "source", ""),
                    "target": getattr(d, "target", ""),
                    "volume": float(getattr(d, "volume", 0.0)),
                    "priority": int(getattr(d, "priority", 0)),
                    "mode": getattr(d, "mode", "pairwise"),
                    "group_mode": getattr(d, "group_mode", "flatten"),
                    "flow_policy": getattr(d, "flow_policy", None),
                    "attrs": dict(getattr(d, "attrs", {}) or {}),
                }
            )
        snapshot_demands[sname] = entries

    return {
        "seed": seed,
        "failures": snapshot_failure_policies,
        "demands": snapshot_demands,
    }
