"""MaxFlow workflow step.

Monte Carlo analysis of maximum flow capacity between node groups using FailureManager.
Produces unified `flow_results` per iteration under `data.flow_results`.

YAML Configuration Example:

    workflow:
      - step_type: MaxFlow
        name: "maxflow_dc_to_edge"
        source_path: "^datacenter/.*"
        sink_path: "^edge/.*"
        mode: "combine"
        failure_policy: "random_failures"
        iterations: 100
        parallelism: auto
        shortest_path: false
        flow_placement: "PROPORTIONAL"
        baseline: false
        seed: 42
        store_failure_patterns: false
        include_flow_details: false      # cost_distribution
        include_min_cut: false           # min-cut edges list
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ngraph.algorithms.base import FlowPlacement
from ngraph.failure.manager.manager import FailureManager
from ngraph.logging import get_logger
from ngraph.results.flow import FlowIterationResult
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class MaxFlow(WorkflowStep):
    """Maximum flow Monte Carlo workflow step.

    Attributes:
        source_path: Regex pattern for source node groups.
        sink_path: Regex pattern for sink node groups.
        mode: Flow analysis mode ("combine" or "pairwise").
        failure_policy: Name of failure policy in scenario.failure_policy_set.
        iterations: Number of Monte Carlo trials.
        parallelism: Number of parallel worker processes.
        shortest_path: Whether to use shortest paths only.
        flow_placement: Flow placement strategy.
        baseline: Whether to run first iteration without failures as baseline.
        seed: Optional seed for reproducible results.
        store_failure_patterns: Whether to store failure patterns in results.
        include_flow_details: Whether to collect cost distribution per flow.
        include_min_cut: Whether to include min-cut edges per flow.
    """

    source_path: str = ""
    sink_path: str = ""
    mode: str = "combine"
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int | str = "auto"
    shortest_path: bool = False
    flow_placement: FlowPlacement | str = FlowPlacement.PROPORTIONAL
    baseline: bool = False
    seed: int | None = None
    store_failure_patterns: bool = False
    include_flow_details: bool = False
    include_min_cut: bool = False

    def __post_init__(self) -> None:
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if isinstance(self.parallelism, str):
            if self.parallelism != "auto":
                raise ValueError("parallelism must be an integer or 'auto'")
        else:
            if self.parallelism < 1:
                raise ValueError("parallelism must be >= 1")
        if self.mode not in {"combine", "pairwise"}:
            raise ValueError("mode must be 'combine' or 'pairwise'")
        if self.baseline and self.iterations < 2:
            raise ValueError(
                "baseline=True requires iterations >= 2 "
                "(first iteration is baseline, remaining are with failures)"
            )
        if isinstance(self.flow_placement, str):
            try:
                self.flow_placement = FlowPlacement[self.flow_placement.upper()]
            except KeyError:
                valid_values = ", ".join([e.name for e in FlowPlacement])
                raise ValueError(
                    f"Invalid flow_placement '{self.flow_placement}'. "
                    f"Valid values are: {valid_values}"
                ) from None

    @staticmethod
    def _resolve_parallelism(parallelism: int | str) -> int:
        if isinstance(parallelism, str):
            return max(1, int(os.cpu_count() or 1))
        return max(1, int(parallelism))

    def run(self, scenario: "Scenario") -> None:
        t0 = time.perf_counter()
        logger.info(f"Starting max-flow: {self.name}")
        logger.debug(
            "Parameters: source_path=%s, sink_path=%s, mode=%s, iterations=%s, parallelism=%s, "
            "failure_policy=%s, baseline=%s, include_flow_details=%s, include_min_cut=%s",
            self.source_path,
            self.sink_path,
            self.mode,
            str(self.iterations),
            str(self.parallelism),
            str(self.failure_policy),
            str(self.baseline),
            str(self.include_flow_details),
            str(self.include_min_cut),
        )

        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )
        effective_parallelism = self._resolve_parallelism(self.parallelism)
        raw = fm.run_max_flow_monte_carlo(
            source_path=self.source_path,
            sink_path=self.sink_path,
            mode=self.mode,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            shortest_path=self.shortest_path,
            flow_placement=self.flow_placement,
            baseline=self.baseline,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
            include_flow_summary=self.include_flow_details,
            include_min_cut=self.include_min_cut,
        )

        scenario.results.put("metadata", raw.get("metadata", {}))
        flow_results: list[dict] = []
        for item in raw.get("results", []):
            if isinstance(item, FlowIterationResult):
                flow_results.append(item.to_dict())
            elif hasattr(item, "to_dict") and callable(item.to_dict):
                flow_results.append(item.to_dict())  # type: ignore[union-attr]
            else:
                flow_results.append(item)

        context = {
            "source_path": self.source_path,
            "sink_path": self.sink_path,
            "mode": self.mode,
            "shortest_path": bool(self.shortest_path),
            "flow_placement": getattr(
                self.flow_placement, "name", str(self.flow_placement)
            ),
            "include_flow_details": bool(self.include_flow_details),
            "include_min_cut": bool(self.include_min_cut),
        }
        scenario.results.put(
            "data",
            {
                "flow_results": flow_results,
                "context": context,
            },
        )

        logger.info(
            "Max-flow stored: name=%s iters=%s workers=%s duration=%.3fs",
            self.name,
            str(raw.get("metadata", {}).get("iterations", self.iterations)),
            str(raw.get("metadata", {}).get("parallelism", effective_parallelism)),
            time.perf_counter() - t0,
        )


register_workflow_step("MaxFlow")(MaxFlow)
