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
    """Build a concise dictionary snapshot of the scenario state.

    Args:
        seed: Scenario-level seed for reproducibility, or None if unseeded.
        failure_policy_set: FailurePolicySet containing named failure policies.
        demand_set: DemandSet containing named demand collections.

    Returns:
        Dict containing: seed, failures (policy snapshots), demands (demand snapshots).
    """
    snapshot_demands: Dict[str, list[dict[str, Any]]] = {
        sname: [d.to_dict() for d in demands]
        for sname, demands in demand_set.sets.items()
    }

    return {
        "seed": seed,
        # Scenario YAML format (rule conditions nested under "match").
        "failures": failure_policy_set.to_dict(),
        "demands": snapshot_demands,
    }
