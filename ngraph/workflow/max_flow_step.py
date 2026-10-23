"""Native capacity questions over one shared sequence of failure cases."""

from dataclasses import dataclass, field
from typing import Literal

import netgraph_core as ngc

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.demands import materialize_config, pooled, selected_pairs
from ngraph.analysis.failures import FailureRequest, Workers, resolve_workers
from ngraph.analysis.precision import question_inputs
from ngraph.analysis.preparation import PreparedScenario, StepNeeds
from ngraph.model.demand import FlowPolicyPreset, PinnedRoutes
from ngraph.model.selectors import Selector
from ngraph.results import StepContext, StepOutput
from ngraph.utils.values import own_scalars, physical, shared_copy
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    workflow_failures,
)


@dataclass
class MaxFlow(WorkflowStep):
    """Evaluate independent endpoint capacities with explicit native routing."""

    _immutable = True
    __copy__ = __deepcopy__ = shared_copy
    source: Selector = field(default_factory=lambda: Selector(".*"))
    target: Selector = field(default_factory=lambda: Selector(".*"))
    mode: Literal["combine", "pairwise"] = "combine"
    preset: FlowPolicyPreset | None = None
    model: object = None
    offer: float | None = None
    design_demand: float | None = None
    failure_policy: str | None = None
    iterations: int = 1
    workers: Workers = "auto"
    failure_trace: bool = False
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_cost_distribution: bool = False
    export_details: bool = False

    def __post_init__(self):
        super().__post_init__()
        if not isinstance(self.export_details, bool):
            raise TypeError("export_details: expected bool")
        if not isinstance(self.source, Selector) or not isinstance(
            self.target, Selector
        ):
            raise TypeError("MaxFlow endpoints: expected Selectors")
        if self.mode not in ("combine", "pairwise"):
            raise ValueError("MaxFlow.mode: expected combine or pairwise")
        if self.preset is not None and self.model is not None:
            raise ValueError("MaxFlow: preset and model are exclusive")
        if self.preset is not None and not isinstance(self.preset, FlowPolicyPreset):
            raise TypeError("MaxFlow.preset: expected FlowPolicyPreset")
        for name in ("offer", "design_demand"):
            if getattr(self, name) is not None:
                object.__setattr__(
                    self, name, physical(getattr(self, name), f"MaxFlow.{name}")
                )
        FailureRequest(None, self.iterations, self.seed, self.failure_trace)
        resolve_workers(self.workers)
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError("MaxFlow.outputs: expected native OutputOptions")
        if not isinstance(self.export_cost_distribution, bool):
            raise TypeError("MaxFlow.export_cost_distribution: expected bool")
        own_scalars(
            self,
            f"workflow step {self.name}",
            (
                "mode",
                "failure_policy",
                "iterations",
                "workers",
                "failure_trace",
                "export_cost_distribution",
                "export_details",
            ),
        )

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        from ngraph.dsl.inputs import flow_outputs, policy
        from ngraph.model.selectors import normalize_selector

        for endpoint in ("source", "target"):
            if endpoint not in arguments:
                raise ValueError(f"workflow step {name}: {endpoint} is required")
            arguments[endpoint] = normalize_selector(arguments[endpoint], "workflow")
        if "preset" in arguments or "model" in arguments:
            declaration = policy(arguments, f"workflow step {name}")
            arguments.pop("preset", None)
            arguments.pop("model", None)
            key = "preset" if isinstance(declaration, FlowPolicyPreset) else "model"
            arguments[key] = declaration
        return flow_outputs(arguments, name)

    @property
    def declaration(self):
        return (
            self.model
            if self.model is not None
            else self.preset or FlowPolicyPreset.TE_MAXFLOW_UNLIM
        )

    def needs(self) -> StepNeeds:
        return StepNeeds(
            numerical=True,
            failure_policy=self.failure_policy,
            capacity=self.query,
            inputs=question_inputs(self.offer, self.design_demand, self.declaration),
            pool_endpoints=(self.source, self.target)
            if pooled(self.mode, self.declaration)
            else None,
        )

    def query(self, prepared: PreparedScenario, failures=None) -> CapacityQuery:
        pairs = selected_pairs(
            prepared.scenario.network,
            self.source,
            self.target,
            self.mode,
            f"step {self.name}",
        )
        if isinstance(self.declaration, PinnedRoutes) and len(pairs) != 1:
            raise ValueError(
                f"step {self.name}: pinned model requires one endpoint pair"
            )
        config = materialize_config(
            prepared.topology, prepared._named, pairs[0], self.declaration
        )
        return CapacityQuery(
            self.source,
            self.target,
            config,
            self.mode,
            self.offer,
            self.design_demand,
            failures,
            self.workers,
            self.outputs,
            self.export_cost_distribution,
            self.export_details,
            self.declaration,
        )

    def run(self, context: StepContext) -> StepOutput:
        failures = workflow_failures(
            context, self.failure_policy, self.iterations, self.failure_trace
        )
        value = capacity(context.prepared, self.query(context.prepared, failures))
        return StepOutput(value.query, value)


register_workflow_step("MaxFlow")(MaxFlow)
