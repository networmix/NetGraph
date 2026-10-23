"""Ordered native traffic placement with typed earlier-MSD scale selection."""

from dataclasses import dataclass, field

import netgraph_core as ngc

from ngraph.analysis.failures import FailureRequest, Workers, resolve_workers
from ngraph.analysis.placement import PlacementQuery, place
from ngraph.analysis.preparation import StepNeeds
from ngraph.results import MSDAnalysis, StepContext, StepOutput
from ngraph.utils.values import own_scalars, physical, shared_copy
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    workflow_failures,
)


@dataclass
class TrafficMatrixPlacement(WorkflowStep):
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

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.export_details, bool):
            raise TypeError("export_details: expected bool")
        if not isinstance(self.demand_set, str) or not self.demand_set:
            raise ValueError(
                "TrafficMatrixPlacement.demand_set: expected nonempty name"
            )
        if self.alpha is not None:
            object.__setattr__(
                self,
                "alpha",
                physical(self.alpha, "TrafficMatrixPlacement.alpha", positive=True),
            )
            if self.alpha_from_step is not None:
                raise ValueError(
                    "TrafficMatrixPlacement: alpha and alpha_from_step are exclusive"
                )
        if self.alpha_from_step is not None and (
            not isinstance(self.alpha_from_step, str) or not self.alpha_from_step
        ):
            raise ValueError(
                "TrafficMatrixPlacement.alpha_from_step: expected nonempty name"
            )
        FailureRequest(None, self.iterations, self.seed, self.failure_trace)
        resolve_workers(self.workers)
        if not isinstance(self.outputs, ngc.OutputOptions) or not isinstance(
            self.export_cost_distribution, bool
        ):
            raise TypeError("TrafficMatrixPlacement: invalid outputs")
        own_scalars(
            self,
            f"workflow step {self.name}",
            (
                "demand_set",
                "failure_policy",
                "iterations",
                "workers",
                "failure_trace",
                "export_cost_distribution",
                "export_details",
                "alpha_from_step",
            ),
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
            ),
        )
        return StepOutput(value.query, value)


register_workflow_step("TrafficMatrixPlacement")(TrafficMatrixPlacement)
