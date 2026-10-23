"""Typed workflow execution and explicit extension registration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import KW_ONLY, FrozenInstanceError, dataclass, field
from importlib import import_module
from typing import TYPE_CHECKING, Literal, TypeVar

from ngraph.analysis.failures import FailureRequest
from ngraph.export import is_question, owned_step_result
from ngraph.logging import get_logger
from ngraph.results import StepContext, StepOutput, StepResult
from ngraph.utils.values import frozen_attrs, own_scalars

if TYPE_CHECKING:
    from ngraph.analysis.preparation import StepNeeds

logger = get_logger(__name__)
SeedSource = Literal["explicit-step", "scenario-derived", "none"]
WORKFLOW_STEP_REGISTRY: dict[str, type[WorkflowStep]] = {}
StepT = TypeVar("StepT", bound="WorkflowStep")
# Built-in step types register when their module first loads.
BUILTIN_STEP_MODULES = {
    "BuildGraph": "ngraph.workflow.build_graph",
    "CostPower": "ngraph.workflow.cost_power",
    "MaxFlow": "ngraph.workflow.max_flow_step",
    "MaximumSupportedDemand": "ngraph.workflow.maximum_supported_demand_step",
    "NetworkStats": "ngraph.workflow.network_stats",
    "TrafficMatrixPlacement": "ngraph.workflow.traffic_matrix_placement_step",
}


def step_type(name: str) -> type[WorkflowStep] | None:
    """Return the registered step class for a YAML type name, if any."""
    if name not in WORKFLOW_STEP_REGISTRY and name in BUILTIN_STEP_MODULES:
        import_module(BUILTIN_STEP_MODULES[name])
    return WORKFLOW_STEP_REGISTRY.get(name)


def register_workflow_step(name: str) -> Callable[[type[StepT]], type[StepT]]:
    """Register one concrete step class for a nonempty YAML type name."""
    if not isinstance(name, str) or not name:
        raise ValueError("workflow registration name: expected nonempty string")

    def register(step_type: type[StepT]) -> type[StepT]:
        if not issubclass(step_type, WorkflowStep):
            raise TypeError("workflow registration requires a WorkflowStep subclass")
        builtin = BUILTIN_STEP_MODULES.get(name)
        if name in WORKFLOW_STEP_REGISTRY or (
            builtin is not None and step_type.__module__ != builtin
        ):
            raise ValueError(f"workflow step type already registered: {name}")
        WORKFLOW_STEP_REGISTRY[name] = step_type
        return step_type

    return register


def validate_unique_step_names(workflow: Sequence[WorkflowStep]) -> None:
    seen = set()
    for step in workflow:
        if not isinstance(step, WorkflowStep):
            raise TypeError("workflow: expected WorkflowStep values")
        name = step.name or type(step).__name__
        if name in seen:
            raise ValueError(f"Duplicate workflow step name: {name}")
        seen.add(name)


def workflow_failures(context, policy_name, iterations, failure_trace):
    """Supply the step's named policy and effective seed to the one sampler."""
    policies = context.prepared.scenario.failure_policies
    if policy_name is not None and policy_name not in policies:
        raise ValueError(
            f"step {context.step_name}: unknown failure policy {policy_name!r}"
        )
    return FailureRequest(
        policies.get(policy_name),
        iterations,
        context.seed,
        failure_trace,
        policy_name,
        "scenario" if context.seed_source == "scenario-derived" else "step",
    )


def _question(value):
    """Check a step's recorded question; custom JSON parameters are frozen."""
    if not is_question(value):
        raise TypeError(f"workflow question: unsupported type {type(value).__name__}")
    if isinstance(value, Mapping) and not isinstance(value, WorkflowStep):
        return frozen_attrs(value, "custom question parameters")
    return value


@dataclass
class WorkflowStep(ABC):
    """Base of every workflow step.

    Built-in steps are immutable once constructed (``dataclasses.replace``
    makes an edited copy). A custom step's own fields stay its own; ``prepare``
    records its name and seed, so later edits of those do not reach a
    prepared scenario.
    """

    name: str = ""
    seed: int | None = None
    _: KW_ONLY
    # Its YAML declaration, kept by dataclasses.replace: the refusal label and
    # the seed the scenario derived for it (its seed is derived while equal).
    yaml_label: str | None = field(default=None, compare=False, repr=False)
    derived_seed: int | None = field(default=None, compare=False, repr=False)
    _immutable = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str):
            raise ValueError("workflow step name: expected string")
        for name in ("seed", "derived_seed"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise ValueError(f"workflow step {name}: expected integer or None")
        if self.yaml_label is not None and (
            not isinstance(self.yaml_label, str) or not self.yaml_label
        ):
            raise ValueError("workflow step yaml_label: expected a nonempty string")
        own_scalars(
            self, "workflow step", ("name", "seed", "yaml_label", "derived_seed")
        )
        if self._immutable:
            object.__setattr__(self, "_constructed", True)

    def __setattr__(self, name, value):
        if "_constructed" in self.__dict__:
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        object.__setattr__(self, name, value)

    def __delattr__(self, name):
        if "_constructed" in self.__dict__:
            raise FrozenInstanceError(f"cannot delete field {name!r}")
        object.__delattr__(self, name)

    def execute(self, context: StepContext) -> StepResult:
        """Run once, validate/own its boundary, and publish one immutable result."""
        logger.info(
            "Starting workflow step: %s (%s)", context.step_name, type(self).__name__
        )
        output = self.run(context)
        if not isinstance(output, StepOutput):
            raise TypeError(f"step {context.step_name}: run must return StepOutput")
        question = _question(output.question)
        result = owned_step_result(output.result)
        completed = StepResult(
            context.step_name,
            type(self).__name__,
            context.execution_order,
            context.prepared.scenario.seed,
            context.seed,
            context.seed_source,
            result,
            question,
        )
        logger.info(
            "Completed workflow step: %s (%s)", context.step_name, type(self).__name__
        )
        return completed

    @classmethod
    def yaml_arguments(cls, arguments: dict, name: str) -> dict:
        """Turn this step type's YAML keys into constructor arguments."""
        return arguments

    @property
    def seed_source(self) -> SeedSource:
        """Where this step's seed comes from."""
        if self.seed is None:
            return "none"
        if self.seed == self.derived_seed:
            return "scenario-derived"
        return "explicit-step"

    def needs(self) -> StepNeeds | None:
        """What preparation must bind for this step; None asks for nothing."""
        return None

    @abstractmethod
    def run(self, context: StepContext) -> StepOutput:
        """Return this step's typed question and result without publishing state."""
        raise NotImplementedError
