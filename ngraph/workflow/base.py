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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Type, Union

from ngraph.logging import get_logger

if TYPE_CHECKING:
    # Only imported for type-checking; not at runtime, so no circular import occurs.
    from ngraph.scenario import Scenario

logger = get_logger(__name__)

# Registry for workflow step classes
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
        ValueError: If parallelism is a string other than "auto", or an
            integer < 1.
    """
    if isinstance(parallelism, str):
        if parallelism != "auto":
            raise ValueError("parallelism must be an integer or 'auto'")
        return max(1, int(os.cpu_count() or 1))
    if int(parallelism) < 1:
        raise ValueError("parallelism must be >= 1")
    return int(parallelism)


def serialize_monte_carlo_results(raw: Dict[str, Any]) -> tuple[Any, list[dict]]:
    """Convert FailureManager Monte Carlo output into JSON-safe dicts.

    Args:
        raw: Dict with optional "baseline" entry and "results" list, whose
            items expose to_dict() (e.g. FlowIterationResult) or are already
            plain dicts.

    Returns:
        Tuple of (baseline_dict, flow_results): the baseline iteration (or
        None) and the failure iterations, converted via to_dict() when
        available.
    """

    def _to_dict(item: Any) -> Any:
        to_dict = getattr(item, "to_dict", None)
        return to_dict() if callable(to_dict) else item

    baseline = raw.get("baseline")
    baseline_dict = _to_dict(baseline) if baseline is not None else None
    flow_results = [_to_dict(item) for item in raw.get("results", [])]
    return baseline_dict, flow_results


@dataclass
class WorkflowStep(ABC):
    """Base class for all workflow steps.

    Every step is logged with execution timing, supports seeding for
    reproducible random operations, and has its metadata stored in
    scenario.results for analysis.

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
            random operations will be non-deterministic.
    """

    name: str = ""
    seed: Optional[int] = None
    # Internal: seed provenance, one of "explicit-step", "scenario-derived", "none".
    _seed_source: str = ""

    def execute(self, scenario: "Scenario") -> None:
        """Execute the workflow step with logging and metadata storage.

        Wraps `run()` with timing, logging, and metadata storage for the
        analysis registry system.

        Args:
            scenario: The scenario to execute the step on.

        Returns:
            None

        Raises:
            Exception: Re-raises any exception raised by `run()` after logging
                duration and context.
        """
        step_type = self.__class__.__name__
        # Guarantee a stable results namespace even when name is not provided
        step_name = self.name or step_type

        # Determine seed provenance from the seed the step actually uses.
        # run() only ever consults self.seed; a scenario-level seed without a
        # concrete step seed means the step runs unseeded.
        scenario_seed = scenario.seed
        step_seed = self.seed
        if step_seed is not None:
            explicit_source = getattr(self, "_seed_source", None)
            seed_source = (
                explicit_source
                if explicit_source in ("explicit-step", "scenario-derived")
                else "explicit-step"
            )
            active_seed = step_seed
        else:
            seed_source = "none"
            active_seed = None

        # Get execution order from scenario instance (thread-safe)
        execution_order = scenario._execution_counter
        scenario._execution_counter += 1

        # Enter step scope and store workflow metadata
        scenario.results.enter_step(step_name)
        scenario.results.put_step_metadata(
            step_name=step_name,
            step_type=step_type,
            execution_order=execution_order,
            scenario_seed=scenario_seed,
            step_seed=step_seed,
            seed_source=seed_source,
            active_seed=active_seed,
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
            # Persist step duration into step-scoped metadata for downstream analysis
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
            try:
                keys = ", ".join(sorted(scenario.results.get_step(step_name).keys()))
            except Exception as exc:
                logger.debug(
                    "Failed to read results keys for step %s: %s", step_name, exc
                )
                keys = "-"
            logger.debug(
                "Step %s finished: duration=%.3fs, results_keys=%s",
                step_name,
                duration,
                keys or "-",
            )
        except Exception as e:
            end_time = time.time()
            duration = end_time - start_time
            logger.error(
                f"Failed workflow step: {step_name} ({step_type}) "
                f"after {duration:.3f} seconds - {type(e).__name__}: {e}"
            )
            raise
        finally:
            # Always exit step scope
            try:
                scenario.results.exit_step()
            except Exception as exc:
                logger.warning(
                    "Failed to exit step scope cleanly for %s: %s", step_name, exc
                )

    @abstractmethod
    def run(self, scenario: "Scenario") -> None:
        """Execute the workflow step logic.

        Called by `execute()`, which handles logging, timing, and metadata
        storage.

        Args:
            scenario: The scenario to execute the step on.

        Returns:
            None
        """
        pass
