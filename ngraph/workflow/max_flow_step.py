"""Native capacity questions over one shared sequence of failure cases."""

from dataclasses import dataclass, field
from functools import partial
from typing import Literal

import netgraph_core as ngc

from ngraph.analysis.capacity import CapacityQuery, capacity
from ngraph.analysis.demands import materialize_config, pooled, selected_pairs
from ngraph.analysis.failures import FailureRequest, Workers, checked_workers
from ngraph.analysis.precision import question_inputs
from ngraph.analysis.preparation import PreparedScenario, StepNeeds
from ngraph.model.demand import FlowPolicyPreset, PinnedRoutes, _ParsedModel
from ngraph.model.selectors import Selector
from ngraph.results import StepContext, StepOutput
from ngraph.utils.values import (
    flag,
    integer,
    optional_text,
    own,
    physical,
    shared_copy,
)
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    step_name,
    workflow_failures,
)


@dataclass
class MaxFlow(WorkflowStep):
    """Workflow step: the capacity between two node sets, under one model."""

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
        if not isinstance(self.source, Selector) or not isinstance(
            self.target, Selector
        ):
            raise TypeError(
                f"MaxFlow endpoints: expected Selectors, got {(self.source, self.target)!r}"
            )
        if not isinstance(self.mode, str) or self.mode not in ("combine", "pairwise"):
            raise ValueError(
                f"MaxFlow.mode: expected combine or pairwise, got {self.mode!r}"
            )
        if self.preset is not None and self.model is not None:
            raise ValueError("MaxFlow: preset and model are exclusive")
        if self.preset is not None and not isinstance(self.preset, FlowPolicyPreset):
            raise TypeError(
                f"MaxFlow.preset: expected FlowPolicyPreset, got {self.preset!r}"
            )
        if self.model is not None and not isinstance(
            self.model, (ngc.FlowPolicyConfig, PinnedRoutes, _ParsedModel)
        ):
            raise TypeError(
                "MaxFlow.model: expected a declared model or native FlowPolicyConfig, "
                f"got {self.model!r}"
            )
        for name in ("offer", "design_demand"):
            if getattr(self, name) is not None:
                object.__setattr__(
                    self, name, physical(getattr(self, name), f"MaxFlow.{name}")
                )
        request = FailureRequest(
            None,
            integer(self.iterations, "MaxFlow.iterations", minimum=0),
            self.seed,
            flag(self.failure_trace, "MaxFlow.failure_trace"),
        )
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError(
                f"MaxFlow.outputs: expected native OutputOptions, got {self.outputs!r}"
            )
        own(
            self,
            mode=str.__str__(self.mode),
            failure_policy=optional_text(self.failure_policy, "MaxFlow.failure_policy"),
            iterations=request.iterations,
            workers=checked_workers(self.workers),
            failure_trace=request.failure_trace,
            export_cost_distribution=flag(
                self.export_cost_distribution, "MaxFlow.export_cost_distribution"
            ),
            export_details=flag(self.export_details, "MaxFlow.export_details"),
        )

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        from ngraph.dsl.inputs import flow_outputs, policy
        from ngraph.model.selectors import normalize_selector
        from ngraph.utils.yaml_utils import declared

        for endpoint in ("source", "target"):
            if endpoint not in arguments:
                raise ValueError(f"workflow step {name}: {endpoint} is required")
            arguments[endpoint] = declared(
                f"workflow step {name}.{endpoint}",
                partial(normalize_selector, arguments[endpoint], "workflow"),
                "selector",
            )
        for optional in ("preset", "model"):
            if arguments.get(optional) is None:
                arguments.pop(optional, None)
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
            f"step {step_name(self)}",
        )
        if isinstance(self.declaration, PinnedRoutes) and len(pairs) != 1:
            raise ValueError(
                f"step {step_name(self)}: pinned model requires one endpoint pair"
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
