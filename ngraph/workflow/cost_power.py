"""Platform/optic cost and power at each named hierarchy level."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Dict, List

from ngraph.hardware import hardware_inventory
from ngraph.results import (
    CostPowerResult,
    HardwareRow,
    StepContext,
    StepOutput,
    _CostPowerLevels,
)
from ngraph.utils.values import flag, integer, own, physical, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step


@register_workflow_step("CostPower")
@dataclass
class CostPower(WorkflowStep):
    """Workflow step: hardware cost and power, aggregated by hierarchy level."""

    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    # The recorded question is the step itself: this kind and its own fields.
    question_kind: ClassVar[str] = "cost_power"
    include_disabled: bool = False
    aggregation_level: int = 2

    def __post_init__(self) -> None:
        super().__post_init__()
        own(
            self,
            include_disabled=flag(self.include_disabled, "CostPower.include_disabled"),
            aggregation_level=integer(
                self.aggregation_level, "CostPower.aggregation_level", minimum=0
            ),
        )

    def run(self, context: StepContext) -> StepOutput:
        scenario = context.prepared.scenario
        inventory = hardware_inventory(scenario.network, scenario.components_library)
        # level -> path -> [platform_capex, platform_power, optics_capex, optics_power],
        # float sums from 0.0
        deepest = max(
            (len([p for p in name.split("/") if p]) for name in scenario.network.nodes),
            default=0,
        )
        levels: Dict[int, Dict[str, List[float]]] = {
            level: {} for level in range(min(self.aggregation_level, deepest) + 1)
        }
        for use in inventory.uses:
            if not (self.include_disabled or use.active):
                continue
            parts = [part for part in use.node.split("/") if part]
            offset = 0 if use.link is None else 2
            for level, paths in levels.items():
                bucket = paths.setdefault("/".join(parts[:level]), [0.0] * 4)
                label = f"hardware path {'/'.join(parts[:level]) or '<root>'} node {use.node}"
                bucket[offset] = physical(bucket[offset] + use.capex, f"{label}.capex")
                bucket[offset + 1] = physical(
                    bucket[offset + 1] + use.power_watts, f"{label}.power_watts"
                )
        result = CostPowerResult(
            self.include_disabled,
            self.aggregation_level,
            _CostPowerLevels(
                tuple(
                    tuple(
                        HardwareRow(
                            path,
                            pc,
                            pp,
                            oc,
                            op,
                            physical(
                                pc + oc, f"hardware path {path or '<root>'}.capex_total"
                            ),
                            physical(
                                pp + op,
                                f"hardware path {path or '<root>'}.power_total_watts",
                            ),
                        )
                        for path, (pc, pp, oc, op) in sorted(mapping.items())
                    )
                    for mapping in levels.values()
                ),
                self.aggregation_level,
            ),
        )

        return StepOutput(self, result)
