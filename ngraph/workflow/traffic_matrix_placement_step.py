"""TrafficMatrixPlacement workflow step.

Runs Monte Carlo demand placement using a named traffic matrix and produces
unified `flow_results` per iteration under `data.flow_results`.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.failure.manager.manager import FailureManager
from ngraph.logging import get_logger
from ngraph.results.flow import FlowIterationResult
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class TrafficMatrixPlacement(WorkflowStep):
    """Monte Carlo demand placement using a named traffic matrix.

    Attributes:
        matrix_name: Name of the traffic matrix to analyze.
        failure_policy: Optional policy name in scenario.failure_policy_set.
        iterations: Number of Monte Carlo iterations.
        parallelism: Number of parallel worker processes.
        placement_rounds: Placement optimization rounds (int or "auto").
        baseline: Include baseline iteration without failures first.
        seed: Optional seed for reproducibility.
        store_failure_patterns: Whether to store failure pattern results.
        include_flow_details: When True, include cost_distribution per flow.
        include_used_edges: When True, include set of used edges per demand in entry data.
        alpha: Numeric scale for demands in the matrix.
        alpha_from_step: Optional producer step name to read alpha from.
        alpha_from_field: Dotted field path in producer step (default: "data.alpha_star").
    """

    matrix_name: str = ""
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int | str = "auto"
    placement_rounds: int | str = "auto"
    baseline: bool = False
    seed: int | None = None
    store_failure_patterns: bool = False
    include_flow_details: bool = False
    include_used_edges: bool = False
    alpha: float = 1.0
    alpha_from_step: str | None = None
    alpha_from_field: str = "data.alpha_star"

    def __post_init__(self) -> None:
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if isinstance(self.parallelism, str):
            if self.parallelism != "auto":
                raise ValueError("parallelism must be an integer or 'auto'")
        else:
            if self.parallelism < 1:
                raise ValueError("parallelism must be >= 1")
        if not (float(self.alpha) > 0.0):
            raise ValueError("alpha must be > 0.0")

    @staticmethod
    def _resolve_parallelism(parallelism: int | str) -> int:
        if isinstance(parallelism, str):
            return max(1, int(os.cpu_count() or 1))
        return max(1, int(parallelism))

    def run(self, scenario: "Scenario") -> None:
        if not self.matrix_name:
            raise ValueError("'matrix_name' is required for TrafficMatrixPlacement")

        t0 = time.perf_counter()
        logger.info(
            f"Starting traffic-matrix placement: {self.name or self.__class__.__name__}"
        )
        logger.debug(
            "Parameters: matrix_name=%s, iterations=%d, parallelism=%s, placement_rounds=%s, baseline=%s, include_flow_details=%s, include_used_edges=%s, failure_policy=%s, alpha=%s",
            self.matrix_name,
            self.iterations,
            str(self.parallelism),
            str(self.placement_rounds),
            str(self.baseline),
            str(self.include_flow_details),
            str(self.include_used_edges),
            str(self.failure_policy),
            str(self.alpha),
        )

        # Extract and serialize traffic matrix
        try:
            td_list = scenario.traffic_matrix_set.get_matrix(self.matrix_name)
        except KeyError as exc:
            raise ValueError(
                f"Traffic matrix '{self.matrix_name}' not found in scenario."
            ) from exc

        def _serialize_policy(cfg: Any) -> Any:
            from ngraph.flows.policy import FlowPolicyConfig  # local import

            if cfg is None:
                return None
            if isinstance(cfg, FlowPolicyConfig):
                return cfg.name
            # Fall back to string when it cannot be coerced to enum
            try:
                return FlowPolicyConfig(int(cfg)).name
            except Exception as exc:
                logger.debug("Unrecognized flow_policy_config value: %r (%s)", cfg, exc)
                return str(cfg)

        base_demands: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": _serialize_policy(
                    getattr(td, "flow_policy_config", None)
                ),
            }
            for td in td_list
        ]

        # Resolve alpha
        effective_alpha = self._resolve_alpha(scenario)
        alpha_src = getattr(self, "_alpha_source", None) or "explicit"
        logger.info(
            "Using alpha: value=%.6g source=%s",
            float(effective_alpha),
            str(alpha_src),
        )

        demands_config: list[dict[str, Any]] = []
        for td in td_list:
            demands_config.append(
                {
                    "source_path": td.source_path,
                    "sink_path": td.sink_path,
                    "demand": float(td.demand) * float(effective_alpha),
                    "mode": getattr(td, "mode", "pairwise"),
                    "flow_policy_config": getattr(td, "flow_policy_config", None),
                    "priority": getattr(td, "priority", 0),
                }
            )

        # Run via FailureManager
        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = self._resolve_parallelism(self.parallelism)

        raw = fm.run_demand_placement_monte_carlo(
            demands_config=demands_config,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            placement_rounds=self.placement_rounds,
            baseline=self.baseline,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
            include_flow_details=self.include_flow_details,
            include_used_edges=self.include_used_edges,
        )

        logger.debug(
            "Placement MC completed: iterations=%s, parallelism=%s, baseline=%s",
            str(raw.get("metadata", {}).get("iterations", 0)),
            str(raw.get("metadata", {}).get("parallelism", 0)),
            str(raw.get("metadata", {}).get("baseline", False)),
        )

        # Store outputs
        step_metadata = raw.get("metadata", {})
        scenario.results.put("metadata", step_metadata)
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
                "flow_results": flow_results,
                "context": {
                    "matrix_name": self.matrix_name,
                    "placement_rounds": self.placement_rounds,
                    "include_flow_details": self.include_flow_details,
                    "include_used_edges": self.include_used_edges,
                    "base_demands": base_demands,
                    "alpha": alpha_value,
                    "alpha_source": alpha_source_value,
                },
            },
        )

        # Log summary
        totals = []
        for item in raw.get("results", []):
            if isinstance(item, FlowIterationResult):
                totals.append(float(item.summary.total_placed))
            else:
                summary = getattr(item, "summary", None)
                if summary and hasattr(summary, "get"):
                    totals.append(float(summary.get("total_placed", 0.0)))
                else:
                    totals.append(0.0)
        from statistics import mean

        mean_v = float(mean(totals)) if totals else 0.0
        duration_sec = time.perf_counter() - t0
        rounds_str = str(self.placement_rounds)
        seed_str = str(self.seed) if self.seed is not None else "-"
        baseline_str = str(step_metadata.get("baseline", self.baseline))
        iterations = int(step_metadata.get("iterations", self.iterations))
        workers = int(
            step_metadata.get(
                "parallelism", self._resolve_parallelism(self.parallelism)
            )
        )
        logger.info(
            (
                "Placement summary: name=%s alpha=%.6g source=%s "
                "iters=%d workers=%d rounds=%s baseline=%s seed=%s delivered_mean=%.4f duration=%.3fs"
            ),
            self.name,
            alpha_value,
            str(alpha_source_value or "explicit"),
            iterations,
            workers,
            rounds_str,
            baseline_str,
            seed_str,
            mean_v,
            duration_sec,
        )

        logger.info(
            f"Traffic-matrix placement completed: {self.name or self.__class__.__name__}"
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
