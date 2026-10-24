"""Report the largest tested feasible physical multiplier and its probe history."""

from dataclasses import dataclass

from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.preparation import StepNeeds
from ngraph.results import ResolvedDemandSet, StepContext, StepOutput
from ngraph.utils.values import own_scalars, shared_copy
from ngraph.workflow.base import WorkflowStep, register_workflow_step, step_name


@dataclass
class MaximumSupportedDemand(WorkflowStep):
    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    demand_set: str = ""
    alpha_start: float = 1.0
    growth_factor: float = 2.0
    alpha_min: float = 1e-6
    alpha_max: float = 1e9
    alpha_tolerance: float = 0.01
    max_bracket_iters: int = 32
    max_bisect_iters: int = 32
    export_details: bool = False

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.demand_set, str) or not self.demand_set:
            raise ValueError(
                "MaximumSupportedDemand.demand_set: expected nonempty name"
            )
        query = self.query(ResolvedDemandSet(self.demand_set, (), (), ()))
        for name in (
            "alpha_start",
            "growth_factor",
            "alpha_min",
            "alpha_max",
            "alpha_tolerance",
        ):
            object.__setattr__(self, name, getattr(query, name))
        own_scalars(
            self,
            f"workflow step {step_name(self)}",
            ("demand_set", "max_bracket_iters", "max_bisect_iters", "export_details"),
        )

    def query(self, demands):
        return MSDQuery(
            demands,
            self.alpha_start,
            self.growth_factor,
            self.alpha_min,
            self.alpha_max,
            self.alpha_tolerance,
            self.max_bracket_iters,
            self.max_bisect_iters,
            export_details=self.export_details,
        )

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        from ngraph.dsl.inputs import boolean, closed

        label = f"workflow step {name}"
        if "export_details" in arguments:
            raise ValueError(
                f"{label}: unknown key export_details; use outputs.details"
            )
        selected = closed(
            arguments.pop("outputs", {}), ("details",), f"{label}.outputs"
        )
        arguments["export_details"] = boolean(
            selected.get("details", False), f"{label}.outputs.details"
        )
        return arguments

    def needs(self) -> StepNeeds:
        return StepNeeds(
            numerical=True, demand_set=self.demand_set, provides_alpha=True
        )

    def run(self, context: StepContext) -> StepOutput:
        value = maximum_supported_demand(
            context.prepared, self.query(context.prepared.demand_sets[self.demand_set])
        )
        return StepOutput(value.query, value)


register_workflow_step("MaximumSupportedDemand")(MaximumSupportedDemand)
