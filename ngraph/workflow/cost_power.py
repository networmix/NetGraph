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
)
from ngraph.utils.values import integer, own_scalars, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step, step_name


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
            f"workflow step {step_name(self)}",
            ("include_disabled", "aggregation_level"),
        )

    def run(self, context: StepContext) -> StepOutput:
        scenario = context.prepared.scenario
        inventory = hardware_inventory(scenario.network, scenario.components_library)
        # level -> path -> [platform_capex, platform_power, optics_capex, optics_power],
        # float sums from 0.0
        levels: Dict[int, Dict[str, List[float]]] = {
            level: {} for level in range(self.aggregation_level + 1)
        }
        for use in inventory.uses:
            if not (self.include_disabled or use.active):
                continue
            parts = [part for part in use.node.split("/") if part]
            offset = 0 if use.link is None else 2
            for level, paths in levels.items():
                bucket = paths.setdefault("/".join(parts[:level]), [0.0] * 4)
                bucket[offset] += use.capex
                bucket[offset + 1] += use.power_watts
        result = CostPowerResult(
            self.include_disabled,
            self.aggregation_level,
            {
                level: tuple(
                    HardwareRow(path, pc, pp, oc, op, pc + oc, pp + op)
                    for path, (pc, pp, oc, op) in mapping.items()
                )
                for level, mapping in levels.items()
            },
        )
        return StepOutput(self, result)
