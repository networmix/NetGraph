"""Traffic matrix demand placement workflow component.

Executes Monte Carlo analysis of traffic demand placement under failures using
FailureManager. Takes a named traffic matrix from the scenario's
TrafficMatrixSet. Optionally includes a baseline iteration (no failures).

YAML Configuration Example:

    workflow:
      - step_type: TrafficMatrixPlacementAnalysis
        name: "tm_placement_monte_carlo"
        matrix_name: "default"           # Required: Name of traffic matrix to use
        failure_policy: "random_failures" # Optional: Named failure policy
        iterations: 100                    # Number of Monte Carlo trials
        parallelism: 4                     # Number of worker processes
        placement_rounds: "auto"          # Optimization rounds per priority (int or "auto")
        baseline: true                     # Include baseline iteration first
        seed: 42                           # Optional reproducible seed
        store_failure_patterns: false      # Store failure patterns if needed

Results stored in `scenario.results` under the step name:
    - placement_results: Per-iteration demand placement statistics (serializable)
    - failure_pattern_results: Failure pattern mapping (if requested)
    - metadata: Execution metadata (iterations, parallelism, baseline, etc.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.failure.manager.manager import FailureManager
from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class TrafficMatrixPlacementAnalysis(WorkflowStep):
    """Monte Carlo demand placement analysis using a named traffic matrix.

    Attributes:
        matrix_name: Name of the traffic matrix in scenario.traffic_matrix_set.
        failure_policy: Optional policy name in scenario.failure_policy_set.
        iterations: Number of Monte Carlo iterations.
        parallelism: Number of parallel worker processes.
        placement_rounds: Placement optimization rounds (int or "auto").
        baseline: Include baseline iteration without failures first.
        seed: Optional seed for reproducibility.
        store_failure_patterns: Whether to store failure pattern results.
    """

    matrix_name: str = ""
    failure_policy: str | None = None
    iterations: int = 1
    parallelism: int = 1
    placement_rounds: int | str = "auto"
    baseline: bool = False
    seed: int | None = None
    store_failure_patterns: bool = False

    def run(self, scenario: "Scenario") -> None:
        """Execute demand placement Monte Carlo analysis.

        Args:
            scenario: Scenario containing network, failure policies, and traffic matrices.

        Raises:
            ValueError: If matrix_name is not provided or not found in the scenario.
        """
        if not self.matrix_name:
            raise ValueError(
                "'matrix_name' is required for TrafficMatrixPlacementAnalysis"
            )

        logger.info(
            f"Starting demand placement analysis: {self.name or self.__class__.__name__}"
        )

        # Extract and serialize the requested traffic matrix to simple dicts
        try:
            td_list = scenario.traffic_matrix_set.get_matrix(self.matrix_name)
        except KeyError as exc:
            raise ValueError(
                f"Traffic matrix '{self.matrix_name}' not found in scenario."
            ) from exc

        demands_config: list[dict[str, Any]] = []
        for td in td_list:
            demands_config.append(
                {
                    "source_path": td.source_path,
                    "sink_path": td.sink_path,
                    "demand": td.demand,
                    "mode": getattr(td, "mode", "pairwise"),
                    "flow_policy_config": getattr(td, "flow_policy_config", None),
                    "priority": getattr(td, "priority", 0),
                }
            )

        # Run via FailureManager convenience method
        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )

        results = fm.run_demand_placement_monte_carlo(
            demands_config=demands_config,
            iterations=self.iterations,
            parallelism=self.parallelism,
            placement_rounds=self.placement_rounds,
            baseline=self.baseline,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
        )

        # Build per-demand placement envelopes similar to capacity envelopes
        from collections import defaultdict

        from ngraph.results.artifacts import PlacementEnvelope

        # Collect per-demand placement ratios across iterations keyed by (src,dst,prio)
        per_demand_ratios: dict[tuple[str, str, int], list[float]] = defaultdict(list)

        for iter_result in results.raw_results.get("results", []):
            for d_entry in iter_result.get("demand_results", []):
                src = str(d_entry.get("src", ""))
                dst = str(d_entry.get("dst", ""))
                prio = int(d_entry.get("priority", 0))
                ratio = float(d_entry.get("placement_ratio", 0.0))
                per_demand_ratios[(src, dst, prio)].append(ratio)

        # Create PlacementEnvelope per demand; use 'pairwise' as mode because expanded demands are per pair
        envelopes: dict[str, dict[str, Any]] = {}
        for (src, dst, prio), ratios in per_demand_ratios.items():
            env = PlacementEnvelope.from_values(
                source=src,
                sink=dst,
                mode="pairwise",
                priority=prio,
                ratios=ratios,
            )
            key = f"{src}->{dst}|prio={prio}"
            data = env.to_dict()
            data["src"] = src
            data["dst"] = dst
            data["metric"] = "placement_ratio"
            envelopes[key] = data

        # Convert to serializable dicts for results export
        # Store serializable outputs
        scenario.results.put(self.name, "placement_envelopes", envelopes)
        if self.store_failure_patterns and results.failure_patterns:
            scenario.results.put(
                self.name, "failure_pattern_results", results.failure_patterns
            )
        scenario.results.put(self.name, "metadata", results.metadata)

        logger.info(
            f"Demand placement analysis completed: {self.name or self.__class__.__name__}"
        )


# Register the workflow step
register_workflow_step("TrafficMatrixPlacementAnalysis")(TrafficMatrixPlacementAnalysis)
