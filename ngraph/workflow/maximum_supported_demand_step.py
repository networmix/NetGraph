"""Report the largest tested feasible physical multiplier and its probe history."""

from dataclasses import dataclass

from ngraph.analysis.msd import MSDQuery, maximum_supported_demand
from ngraph.analysis.preparation import StepNeeds
from ngraph.results import ResolvedDemandSet, StepContext, StepOutput
from ngraph.utils.values import _located_error, flag, own, shared_copy, text
from ngraph.workflow.base import WorkflowStep, _query_error, register_workflow_step


@dataclass
class MaximumSupportedDemand(WorkflowStep):
    """Workflow step: the maximum supported demand of a demand set."""

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
        own(self, demand_set=text(self.demand_set, "MaximumSupportedDemand.demand_set"))
        try:
            query = self.query(ResolvedDemandSet(self.demand_set, (), (), ()))
        except (TypeError, ValueError) as exc:
            message = str(exc)
            if message.startswith("msd"):
                message = "MaximumSupportedDemand" + message[3:]
            else:
                message = "MaximumSupportedDemand." + message
            raise _query_error(exc, message, "msd", "MaximumSupportedDemand") from exc
        # The query checks every field it shares with the step.
        for name in (
            "alpha_start",
            "growth_factor",
            "alpha_min",
            "alpha_max",
            "alpha_tolerance",
            "max_bracket_iters",
            "max_bisect_iters",
            "export_details",
        ):
            object.__setattr__(self, name, getattr(query, name))

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
        from ngraph.dsl.inputs import closed

        label = f"workflow step {name}"
        if "export_details" in arguments:
            raise _located_error(
                ValueError(f"{label}: unknown key export_details; use outputs.details"),
                label + ".export_details",
                arguments["export_details"],
            )
        selected = closed(
            arguments.pop("outputs", {}), ("details",), f"{label}.outputs"
        )
        arguments["export_details"] = flag(
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
