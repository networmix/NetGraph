"""Generic results store for workflow steps and their metadata.

`Results` organizes outputs by workflow step name and records
`WorkflowStepMetadata` for execution context. Storage is strictly
step-scoped: steps must write two keys under their namespace:

- ``metadata``: step-level metadata (dict)
- ``data``: step-specific payload (dict)

Export with :meth:`Results.to_dict`, which returns a JSON-safe structure
with shape ``{workflow, steps, scenario}``. During export, objects with a
``to_dict()`` method are converted, dictionary keys are coerced to strings,
tuples are emitted as lists, and only JSON primitives are produced.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class WorkflowStepMetadata:
    """Metadata for a workflow step execution.

    Attributes:
        step_type: The workflow step class name (e.g., 'CapacityEnvelopeAnalysis').
        step_name: The instance name of the step.
        execution_order: Order in which this step was executed (0-based).
        scenario_seed: Scenario-level seed provided in the YAML (if any).
        step_seed: Seed assigned to this step (explicit or scenario-derived).
        seed_source: Source for the step seed. One of:
            - "scenario-derived": seed was derived from scenario.seed
            - "explicit-step": seed was explicitly provided for the step
            - "none": no seed provided/active for this step
        active_seed: The effective base seed used by the step, if any. For steps
            that use Monte Carlo execution, per-iteration seeds are derived from
            active_seed (e.g., active_seed + iteration_index).
    """

    step_type: str
    step_name: str
    execution_order: int
    scenario_seed: Optional[int] = None
    step_seed: Optional[int] = None
    seed_source: str = "none"
    active_seed: Optional[int] = None


@dataclass
class Results:
    """Step-scoped results container with deterministic export shape.

    Structure:
      - workflow: step metadata registry
      - steps: per-step results with enforced keys {"metadata", "data"}
      - scenario: optional scenario snapshot set once at load time
    """

    # Per-step data store: _store[step_name]["metadata"|"data"] = dict
    _store: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Metadata registry: _metadata[step_name] = WorkflowStepMetadata
    _metadata: Dict[str, WorkflowStepMetadata] = field(default_factory=dict)

    # Active step scope during WorkflowStep.execute()
    _active_step: Optional[str] = None

    # Scenario snapshot
    _scenario: Dict[str, Any] = field(default_factory=dict)

    # ---- Scope management -------------------------------------------------
    def enter_step(self, step_name: str) -> None:
        """Enter step scope. Subsequent put/get are scoped to this step."""
        self._active_step = step_name
        if step_name not in self._store:
            self._store[step_name] = {}

    def exit_step(self) -> None:
        """Exit step scope."""
        self._active_step = None

    # ---- Step-scoped accessors -------------------------------------------
    def put(self, key: str, value: Any) -> None:
        """Store a value in the active step under an allowed key.

        Allowed keys are strictly "metadata" and "data". Both are expected to be
        dictionaries at export time.
        """
        if self._active_step is None:
            raise RuntimeError("Results.put() called without active step scope")
        if key not in {"metadata", "data"}:
            raise ValueError("Results.put() only allows keys 'metadata' and 'data'")
        if self._active_step not in self._store:
            self._store[self._active_step] = {}
        self._store[self._active_step][key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the active step scope."""
        if self._active_step is None:
            raise RuntimeError("Results.get() called without active step scope")
        return self._store.get(self._active_step, {}).get(key, default)

    def get_step(self, step_name: str) -> Dict[str, Any]:
        """Return the raw dict for a given step name (for cross-step reads)."""
        return self._store.get(step_name, {})

    def put_step_metadata(
        self,
        step_name: str,
        step_type: str,
        execution_order: int,
        *,
        scenario_seed: Optional[int] = None,
        step_seed: Optional[int] = None,
        seed_source: str = "none",
        active_seed: Optional[int] = None,
    ) -> None:
        """Store metadata for a workflow step.

        Args:
            step_name: The step instance name.
            step_type: The workflow step class name.
            execution_order: Order in which this step was executed (0-based).
            scenario_seed: Scenario-level seed from YAML, if any.
            step_seed: Seed attached to this step (explicit or derived), if any.
            seed_source: Source of step seed ("scenario-derived", "explicit-step", or "none").
            active_seed: Effective base seed used by the step, if any.
        """
        self._metadata[step_name] = WorkflowStepMetadata(
            step_type=step_type,
            step_name=step_name,
            execution_order=execution_order,
            scenario_seed=scenario_seed,
            step_seed=step_seed,
            seed_source=seed_source,
            active_seed=active_seed,
        )

    def get_step_metadata(self, step_name: str) -> Optional[WorkflowStepMetadata]:
        """Get metadata for a workflow step.

        Args:
            step_name: The step name.

        Returns:
            WorkflowStepMetadata if found, None otherwise.
        """
        return self._metadata.get(step_name)

    def get_all_step_metadata(self) -> Dict[str, WorkflowStepMetadata]:
        """Get metadata for all workflow steps.

        Returns:
            Dictionary mapping step names to their metadata.
        """
        return self._metadata.copy()

    def get_steps_by_execution_order(self) -> list[str]:
        """Get step names ordered by their execution order.

        Returns:
            List of step names in execution order.
        """
        return sorted(
            self._metadata.keys(), key=lambda step: self._metadata[step].execution_order
        )

    def set_scenario_snapshot(self, snapshot: Dict[str, Any]) -> None:
        """Attach a normalized scenario snapshot for export."""
        self._scenario = snapshot

    def to_dict(self) -> Dict[str, Any]:
        """Return exported results with shape: {workflow, steps, scenario}."""
        # Workflow metadata
        workflow: Dict[str, Any] = {
            step_name: {
                "step_type": md.step_type,
                "step_name": md.step_name,
                "execution_order": md.execution_order,
                "scenario_seed": md.scenario_seed,
                "step_seed": md.step_seed,
                "seed_source": md.seed_source,
                "active_seed": md.active_seed,
            }
            for step_name, md in self._metadata.items()
        }

        # Steps data with validation and to_dict() conversion
        steps: Dict[str, Dict[str, Any]] = {}
        for step_name, data in self._store.items():
            # Enforce explicit keys
            if not set(data.keys()).issubset({"metadata", "data"}):
                invalid = ", ".join(sorted(set(data.keys()) - {"metadata", "data"}))
                raise ValueError(
                    f"Step '{step_name}' contains invalid result keys: {invalid}"
                )
            metadata_part = data.get("metadata", {})
            data_part = data.get("data", {})
            if metadata_part is None:
                metadata_part = {}
            if data_part is None:
                data_part = {}
            if not isinstance(metadata_part, dict) or not isinstance(data_part, dict):
                raise ValueError(
                    f"Step '{step_name}' must store dicts for 'metadata' and 'data'"
                )

            def deep_convert(v: Any) -> Any:
                # Convert nested structures; apply to_dict to any object that supports it
                if hasattr(v, "to_dict") and callable(v.to_dict):
                    return v.to_dict()
                if isinstance(v, dict):
                    return {str(k): deep_convert(val) for k, val in v.items()}
                if isinstance(v, (list, tuple)):
                    return [deep_convert(x) for x in v]
                return v

            steps[step_name] = {
                "metadata": deep_convert(metadata_part),
                "data": deep_convert(data_part),
            }

        # Compose final
        out: Dict[str, Any] = {
            "workflow": workflow,
            "steps": steps,
        }
        if self._scenario:
            out["scenario"] = self._scenario
        return out
