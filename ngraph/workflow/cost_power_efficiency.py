"""Workflow step to compute cost/power efficiency metrics.

Computes total capex and power for the active network inventory, and normalizes
by a provided delivered-bandwidth figure (e.g., BAC at availability target).

This step does not compute BAC itself; it expects callers to pass the delivered
bandwidth value explicitly or to point to a prior step result.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: CostPowerEfficiency
        name: "cost_power_efficiency"   # Optional custom name
        delivered_bandwidth_gbps: 10000  # Optional explicit denominator (float)
        delivered_bandwidth_key: "delivered_bandwidth_gbps"  # Lookup key in results
        include_disabled: true           # Whether to include disabled nodes/links in totals
    ```

Results stored in `scenario.results` under the step name:
    - total_capex: Sum of component capex (float)
    - total_power_watts: Sum of component power (float)
    - delivered_bandwidth_gbps: Denominator used for normalization (float)
    - dollars_per_gbit: Normalized capex (float, inf if denominator <= 0)
    - watts_per_gbit: Normalized power (float, inf if denominator <= 0)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ngraph.explorer import NetworkExplorer
from ngraph.workflow.base import WorkflowStep, register_workflow_step


@dataclass
class CostPowerEfficiency(WorkflowStep):
    """Compute $/Gbit and W/Gbit given delivered bandwidth.

    Attributes:
        delivered_bandwidth_gbps: Delivered bandwidth in Gbit/s used as denominator.
            If not provided, the step will attempt to read a value from
            ``scenario.results`` using ``delivered_bandwidth_key``.
        delivered_bandwidth_key: Results key to read if ``delivered_bandwidth_gbps``
            is None. The key is looked up under this step's own namespace first; if
            not present, the key is treated as a global results key.
        include_disabled: If False, only enabled nodes/links are counted for totals.
            Default ``True`` aggregates regardless of disabled flags.
    """

    delivered_bandwidth_gbps: Optional[float] = None
    delivered_bandwidth_key: str = "delivered_bandwidth_gbps"
    include_disabled: bool = True

    def run(self, scenario: Any) -> None:
        """Compute totals and normalized efficiency metrics.

        Args:
            scenario: Scenario providing the network, components library, and results store.

        Returns:
            None
        """
        explorer = NetworkExplorer.explore_network(
            scenario.network, components_library=scenario.components_library
        )

        # Select stats view using getattr to avoid optional-member type warnings
        attr_name = "stats" if self.include_disabled else "active_stats"
        stats = getattr(explorer.root_node, attr_name, None)
        if stats is None:
            # Fallback to any available stats attribute
            stats = getattr(explorer.root_node, "stats", None) or getattr(
                explorer.root_node, "active_stats", None
            )
        if stats is None:
            raise AttributeError(
                "Explorer root node has no stats/active_stats available"
            )

        total_capex = float(stats.total_capex)
        total_power_watts = float(stats.total_power)

        # Resolve denominator
        denom = self.delivered_bandwidth_gbps
        if denom is None:
            # Prefer namespaced lookup
            ns = self.name or self.__class__.__name__
            try:
                val = scenario.results.get(ns, self.delivered_bandwidth_key)
            except Exception:
                val = None
            if val is None:
                # Global lookup for convenience
                try:
                    val = scenario.results.get(self.delivered_bandwidth_key)
                except Exception:
                    val = None
            denom = float(val) if val is not None else 0.0

        # Compute normalized metrics; guard zero denominator
        if denom <= 0.0:
            dollars_per_gbit = float("inf")
            watts_per_gbit = float("inf")
        else:
            dollars_per_gbit = total_capex / denom
            watts_per_gbit = total_power_watts / denom

        step_name = self.name or self.__class__.__name__
        scenario.results.put(step_name, "total_capex", total_capex)
        scenario.results.put(step_name, "total_power_watts", total_power_watts)
        scenario.results.put(step_name, "delivered_bandwidth_gbps", denom)
        scenario.results.put(step_name, "dollars_per_gbit", dollars_per_gbit)
        scenario.results.put(step_name, "watts_per_gbit", watts_per_gbit)


register_workflow_step("CostPowerEfficiency")(CostPowerEfficiency)
