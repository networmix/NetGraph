"""Ordered native traffic placement with typed earlier-MSD scale selection."""

from dataclasses import dataclass, field
from typing import Literal

import netgraph_core as ngc

from ngraph.analysis.failures import FailureRequest, Workers, checked_workers
from ngraph.analysis.placement import PlacementQuery, place, state_names
from ngraph.analysis.preparation import StepNeeds
from ngraph.results import MSDAnalysis, StateName, StepContext, StepOutput
from ngraph.utils.values import (
    _located_error,
    _shown,
    flag,
    integer,
    optional_text,
    own,
    physical,
    shared_copy,
    text,
)
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    step_name,
    workflow_failures,
)


@dataclass
class TrafficMatrixPlacement(WorkflowStep):
    """Workflow step: place a demand set, with optional failures, failure states and
    interaction.
    """

    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    demand_set: str = ""
    failure_policy: str | None = None
    iterations: int = 1
    workers: Workers = "auto"
    failure_trace: bool = False
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_cost_distribution: bool = False
    export_details: bool = False
    alpha: float | None = None
    alpha_from_step: str | None = None
    failure_states: tuple[StateName, ...] = ("converged",)
    interaction: Literal["ordered", "simultaneous"] = "ordered"

    def __post_init__(self):
        super().__post_init__()
        object.__setattr__(
            self,
            "failure_states",
            state_names(
                self.failure_states,
                f"workflow.{step_name(self)}.failure_states",
            ),
        )
        if not isinstance(self.interaction, str) or self.interaction not in (
            "ordered",
            "simultaneous",
        ):
            raise _located_error(
                ValueError(
                    f"workflow.{step_name(self)}.interaction: "
                    f"expected ordered or simultaneous, got {_shown(self.interaction)}"
                ),
                f"workflow.{step_name(self)}.interaction",
                self.interaction,
            )
        if self.alpha is not None:
            raw_alpha = self.alpha
            object.__setattr__(
                self,
                "alpha",
                physical(self.alpha, "TrafficMatrixPlacement.alpha", positive=True),
            )
            if self.alpha_from_step is not None:
                raise ValueError(
                    f"TrafficMatrixPlacement: alpha and alpha_from_step are exclusive, got {_shown((raw_alpha, self.alpha_from_step))}"
                )
        request = FailureRequest(
            None,
            integer(self.iterations, "TrafficMatrixPlacement.iterations", minimum=0),
            self.seed,
            flag(self.failure_trace, "TrafficMatrixPlacement.failure_trace"),
        )
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError(
                f"TrafficMatrixPlacement.outputs: expected native OutputOptions, got {_shown(self.outputs)}"
            )
        own(
            self,
            demand_set=text(self.demand_set, "TrafficMatrixPlacement.demand_set"),
            failure_policy=optional_text(
                self.failure_policy, "TrafficMatrixPlacement.failure_policy"
            ),
            iterations=request.iterations,
            workers=checked_workers(self.workers),
            failure_trace=request.failure_trace,
            export_cost_distribution=flag(
                self.export_cost_distribution,
                "TrafficMatrixPlacement.export_cost_distribution",
            ),
            export_details=flag(
                self.export_details, "TrafficMatrixPlacement.export_details"
            ),
            alpha_from_step=optional_text(
                self.alpha_from_step, "TrafficMatrixPlacement.alpha_from_step"
            ),
            interaction=str.__str__(self.interaction),
        )

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        from ngraph.dsl.inputs import flow_outputs

        return flow_outputs(arguments, name)

    def needs(self) -> StepNeeds:
        return StepNeeds(
            numerical=True,
            demand_set=self.demand_set,
            failure_policy=self.failure_policy,
            alpha_from_step=self.alpha_from_step,
            states=self.failure_states,
            interaction=self.interaction,
            alpha=None if self.alpha_from_step is not None else (self.alpha or 1.0),
        )

    def run(self, context: StepContext) -> StepOutput:
        alpha = 1.0 if self.alpha is None else self.alpha
        if self.alpha_from_step is not None:
            earlier = context.prior_results.get(self.alpha_from_step)
            if earlier is None or not isinstance(earlier.result, MSDAnalysis):
                raise ValueError(
                    f"alpha_from_step {self.alpha_from_step!r}: expected an earlier MSD result"
                )
            if earlier.result.alpha_feasible is None:
                raise ValueError(
                    f"alpha_from_step {self.alpha_from_step!r}: no tested feasible alpha"
                )
            alpha = earlier.result.alpha_feasible.value
        failures = workflow_failures(
            context, self.failure_policy, self.iterations, self.failure_trace
        )
        value = place(
            context.prepared,
            PlacementQuery(
                context.prepared.demand_sets[self.demand_set],
                alpha,
                failures,
                self.workers,
                self.outputs,
                self.export_cost_distribution,
                self.export_details,
                self.alpha_from_step,
                self.failure_states,
                self.interaction,
            ),
        )
        return StepOutput(value.query, value)


register_workflow_step("TrafficMatrixPlacement")(TrafficMatrixPlacement)
