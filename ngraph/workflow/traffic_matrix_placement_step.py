"""TrafficMatrixPlacement workflow step.

Runs Monte Carlo demand placement using a named demand set and produces
unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) always runs first as a separate reference; `iterations`
counts failure scenarios only.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: TrafficMatrixPlacement
        name: "tm_analysis"
        demand_set: "default"
        failure_policy: "single_link"    # Optional: failure policy name
        iterations: 100                  # Number of failure scenarios
        parallelism: 4                   # Worker threads (or "auto")
        alpha: 1.0                       # Demand volume multiplier
        include_flow_details: true       # Include cost distribution per flow
    ```
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.analysis.failure_manager import FailureManager
from ngraph.logging import get_logger
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    resolve_parallelism,
    serialize_monte_carlo_results,
)

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class TrafficMatrixPlacement(WorkflowStep):
    """Monte Carlo demand placement using a named demand set.

    Baseline (no failures) always runs first and is returned in a separate field.
    The flow_results list holds unique failure patterns (deduplicated); each result
    carries an occurrence_count of how many iterations matched that pattern.

    Attributes:
        demand_set: Name of the demand set to analyze. Required; an empty
            value raises ValueError.
        failure_policy: Failure policy name in scenario.failure_policy_set.
            If None, no failure policy is applied.
        iterations: Number of failure iterations to run; must be >= 0.
        parallelism: Worker thread count, or "auto" for the CPU count.
        placement_rounds: Deprecated; accepted for backward compatibility but
            has no effect (placement optimization is handled by the core engine).
        seed: Optional seed for reproducibility.
        store_failure_patterns: Record the failure trace on each result.
            Iterations are deduplicated, so a trace describes the first
            iteration of its pattern, not every matching iteration.
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        alpha: Numeric scale for demands in the set; must be > 0.0. Ignored
            when alpha_from_step is set.
        alpha_from_step: Optional producer step name to read alpha from; it
            must run before this step.
        alpha_from_field: Dotted field path in producer step (default: "data.alpha_star").
    """

    demand_set: str = ""
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int | str = "auto"
    placement_rounds: int | str = "auto"
    seed: int | None = None
    store_failure_patterns: bool = False
    include_flow_details: bool = False
    include_used_edges: bool = False
    alpha: float = 1.0
    alpha_from_step: str | None = None
    alpha_from_field: str = "data.alpha_star"

    def __post_init__(self) -> None:
        if self.placement_rounds != "auto":
            logger.warning(
                "TrafficMatrixPlacement 'placement_rounds' is deprecated and has "
                "no effect; placement optimization is handled by the core engine."
            )
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        resolve_parallelism(self.parallelism)  # validate at construction
        if not (float(self.alpha) > 0.0):
            raise ValueError("alpha must be > 0.0")

    def run(self, scenario: "Scenario") -> None:
        if not self.demand_set:
            raise ValueError("'demand_set' is required for TrafficMatrixPlacement")

        t0 = time.perf_counter()
        logger.info("Starting TrafficMatrixPlacement: name=%s", self.name)
        logger.debug(
            "TrafficMatrixPlacement params: demand_set=%s failure_iters=%d "
            "parallelism=%s failure_policy=%s alpha=%s",
            self.demand_set,
            self.iterations,
            self.parallelism,
            self.failure_policy,
            self.alpha,
        )

        # Extract and serialize demand set
        try:
            td_list = scenario.demand_set.get_set(self.demand_set)
        except KeyError as exc:
            raise ValueError(
                f"Demand set '{self.demand_set}' not found in scenario."
            ) from exc

        # Resolve alpha
        effective_alpha = self._resolve_alpha(scenario)
        alpha_src = getattr(self, "_alpha_source", None) or "explicit"
        logger.info(
            "Using alpha: value=%.6g source=%s",
            float(effective_alpha),
            str(alpha_src),
        )

        # base_demands: canonical serialized form for output (unscaled).
        # demands_config: analysis wire format (scaled volume, raw preset).
        base_demands: list[dict[str, Any]] = [td.to_dict() for td in td_list]
        demands_config: list[dict[str, Any]] = [
            {
                **td.to_dict(),
                "volume": float(td.volume) * float(effective_alpha),
                "flow_policy": td.flow_policy,
            }
            for td in td_list
        ]

        # Run via FailureManager
        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = resolve_parallelism(self.parallelism)

        raw = fm.run_demand_placement_monte_carlo(
            demands_config=demands_config,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
            include_flow_details=self.include_flow_details,
            include_used_edges=self.include_used_edges,
        )

        logger.debug(
            "TrafficMatrixPlacement MC done: failure_iters=%d unique_patterns=%d",
            raw.get("metadata", {}).get("iterations", 0),
            raw.get("metadata", {}).get("unique_patterns", 0),
        )

        # Store outputs
        scenario.results.put("metadata", raw.get("metadata", {}))

        baseline_dict, flow_results = serialize_monte_carlo_results(raw)

        alpha_value = float(effective_alpha)
        alpha_source_value = getattr(self, "_alpha_source", "explicit")

        scenario.results.put(
            "data",
            {
                "baseline": baseline_dict,
                "flow_results": flow_results,
                "context": {
                    "demand_set": self.demand_set,
                    "include_flow_details": self.include_flow_details,
                    "include_used_edges": self.include_used_edges,
                    "base_demands": base_demands,
                    "alpha": alpha_value,
                    "alpha_source": alpha_source_value,
                },
            },
        )

        metadata = raw.get("metadata", {})
        logger.info(
            "TrafficMatrixPlacement completed: name=%s alpha=%.6g failure_iters=%d "
            "unique_patterns=%d workers=%d duration=%.3fs",
            self.name,
            alpha_value,
            metadata.get("iterations", self.iterations),
            metadata.get("unique_patterns", 0),
            metadata.get("parallelism", effective_parallelism),
            time.perf_counter() - t0,
        )

    def _resolve_alpha(self, scenario: "Scenario") -> float:
        if self.alpha_from_step:
            step = scenario.results.get_step(self.alpha_from_step)
            # Results.get_step returns {} for unknown or not-yet-run steps.
            if not step:
                raise ValueError(
                    f"alpha_from_step '{self.alpha_from_step}' has no results - "
                    "check the step name and that it runs before this step"
                )
            parts = [p for p in str(self.alpha_from_field).split(".") if p]
            cursor: Any = step
            for part in parts:
                if not isinstance(cursor, dict) or part not in cursor:
                    raise ValueError(
                        f"alpha_from_field '{self.alpha_from_field}' missing in step '{self.alpha_from_step}'"
                    )
                cursor = cursor[part]
            try:
                value = float(cursor)
            except Exception as exc:
                raise ValueError(
                    f"alpha_from_step '{self.alpha_from_step}' field '{self.alpha_from_field}' is not a number"
                ) from exc
            if not (value > 0.0):
                raise ValueError("alpha_from_step produced non-positive alpha")
            self._alpha_source = self.alpha_from_step
            return value
        return float(self.alpha)


register_workflow_step("TrafficMatrixPlacement")(TrafficMatrixPlacement)
