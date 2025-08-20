"""CostPower workflow step: collect capex and power by hierarchy level.

This step aggregates capex and power from the network hardware inventory without
performing any normalization or reporting. It separates contributions into two
categories:

- platform_*: node hardware (e.g., chassis, linecards) resolved from node attrs
- optics_*: per-end link hardware (e.g., optics) resolved from link attrs

Aggregation is computed at hierarchy levels 0..N where level 0 is the global
root (path ""), and higher levels correspond to prefixes of node names split by
"/". For example, for node "dc1/plane1/leaf/leaf-1":
    - level 1 path is "dc1"
    - level 2 path is "dc1/plane1"
    - etc.

Disabled handling:
- When include_disabled is False, only enabled nodes and links are considered.
- Optics are counted only when the endpoint node has platform hardware.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: CostPower
        name: "cost_power"           # Optional custom name
        include_disabled: false       # Default: only enabled nodes/links
        aggregation_level: 2          # Produce levels: 0, 1, 2
    ```

Results stored in `scenario.results` under this step namespace:
    data:
      context:
        include_disabled: bool
        aggregation_level: int
      levels:
        "0":
          - path: ""
            platform_capex: float
            platform_power_watts: float
            optics_capex: float
            optics_power_watts: float
            capex_total: float
            power_total_watts: float
        "1": [ ... ]
        "2": [ ... ]
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

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
class CostPower(WorkflowStep):
    """Collect platform and optics capex/power by aggregation level.

    Attributes:
        include_disabled: If True, include disabled nodes and links.
        aggregation_level: Inclusive depth for aggregation. 0=root only.
    """

    include_disabled: bool = False
    aggregation_level: int = 2

    def __post_init__(self) -> None:
        try:
            self.aggregation_level = int(self.aggregation_level)
        except Exception as exc:
            raise ValueError(f"aggregation_level must be int: {exc}") from exc
        if self.aggregation_level < 0:
            raise ValueError("aggregation_level must be >= 0")

    def run(self, scenario: Any) -> None:
        """Aggregate capex and power by hierarchy levels 0..N.

        Args:
            scenario: Scenario with network, components_library, and results store.
        """
        t0 = time.perf_counter()
        logger.info(
            "Starting CostPower: name=%s include_disabled=%s levels=0..%d",
            self.name or self.__class__.__name__,
            str(self.include_disabled),
            int(self.aggregation_level),
        )

        network = scenario.network
        library: ComponentsLibrary = scenario.components_library

        explorer = NetworkExplorer.explore_network(network, components_library=library)

        # Helper: enabled checks honor both flags and attrs for consistency
        def node_enabled(nd: Any) -> bool:
            return not (
                bool(getattr(nd, "disabled", False)) or bool(nd.attrs.get("disabled"))
            )

        def link_enabled(lk: Any) -> bool:
            return not (
                bool(getattr(lk, "disabled", False)) or bool(lk.attrs.get("disabled"))
            )

        # Precompute endpoint eligibility for optics (node must have platform HW)
        node_has_hw: Dict[str, bool] = {}
        for nd in network.nodes.values():
            comp, _ = resolve_node_hardware(nd.attrs, library)
            node_has_hw[nd.name] = comp is not None

        # Aggregation maps: level -> path -> [platform_capex, platform_power, optics_capex, optics_power]
        levels: Dict[int, Dict[str, List[float]]] = {
            lvl: {} for lvl in range(0, self.aggregation_level + 1)
        }

        def path_prefix(full_path: str, level: int) -> str:
            if level <= 0:
                return ""
            parts = [p for p in full_path.split("/") if p]
            return "/".join(parts[:level])

        def add_values(
            path: str,
            platform_capex: float,
            platform_power: float,
            optics_capex: float,
            optics_power: float,
        ) -> None:
            for lvl in range(0, self.aggregation_level + 1):
                key = path_prefix(path, lvl)
                bucket = levels[lvl].setdefault(key, [0.0, 0.0, 0.0, 0.0])
                bucket[0] += platform_capex
                bucket[1] += platform_power
                bucket[2] += optics_capex
                bucket[3] += optics_power

        # --- Platform aggregation (nodes) ---
        for nd in network.nodes.values():
            if not self.include_disabled and not node_enabled(nd):
                continue
            comp, count = resolve_node_hardware(nd.attrs, library)
            if comp is None:
                continue
            capex, power, _ = totals_with_multiplier(comp, count)
            tree_node = explorer._node_map.get(nd.name)
            if tree_node is None:
                continue
            full_path = explorer._compute_full_path(tree_node)
            add_values(full_path, float(capex), float(power), 0.0, 0.0)

        # --- Optics aggregation (per-end link hardware) ---
        for lk in network.links.values():
            if not self.include_disabled:
                if not link_enabled(lk):
                    continue
                # Both endpoints must be enabled when aggregating active view
                if not node_enabled(network.nodes[lk.source]):
                    continue
                if not node_enabled(network.nodes[lk.target]):
                    continue

            (src_end, dst_end, per_end) = resolve_link_end_components(lk.attrs, library)
            if not per_end:
                continue

            # Source endpoint
            src_comp, src_cnt, _src_excl = src_end
            if src_comp is not None and node_has_hw.get(lk.source, False):
                capex, power, _ = totals_with_multiplier(src_comp, src_cnt)
                src_tree = explorer._node_map.get(lk.source)
                if src_tree is not None:
                    src_path = explorer._compute_full_path(src_tree)
                    add_values(src_path, 0.0, 0.0, float(capex), float(power))

            # Destination endpoint
            dst_comp, dst_cnt, _dst_excl = dst_end
            if dst_comp is not None and node_has_hw.get(lk.target, False):
                capex, power, _ = totals_with_multiplier(dst_comp, dst_cnt)
                dst_tree = explorer._node_map.get(lk.target)
                if dst_tree is not None:
                    dst_path = explorer._compute_full_path(dst_tree)
                    add_values(dst_path, 0.0, 0.0, float(capex), float(power))

        # Build payload
        levels_payload: Dict[int, List[Dict[str, Any]]] = {}
        for lvl, mapping in levels.items():
            out_list: List[Dict[str, Any]] = []
            for path, vals in sorted(mapping.items(), key=lambda kv: kv[0]):
                platform_capex, platform_power, optics_capex, optics_power = vals
                out_list.append(
                    {
                        "path": path,
                        "platform_capex": float(platform_capex),
                        "platform_power_watts": float(platform_power),
                        "optics_capex": float(optics_capex),
                        "optics_power_watts": float(optics_power),
                        "capex_total": float(platform_capex + optics_capex),
                        "power_total_watts": float(platform_power + optics_power),
                    }
                )
            levels_payload[lvl] = out_list

        # Store results
        scenario.results.put("metadata", {})
        scenario.results.put(
            "data",
            {
                "context": {
                    "include_disabled": bool(self.include_disabled),
                    "aggregation_level": int(self.aggregation_level),
                },
                "levels": levels_payload,
            },
        )

        # Log root summary
        root_items = levels_payload.get(0, [])
        root = root_items[0] if root_items else {}
        logger.info(
            "CostPower complete: name=%s capex=%.3f power=%.3f platform_capex=%.3f optics_capex=%.3f duration=%.3fs",
            self.name or self.__class__.__name__,
            float(root.get("capex_total", 0.0)),
            float(root.get("power_total_watts", 0.0)),
            float(root.get("platform_capex", 0.0)),
            float(root.get("optics_capex", 0.0)),
            time.perf_counter() - t0,
        )


register_workflow_step("CostPower")(CostPower)
