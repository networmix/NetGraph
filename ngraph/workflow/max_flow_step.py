"""MaxFlow workflow step.

Monte Carlo analysis of maximum flow capacity between node groups using FailureManager.
Produces unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) is always run first as a separate reference. The `iterations`
parameter specifies how many failure scenarios to run.

YAML Configuration Example:

    workflow:
      - step_type: MaxFlow
        name: "maxflow_dc_to_edge"
        source: "^datacenter/.*"
        sink: "^edge/.*"
        mode: "combine"
        failure_policy: "random_failures"
        iterations: 100
        parallelism: auto
        shortest_path: false
        require_capacity: true           # false for true IP/IGP semantics
        flow_placement: "PROPORTIONAL"
        seed: 42
        store_failure_patterns: false
        include_flow_details: false      # cost_distribution
        include_min_cut: false           # min-cut edges list
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
class MaxFlow(WorkflowStep):
    """Maximum flow Monte Carlo workflow step.

    Baseline (no failures) is always run first as a separate reference. Results are
    returned with baseline in a separate field. The flow_results list contains unique
    failure patterns (deduplicated); each result has occurrence_count indicating how
    many iterations matched that pattern.

    Attributes:
        source: Source node selector (string path or selector dict).
        sink: Sink node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").
        failure_policy: Name of failure policy in scenario.failure_policy_set.
        iterations: Number of failure iterations to run.
        parallelism: Number of parallel worker processes.
        shortest_path: Whether to use shortest paths only.
        require_capacity: If True (default), path selection considers capacity.
            If False, path selection is cost-only (true IP/IGP semantics).
        flow_placement: Flow placement strategy.
        seed: Optional seed for reproducible results.
        store_failure_patterns: Whether to store failure patterns in results.
        include_flow_details: Whether to collect cost distribution per flow.
        include_min_cut: Whether to include min-cut edges per flow.
    """

    source: Union[str, Dict[str, Any]] = ""
    sink: Union[str, Dict[str, Any]] = ""
    mode: str = "combine"
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int | str = "auto"
    shortest_path: bool = False
    require_capacity: bool = True
    flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL
    seed: int | None = None
    store_failure_patterns: bool = False
    include_flow_details: bool = False
    include_min_cut: bool = False

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
        logger.info("Starting MaxFlow: name=%s", self.name)
        logger.debug(
            "MaxFlow params: source=%s sink=%s mode=%s failure_iters=%d parallelism=%s "
            "failure_policy=%s include_flow_details=%s include_min_cut=%s",
            self.source,
            self.sink,
            self.mode,
            self.iterations,
            self.parallelism,
            self.failure_policy,
            self.include_flow_details,
            self.include_min_cut,
        )

        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = resolve_parallelism(self.parallelism)
        raw = fm.run_max_flow_monte_carlo(
            source=self.source,
            sink=self.sink,
            mode=self.mode,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            shortest_path=self.shortest_path,
            require_capacity=self.require_capacity,
            flow_placement=self.flow_placement,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
            include_flow_summary=self.include_flow_details,
            include_min_cut=self.include_min_cut,
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

        context = {
            "source": self.source,
            "sink": self.sink,
            "mode": self.mode,
            "shortest_path": bool(self.shortest_path),
            "require_capacity": bool(self.require_capacity),
            "flow_placement": getattr(
                self.flow_placement, "name", str(self.flow_placement)
            ),
            "include_flow_details": bool(self.include_flow_details),
            "include_min_cut": bool(self.include_min_cut),
        }
        scenario.results.put(
            "data",
            {
                "baseline": baseline_dict,
                "flow_results": flow_results,
                "context": context,
            },
        )

        metadata = raw.get("metadata", {})
        logger.info(
            "MaxFlow completed: name=%s failure_iters=%d unique_patterns=%d "
            "workers=%d duration=%.3fs",
            self.name,
            metadata.get("iterations", self.iterations),
            metadata.get("unique_patterns", 0),
            metadata.get("parallelism", effective_parallelism),
            time.perf_counter() - t0,
        )


register_workflow_step("MaxFlow")(MaxFlow)
