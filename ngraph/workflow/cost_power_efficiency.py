"""Workflow step to compute cost/power efficiency metrics and optional HW inventory.

Computes total capex and power for the selected network inventory (all or only
active), and normalizes by a provided delivered-bandwidth figure (e.g., BAC at
availability target).

Optionally collects node and/or link hardware entries to provide an inventory
view of hardware usage. Each entry includes hardware capacity, allocated
capacity, typical and maximum power, and a normalized hardware mapping.

This step does not compute BAC itself; it expects callers to pass the delivered
bandwidth value explicitly or to point to a prior step result.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: CostPowerEfficiency
        name: "cost_power_efficiency"   # Optional custom name
        delivered_bandwidth_gbps: 10000  # Optional explicit denominator (float)
        delivered_bandwidth_key: "delivered_bandwidth_gbps"  # Lookup key in results
        include_disabled: true           # Whether to include disabled nodes/links
        collect_node_hw_entries: true    # Optional: collect per-node HW entries
        collect_link_hw_entries: false   # Optional: collect per-link HW entries
    ```

Results stored in `scenario.results`:
    - total_capex: Sum of component capex (float)
    - total_power_watts: Sum of component power (float)
    - delivered_bandwidth_gbps: Denominator used for normalization (float)
    - dollars_per_gbit: Normalized capex (float, inf if denominator <= 0)
    - watts_per_gbit: Normalized power (float, inf if denominator <= 0)
    - node_hw_entries: Optional list of node-level hardware dicts with keys:
        node, hardware {component, count}, hw_capacity, allocated_capacity,
        power_watts, power_watts_max
    - link_hw_entries: Optional list of link-level hardware dicts with keys:
        link_id, source, target, capacity,
        hardware {source {component, count, exclusive}, target {component, count, exclusive}},
        hw_capacity, power_watts, power_watts_max
    - hardware_bom_total: Aggregated hardware BOM for the whole network (Dict[str, float])
    - hardware_bom_by_path: Mapping of hierarchy path -> BOM dict for each subtree
      (root is stored under the empty string key "")
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ngraph.components import (
    ComponentsLibrary,
    resolve_link_end_components,
    resolve_node_hardware,
    totals_with_multiplier,
)
from ngraph.explorer import NetworkExplorer
from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

logger = get_logger(__name__)


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
        collect_node_hw_entries: If True, store per-node hardware entries with
            hardware mapping, capacity, allocated capacity, and power metrics.
        collect_link_hw_entries: If True, store per-link hardware entries with
            per-end hardware mapping, capacity, and power metrics.
    """

    delivered_bandwidth_gbps: Optional[float] = None
    delivered_bandwidth_key: str = "delivered_bandwidth_gbps"
    include_disabled: bool = True
    collect_node_hw_entries: bool = False
    collect_link_hw_entries: bool = False

    def run(self, scenario: Any) -> None:
        """Compute totals and normalized efficiency metrics.

        Args:
            scenario: Scenario providing the network, components library, and results store.

        Returns:
            None
        """
        t0 = time.perf_counter()
        logger.info(
            "Starting cost/power efficiency analysis: name=%s include_disabled=%s "
            "node_hw=%s link_hw=%s denom_key=%s denom_explicit=%s",
            self.name,
            str(self.include_disabled),
            str(self.collect_node_hw_entries),
            str(self.collect_link_hw_entries),
            self.delivered_bandwidth_key,
            str(self.delivered_bandwidth_gbps is not None),
        )

        # Build explorer FIRST to trigger all validations before collecting metrics
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
            # Prefer namespaced lookup under this step's namespace
            ns = self.name
            try:
                val = scenario.results.get(ns, self.delivered_bandwidth_key)
            except Exception:
                val = None

            if val is None:
                # Global lookup across all prior steps: choose value from the most recent step
                try:
                    all_vals = scenario.results.get_all(self.delivered_bandwidth_key)
                    if all_vals:
                        # Order by execution order descending and pick first available
                        meta = scenario.results.get_all_step_metadata()
                        ordered_steps = sorted(
                            all_vals.keys(),
                            key=lambda s: meta.get(s).execution_order
                            if meta.get(s)
                            else -1,
                            reverse=True,
                        )
                        for step_name in ordered_steps:
                            val = all_vals.get(step_name)
                            if val is not None:
                                break
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

        step_name = self.name
        scenario.results.put(step_name, "total_capex", total_capex)
        scenario.results.put(step_name, "total_power_watts", total_power_watts)
        scenario.results.put(step_name, "delivered_bandwidth_gbps", denom)
        scenario.results.put(step_name, "dollars_per_gbit", dollars_per_gbit)
        scenario.results.put(step_name, "watts_per_gbit", watts_per_gbit)

        # Hardware BOMs (total and per-path), matching include_disabled view
        bom_total = explorer.get_bom(include_disabled=self.include_disabled)
        bom_by_path = explorer.get_bom_map(
            include_disabled=self.include_disabled, include_root=True, root_label=""
        )
        scenario.results.put(step_name, "hardware_bom_total", bom_total)
        scenario.results.put(step_name, "hardware_bom_by_path", bom_by_path)

        # Optional hardware inventory
        node_entries: List[Dict[str, Any]] = []
        link_entries: List[Dict[str, Any]] = []
        if self.collect_node_hw_entries or self.collect_link_hw_entries:
            node_entries, link_entries = self._collect_hw_entries(
                scenario.components_library, scenario
            )
            if self.collect_node_hw_entries:
                scenario.results.put(step_name, "node_hw_entries", node_entries)
            if self.collect_link_hw_entries:
                scenario.results.put(step_name, "link_hw_entries", link_entries)

        # INFO-level outcome summary for quick visual inspection
        try:
            duration_sec = time.perf_counter() - t0
            bom_count = len(bom_total) if isinstance(bom_total, dict) else 0
            # Top-N components by count
            top_n = 3
            top_items = []
            try:
                top_items = sorted(
                    bom_total.items(), key=lambda kv: (-float(kv[1]), kv[0])
                )[:top_n]
            except Exception:
                top_items = []
            top_str = (
                ", ".join(f"{k}:{float(v):.3f}" for k, v in top_items)
                if top_items
                else "-"
            )
            logger.info(
                (
                    "CostPowerEfficiency summary: name=%s include_disabled=%s "
                    "capex=%.3f power_watts=%.3f delivered_gbps=%.6g "
                    "dollars_per_gbit=%.6g watts_per_gbit=%.6g "
                    "bom_components=%d top=[%s] node_hw_entries=%d link_hw_entries=%d "
                    "duration=%.3fs"
                ),
                self.name,
                str(self.include_disabled),
                total_capex,
                total_power_watts,
                denom,
                dollars_per_gbit,
                watts_per_gbit,
                bom_count,
                top_str,
                len(node_entries) if self.collect_node_hw_entries else 0,
                len(link_entries) if self.collect_link_hw_entries else 0,
                duration_sec,
            )
        except Exception:
            # Logging must not raise
            pass

        logger.info("Cost/power efficiency analysis completed: %s", self.name)

    def _collect_hw_entries(
        self, library: ComponentsLibrary, scenario: Any
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Collect node/link hardware entries.

        This respects ``include_disabled`` both for which items are included and
        for how node allocated capacity is computed:
        - If ``include_disabled`` is True, consider all nodes/links and sum all
          link capacities to both endpoints for allocation.
        - If False, include only enabled nodes and only links that are enabled
          with both endpoints enabled; allocate capacity from those links only.

        Args:
            library: Components library for resolving hardware totals.
            scenario: Scenario providing the network.

        Returns:
            Tuple (node_entries, link_entries), where each entry is a dict with
            the keys listed in the module docstring results section.
        """
        network = scenario.network

        def _node_enabled(name: str) -> bool:
            nd = network.nodes[name]
            return not (
                bool(getattr(nd, "disabled", False)) or bool(nd.attrs.get("disabled"))
            )

        def _link_enabled(link_obj: Any) -> bool:
            return not (
                bool(getattr(link_obj, "disabled", False))
                or bool(link_obj.attrs.get("disabled"))
            )

        # Build link list according to include_disabled semantics
        if self.include_disabled:
            links_for_sum = list(network.links.values())
        else:
            enabled_nodes = {name for name in network.nodes if _node_enabled(name)}
            links_for_sum = [
                lk
                for lk in network.links.values()
                if _link_enabled(lk)
                and lk.source in enabled_nodes
                and lk.target in enabled_nodes
            ]

        # Precompute per-node allocated capacity (sum of attached link capacities)
        allocated_by_node: Dict[str, float] = {name: 0.0 for name in network.nodes}
        for lk in links_for_sum:
            cap_val = float(lk.capacity)
            allocated_by_node[lk.source] = (
                allocated_by_node.get(lk.source, 0.0) + cap_val
            )
            allocated_by_node[lk.target] = (
                allocated_by_node.get(lk.target, 0.0) + cap_val
            )

        # Node entries
        node_entries: List[Dict[str, Any]] = []
        if self.collect_node_hw_entries:
            if self.include_disabled:
                node_iter = list(network.nodes.values())
            else:
                node_iter = [
                    nd for nd in network.nodes.values() if _node_enabled(nd.name)
                ]

            for nd in node_iter:
                comp, hw_count = resolve_node_hardware(nd.attrs, library)
                if comp is not None:
                    hw_capacity = float(comp.total_capacity() * hw_count)
                    power_watts = float(comp.total_power() * hw_count)
                    power_watts_max = float(comp.total_power_max() * hw_count)
                else:
                    hw_capacity = 0.0
                    power_watts = 0.0
                    power_watts_max = 0.0

                entry = {
                    "node": nd.name,
                    "hardware": {
                        "component": comp.name if comp is not None else None,
                        "count": float(hw_count),
                    },
                    "hw_capacity": hw_capacity,
                    "allocated_capacity": float(allocated_by_node.get(nd.name, 0.0)),
                    "power_watts": power_watts,
                    "power_watts_max": power_watts_max,
                }
                node_entries.append(entry)

        # Link entries
        link_entries: List[Dict[str, Any]] = []
        if self.collect_link_hw_entries:
            links_iter: List[Any]
            if self.include_disabled:
                links_iter = list(network.links.values())
            else:
                # Reuse the same selection as links_for_sum to ensure endpoint-enabled check
                links_iter = links_for_sum

            # Precompute which nodes have chassis/hardware; optics are ignored when absent
            node_has_hw: Dict[str, bool] = {}
            for nd in network.nodes.values():
                nd_comp, _nd_cnt = resolve_node_hardware(nd.attrs, library)
                node_has_hw[nd.name] = nd_comp is not None

            for lk in links_iter:
                (src_end, dst_end, per_end) = resolve_link_end_components(
                    lk.attrs, library
                )

                src_comp, src_cnt, _ = src_end
                dst_comp, dst_cnt, _ = dst_end

                def _totals_with_max(c, n) -> tuple[float, float, float, float]:
                    if c is None:
                        return 0.0, 0.0, 0.0, 0.0
                    capex, power, cap = totals_with_multiplier(c, n)
                    power_max = float(c.total_power_max() * n)
                    return capex, power, cap, power_max

                # Compute endpoints; ignore optics if the endpoint node has no hardware
                if src_comp is not None and node_has_hw.get(lk.source, False):
                    _, src_power, src_cap, src_power_max = _totals_with_max(
                        src_comp, src_cnt
                    )
                else:
                    src_power, src_cap, src_power_max = 0.0, 0.0, 0.0

                if dst_comp is not None and node_has_hw.get(lk.target, False):
                    _, dst_power, dst_cap, dst_power_max = _totals_with_max(
                        dst_comp, dst_cnt
                    )
                else:
                    dst_power, dst_cap, dst_power_max = 0.0, 0.0, 0.0

                # Aggregate per-link
                power_watts = float(src_power + dst_power)
                power_watts_max = float(src_power_max + dst_power_max)
                # Capacity for validation/reporting: min of specified ends when both present
                if src_cap > 0.0 and dst_cap > 0.0:
                    hw_capacity = float(min(src_cap, dst_cap))
                else:
                    hw_capacity = 0.0

                entry = {
                    "link_id": lk.id,
                    "source": lk.source,
                    "target": lk.target,
                    "capacity": float(lk.capacity),
                    "hardware": {
                        "source": {
                            "component": src_comp.name
                            if src_comp is not None
                            and node_has_hw.get(lk.source, False)
                            else None,
                            "count": float(src_cnt),
                        },
                        "target": {
                            "component": dst_comp.name
                            if dst_comp is not None
                            and node_has_hw.get(lk.target, False)
                            else None,
                            "count": float(dst_cnt),
                        },
                    },
                    "hw_capacity": hw_capacity,
                    "power_watts": power_watts,
                    "power_watts_max": power_watts_max,
                }
                link_entries.append(entry)

        return node_entries, link_entries


register_workflow_step("CostPowerEfficiency")(CostPowerEfficiency)
