"""TrafficMatrixPlacement workflow step.

Runs Monte Carlo demand placement using a named demand set and produces
unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) is always run first as a separate reference. The `iterations`
parameter specifies how many failure scenarios to run.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.analysis.failure_manager import FailureManager
from ngraph.logging import get_logger
from ngraph.results.flow import FlowIterationResult
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    resolve_parallelism,
)

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class TrafficMatrixPlacement(WorkflowStep):
    """Monte Carlo demand placement using a named demand set.

    Baseline (no failures) is always run first as a separate reference. Results are
    returned with baseline in a separate field. The flow_results list contains unique
    failure patterns (deduplicated); each result has occurrence_count indicating how
    many iterations matched that pattern.

    Attributes:
        demand_set: Name of the demand set to analyze.
        failure_policy: Optional failure policy name in scenario.failure_policy_set.
        iterations: Number of failure iterations to run.
        parallelism: Number of parallel worker processes.
        placement_rounds: Placement optimization rounds (int or "auto").
        seed: Optional seed for reproducibility.
        store_failure_patterns: Whether to store failure pattern results.
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        alpha: Numeric scale for demands in the set.
        alpha_from_step: Optional producer step name to read alpha from.
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
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        if isinstance(self.parallelism, str):
            if self.parallelism != "auto":
                raise ValueError("parallelism must be an integer or 'auto'")
        else:
            if self.parallelism < 1:
                raise ValueError("parallelism must be >= 1")
        if not (float(self.alpha) > 0.0):
            raise ValueError("alpha must be > 0.0")

    def run(self, scenario: "Scenario") -> None:
        if not self.demand_set:
            raise ValueError("'demand_set' is required for TrafficMatrixPlacement")

        t0 = time.perf_counter()
        logger.info("Starting TrafficMatrixPlacement: name=%s", self.name)
        logger.debug(
            "TrafficMatrixPlacement params: demand_set=%s failure_iters=%d "
            "parallelism=%s placement_rounds=%s failure_policy=%s alpha=%s",
            self.demand_set,
            self.iterations,
            self.parallelism,
            self.placement_rounds,
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

        from ngraph.model.flow.policy_config import serialize_policy_preset

        # Resolve alpha
        effective_alpha = self._resolve_alpha(scenario)
        alpha_src = getattr(self, "_alpha_source", None) or "explicit"
        logger.info(
            "Using alpha: value=%.6g source=%s",
            float(effective_alpha),
            str(alpha_src),
        )

        # Build demands_config with scaled demands (used for analysis)
        # Also build base_demands for output (with serialized policy, unscaled)
        demands_config: list[dict[str, Any]] = []
        base_demands: list[dict[str, Any]] = []
        for td in td_list:
            demands_config.append(
                {
                    "id": td.id,
                    "source": td.source,
                    "target": td.target,
                    "volume": float(td.volume) * float(effective_alpha),
                    "mode": getattr(td, "mode", "pairwise"),
                    "flow_policy": getattr(td, "flow_policy", None),
                    "priority": getattr(td, "priority", 0),
                    "group_mode": getattr(td, "group_mode", "flatten"),
                }
            )
            base_demands.append(
                {
                    "id": td.id,
                    "source": getattr(td, "source", ""),
                    "target": getattr(td, "target", ""),
                    "volume": float(getattr(td, "volume", 0.0)),
                    "mode": getattr(td, "mode", "pairwise"),
                    "priority": int(getattr(td, "priority", 0)),
                    "flow_policy": serialize_policy_preset(
                        getattr(td, "flow_policy", None)
                    ),
                    "group_mode": getattr(td, "group_mode", "flatten"),
                }
            )

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
            placement_rounds=self.placement_rounds,
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

        # Handle baseline (separate from failure results)
        baseline_result = raw.get("baseline")
        baseline_dict = None
        if baseline_result is not None:
            if hasattr(baseline_result, "to_dict"):
                baseline_dict = baseline_result.to_dict()
            else:
                baseline_dict = baseline_result

        # Handle failure results
        flow_results: list[dict] = []
        for item in raw.get("results", []):
            if isinstance(item, FlowIterationResult):
                flow_results.append(item.to_dict())
            elif hasattr(item, "to_dict") and callable(item.to_dict):
                flow_results.append(item.to_dict())  # type: ignore[union-attr]
            else:
                flow_results.append(item)

        alpha_value = float(effective_alpha)
        alpha_source_value = getattr(self, "_alpha_source", "explicit")

        scenario.results.put(
            "data",
            {
                "baseline": baseline_dict,
                "flow_results": flow_results,
                "context": {
                    "demand_set": self.demand_set,
                    "placement_rounds": self.placement_rounds,
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
            if not isinstance(step, dict):
                raise ValueError(
                    f"alpha_from_step='{self.alpha_from_step}' not found or invalid"
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
