"""Platform/optic cost and power at each named hierarchy level."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, ClassVar, Dict, List

from ngraph.model.components import (
    ComponentsLibrary,
    resolve_link_end_components,
    resolve_node_hardware,
    totals_with_multiplier,
)
from ngraph.results import (
    CostPowerResult,
    HardwareRow,
    StepContext,
    StepOutput,
)
from ngraph.utils.values import integer, own_scalars, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step


@register_workflow_step("CostPower")
@dataclass
class CostPower(WorkflowStep):
    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    # The recorded question is the step itself: this kind and its own fields.
    question_kind: ClassVar[str] = "cost_power"
    include_disabled: bool = False
    aggregation_level: int = 2

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.include_disabled, bool):
            raise ValueError("CostPower.include_disabled: expected bool")
        integer(self.aggregation_level, "CostPower.aggregation_level", minimum=0)
        own_scalars(
            self,
            f"workflow step {self.name}",
            ("include_disabled", "aggregation_level"),
        )

    def run(self, context: StepContext) -> StepOutput:
        scenario = context.prepared.scenario
        network = scenario.network
        library: ComponentsLibrary = scenario.components_library

        def node_enabled(nd: Any) -> bool:
            return not bool(nd.disabled)

        def link_enabled(lk: Any) -> bool:
            return not bool(lk.disabled)

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
            add_values(nd.name, float(capex), float(power), 0.0, 0.0)

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

            src_end, dst_end = resolve_link_end_components(lk.attrs, library)

            src_comp, src_cnt, _src_excl = src_end
            if src_comp is not None and node_has_hw.get(lk.source, False):
                capex, power, _ = totals_with_multiplier(src_comp, src_cnt)
                add_values(lk.source, 0.0, 0.0, float(capex), float(power))

            dst_comp, dst_cnt, _dst_excl = dst_end
            if dst_comp is not None and node_has_hw.get(lk.target, False):
                capex, power, _ = totals_with_multiplier(dst_comp, dst_cnt)
                add_values(lk.target, 0.0, 0.0, float(capex), float(power))

        result = CostPowerResult(
            self.include_disabled,
            self.aggregation_level,
            MappingProxyType(
                {
                    level: tuple(
                        HardwareRow(
                            path,
                            float(values[0]),
                            float(values[1]),
                            float(values[2]),
                            float(values[3]),
                            float(values[0] + values[2]),
                            float(values[1] + values[3]),
                        )
                        for path, values in mapping.items()
                    )
                    for level, mapping in levels.items()
                }
            ),
        )
        return StepOutput(self, result)
