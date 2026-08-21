"""MaxFlow workflow step.

Monte Carlo analysis of maximum flow capacity between node groups using FailureManager.
Produces unified `flow_results` per iteration under `data.flow_results`.

Baseline (no failures) always runs first as a separate reference; `iterations`
counts failure scenarios only.

YAML Configuration Example:

    workflow:
      - type: MaxFlow
        name: "maxflow_dc_to_edge"
        source: "^datacenter/.*"
        target: "^edge/.*"
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
from ngraph.types.base import FlowPlacement, Mode
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
class MaxFlow(WorkflowStep):
    """Maximum flow Monte Carlo workflow step.

    Baseline (no failures) always runs first and is returned in a separate field.
    The flow_results list holds unique failure patterns (deduplicated); each result
    carries an occurrence_count of how many iterations matched that pattern.

    Attributes:
        source: Source node selector (string path or selector dict).
        target: Target node selector (string path or selector dict).
        mode: Flow analysis mode ("combine" or "pairwise").
        failure_policy: Name of failure policy in scenario.failure_policy_set.
            If None, no failure policy is applied.
        iterations: Number of failure iterations to run; must be >= 0.
        parallelism: Worker thread count, or "auto" for the CPU count.
        shortest_path: Restrict flow to lowest-cost paths (IP/IGP mode).
        require_capacity: If True (default), path selection considers capacity.
            If False, path selection is cost-only (true IP/IGP semantics).
        flow_placement: Flow placement strategy.
        seed: Optional seed for reproducible results.
        store_failure_patterns: Record the failure trace on each result.
            Iterations are deduplicated, so a trace describes the first
            iteration of its pattern, not every matching iteration.
        include_flow_details: Whether to collect cost distribution per flow.
        include_min_cut: Whether to include min-cut edges per flow.
    """

    source: Union[str, Dict[str, Any]] = ""
    target: Union[str, Dict[str, Any]] = ""
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
        resolve_parallelism(self.parallelism)  # validate at construction
        Mode.from_string(self.mode)  # validate; raises ValueError on bad values
        if isinstance(self.flow_placement, str):
            self.flow_placement = FlowPlacement.from_string(self.flow_placement)

    def run(self, scenario: "Scenario") -> None:
        t0 = time.perf_counter()
        logger.info("Starting MaxFlow: name=%s", self.name)
        logger.debug(
            "MaxFlow params: source=%s target=%s mode=%s failure_iters=%d parallelism=%s "
            "failure_policy=%s include_flow_details=%s include_min_cut=%s",
            self.source,
            self.target,
            self.mode,
            self.iterations,
            self.parallelism,
            self.failure_policy,
            self.include_flow_details,
            self.include_min_cut,
        )

        # __post_init__ converts string flow_placement values to the enum
        assert isinstance(self.flow_placement, FlowPlacement)

        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = resolve_parallelism(self.parallelism)
        raw = fm.run_max_flow_monte_carlo(
            source=self.source,
            target=self.target,
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

        baseline_dict, flow_results = serialize_monte_carlo_results(raw)

        context = {
            "source": self.source,
            "target": self.target,
            "mode": self.mode,
            "shortest_path": bool(self.shortest_path),
            "require_capacity": bool(self.require_capacity),
            "flow_placement": self.flow_placement.name,
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
