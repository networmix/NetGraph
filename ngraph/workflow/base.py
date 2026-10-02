"""Base classes for workflow automation.

Defines the workflow step abstraction, registration decorator, and execution
lifecycle. Steps implement `run()` and are executed via `execute()` which
handles timing, logging, and metadata recording. Failures are logged and
re-raised.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, Union

from ngraph.logging import get_logger

if TYPE_CHECKING:
    # Type-checking import only; a runtime import would be circular.
    from ngraph.scenario import Scenario

logger = get_logger(__name__)

# Maps YAML step `type` names to WorkflowStep subclasses
WORKFLOW_STEP_REGISTRY: Dict[str, Type["WorkflowStep"]] = {}


def register_workflow_step(step_type: str):
    """Return a decorator that registers a `WorkflowStep` subclass.

    Args:
        step_type: Registry key used to instantiate steps from configuration.

    Returns:
        A class decorator that adds the class to `WORKFLOW_STEP_REGISTRY`.
    """

    def decorator(cls: Type["WorkflowStep"]) -> Type["WorkflowStep"]:
        WORKFLOW_STEP_REGISTRY[step_type] = cls
        return cls

    return decorator


def validate_unique_step_names(workflow: "list[WorkflowStep]") -> None:
    """Validate that effective step names in a workflow list are unique.

    Effective names follow the same rule used for results storage:
    ``step.name`` or the step class name when no name is set. Duplicate
    effective names would silently overwrite each other's namespace in the
    results store.

    Args:
        workflow: Workflow step list.

    Raises:
        ValueError: If two or more steps share the same effective name.
    """
    counts: Dict[str, int] = {}
    for step in workflow:
        effective = step.name or type(step).__name__
        counts[effective] = counts.get(effective, 0) + 1
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    if duplicates:
        dup_list = ", ".join(f"'{name}'" for name in duplicates)
        raise ValueError(
            f"Duplicate workflow step name(s): {dup_list}. Results are stored "
            "per step name, so duplicates would overwrite each other; set a "
            "unique 'name' on each step."
        )


def resolve_parallelism(parallelism: Union[int, str]) -> int:
    """Validate and resolve a parallelism setting to a concrete worker count.

    Args:
        parallelism: Either a positive integer worker count or "auto" for
            the CPU count.

    Returns:
        Positive integer worker count (minimum 1).

    Raises:
        ValueError: If parallelism is neither "auto" nor an integer >= 1.
    """
    if parallelism == "auto":
        return max(1, os.cpu_count() or 1)
    if isinstance(parallelism, bool) or not isinstance(parallelism, int):
        raise ValueError(
            f"parallelism must be an integer or 'auto', got {parallelism!r}"
        )
    if parallelism < 1:
        raise ValueError("parallelism must be >= 1")
    return parallelism


def serialize_monte_carlo_results(raw: Dict[str, Any]) -> tuple[dict, list[dict]]:
    """Convert FailureManager Monte Carlo output into JSON-safe dicts.

    Args:
        raw: ``run_monte_carlo_analysis`` output whose "baseline" and
            "results" items are FlowIterationResult objects.

    Returns:
        Tuple of (baseline_dict, flow_results).
    """
    return raw["baseline"].to_dict(), [item.to_dict() for item in raw["results"]]


@dataclass
class WorkflowStep(ABC):
    """Base class for all workflow steps.

    `execute()` logs each step with its duration and records step metadata in
    scenario.results. A step seed makes random operations reproducible.

    YAML Configuration:
        ```yaml
        workflow:
          - type: <StepTypeName>
            name: "optional_step_name"  # Optional: Custom name for this step instance
            seed: 42                    # Optional: Seed for reproducible random operations
            # ... step-specific parameters ...
        ```

    Attributes:
        name: Optional custom identifier for this workflow step instance,
            used for logging and result storage. When empty, the class name
            is used instead.
        seed: Optional seed for reproducible random operations. If None,
            random operations are non-deterministic.
    """

    name: str = ""
    seed: Optional[int] = None
    # Provenance of a set seed: "explicit-step", or "scenario-derived" when
    # the workflow parser derived it from the scenario seed.
    _seed_source: str = field(default="explicit-step", init=False, repr=False)

    def execute(self, scenario: "Scenario") -> None:
        """Run the step inside its results namespace and record metadata.

        Wraps `run()`: enters the step's results scope, stores step metadata
        (type, execution order, seeds), logs start and end, and adds
        `duration_sec` to the step metadata on success.

        Args:
            scenario: The scenario to execute the step on.

        Raises:
            Exception: Re-raises any exception raised by `run()` after logging
                duration and context.
        """
        step_type = self.__class__.__name__
        # An unnamed step uses its class name as the results namespace.
        step_name = self.name or step_type

        # Determine seed provenance from the seed the step actually uses.
        # run() only ever consults self.seed; a scenario-level seed without a
        # concrete step seed means the step runs unseeded.
        scenario_seed = scenario.seed
        step_seed = self.seed
        seed_source = self._seed_source if step_seed is not None else "none"

        execution_order = scenario._execution_counter
        scenario._execution_counter += 1

        scenario.results.enter_step(step_name)
        scenario.results.put_step_metadata(
            step_name=step_name,
            step_type=step_type,
            execution_order=execution_order,
            scenario_seed=scenario_seed,
            step_seed=step_seed,
            seed_source=seed_source,
        )

        if self.seed is not None:
            logger.debug(
                "Executing step: %s (%s) with seed=%s",
                step_name,
                step_type,
                str(self.seed),
            )
        logger.info(f"Starting workflow step: {step_name} ({step_type})")
        start_time = time.time()

        try:
            self.run(scenario)
            end_time = time.time()
            duration = end_time - start_time
            # Merge duration_sec into the step's 'metadata' entry (created
            # if run() stored none).
            existing_md = scenario.results.get("metadata", {})
            if not isinstance(existing_md, dict):
                raise TypeError("Results metadata must be a dict")
            updated_md = dict(existing_md)
            updated_md["duration_sec"] = float(duration)
            scenario.results.put("metadata", updated_md)
            logger.info(
                f"Completed workflow step: {step_name} ({step_type}) "
                f"in {duration:.3f} seconds"
            )
            logger.debug(
                "Step %s finished: duration=%.3fs, results_keys=%s",
                step_name,
                duration,
                ", ".join(sorted(scenario.results.get_step(step_name))) or "-",
            )
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(
                f"Failed workflow step: {step_name} ({step_type}) "
                f"after {duration:.3f} seconds: {type(e).__name__}: {e}"
            )
            raise
        finally:
            scenario.results.exit_step()

    @abstractmethod
    def run(self, scenario: "Scenario") -> None:
        """Execute the workflow step logic.

        Called by `execute()`, which handles logging, timing, and metadata
        storage.

        Args:
            scenario: The scenario to execute the step on.
        """
        pass
