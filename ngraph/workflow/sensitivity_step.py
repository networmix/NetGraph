"""Sensitivity workflow step.

Monte Carlo sensitivity analysis of network bottlenecks between node groups
using FailureManager. Identifies critical edges and quantifies their impact
on flow capacity across failure scenarios.

Baseline (no failures) is always run first as a separate reference. The
``iterations`` parameter specifies how many failure scenarios to run.
Per-iteration results include per-edge flow-reduction deltas. Aggregated
``component_scores`` summarize mean/max/min impact across all iterations.

YAML Configuration Example:

    workflow:
      - type: Sensitivity
        name: "bottleneck_analysis"
        source: "^datacenter/.*"
        target: "^edge/.*"
        mode: "combine"
        failure_policy: "random_failures"
        iterations: 100
        parallelism: auto
        shortest_path: false
        flow_placement: "PROPORTIONAL"
        seed: 42
        store_failure_patterns: false
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Union

from ngraph.analysis.failure_manager import FailureManager
from ngraph.logging import get_logger
from ngraph.results.flow import FlowIterationResult
from ngraph.types.base import FlowPlacement
from ngraph.workflow.base import (
    WorkflowStep,
    register_workflow_step,
    resolve_parallelism,
)

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class Sensitivity(WorkflowStep):
    """Monte Carlo sensitivity analysis workflow step.

    Identifies critical network edges by measuring the flow-capacity reduction
    caused by removing each one, across Monte Carlo failure scenarios. Results
    include per-iteration sensitivity maps and aggregated component scores.

    Baseline (no failures) is always run first as a separate reference. The
    flow_results list contains unique failure patterns (deduplicated); each
    result has occurrence_count indicating how many iterations matched that
    pattern.

    Attributes:
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").
        failure_policy: Name of failure policy in scenario.failure_policy_set.
        iterations: Number of failure iterations to run.
        parallelism: Number of parallel worker threads.
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.
        seed: Optional seed for reproducible results.
        store_failure_patterns: Whether to store failure patterns in results.
    """

    source: Union[str, Dict[str, Any]] = ""
    target: Union[str, Dict[str, Any]] = ""
    mode: str = "combine"
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int | str = "auto"
    shortest_path: bool = False
    flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL
    seed: int | None = None
    store_failure_patterns: bool = False

    def __post_init__(self) -> None:
        if self.iterations < 0:
            raise ValueError("iterations must be >= 0")
        if isinstance(self.parallelism, str):
            if self.parallelism != "auto":
                raise ValueError("parallelism must be an integer or 'auto'")
        else:
            if self.parallelism < 1:
                raise ValueError("parallelism must be >= 1")
        if self.mode not in {"combine", "pairwise"}:
            raise ValueError("mode must be 'combine' or 'pairwise'")
        if isinstance(self.flow_placement, str):
            self.flow_placement = FlowPlacement.from_string(self.flow_placement)

    def run(self, scenario: "Scenario") -> None:
        t0 = time.perf_counter()
        logger.info("Starting Sensitivity: name=%s", self.name)
        logger.debug(
            "Sensitivity params: source=%s target=%s mode=%s failure_iters=%d "
            "parallelism=%s failure_policy=%s shortest_path=%s",
            self.source,
            self.target,
            self.mode,
            self.iterations,
            self.parallelism,
            self.failure_policy,
            self.shortest_path,
        )

        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = resolve_parallelism(self.parallelism)
        raw = fm.run_sensitivity_monte_carlo(
            source=self.source,
            target=self.target,
            mode=self.mode,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            shortest_path=self.shortest_path,
            flow_placement=self.flow_placement,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
        )

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

        # Component scores: aggregated per-component sensitivity statistics
        component_scores = raw.get("component_scores", {})

        context = {
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
            "shortest_path": bool(self.shortest_path),
            "flow_placement": getattr(
                self.flow_placement, "name", str(self.flow_placement)
            ),
        }
        scenario.results.put(
            "data",
            {
                "baseline": baseline_dict,
                "flow_results": flow_results,
                "component_scores": component_scores,
                "context": context,
            },
        )

        metadata = raw.get("metadata", {})
        logger.info(
            "Sensitivity completed: name=%s failure_iters=%d unique_patterns=%d "
            "workers=%d duration=%.3fs",
            self.name,
            metadata.get("iterations", self.iterations),
            metadata.get("unique_patterns", 0),
            metadata.get("parallelism", effective_parallelism),
            time.perf_counter() - t0,
        )


register_workflow_step("Sensitivity")(Sensitivity)
