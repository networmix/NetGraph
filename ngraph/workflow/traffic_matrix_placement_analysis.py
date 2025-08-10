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
        include_flow_details: true         # Collect per-demand cost distribution and edges

Results stored in `scenario.results` under the step name:
    - placement_envelopes: Per-demand placement ratio envelopes with statistics
      When ``include_flow_details`` is true, each envelope also includes
      ``flow_summary_stats`` with aggregated ``cost_distribution_stats`` and
      ``edge_usage_frequencies``.
    - failure_pattern_results: Failure pattern mapping (if requested)
    - metadata: Execution metadata (iterations, parallelism, baseline, etc.)
"""

from __future__ import annotations

import os
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
        include_flow_details: If True, collect per-demand cost distribution and
            edges used per iteration, and aggregate into ``flow_summary_stats``
            on each placement envelope.
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

    def __post_init__(self) -> None:
        """Validate parameters.

        Raises:
            ValueError: If parameters are invalid.
        """
        if self.iterations < 1:
            raise ValueError("iterations must be >= 1")
        if isinstance(self.parallelism, str):
            if self.parallelism != "auto":
                raise ValueError("parallelism must be an integer or 'auto'")
        else:
            if self.parallelism < 1:
                raise ValueError("parallelism must be >= 1")

    @staticmethod
    def _resolve_parallelism(parallelism: int | str) -> int:
        """Resolve requested parallelism, supporting the "auto" keyword.

        Args:
            parallelism: Requested parallelism as int or the string "auto".

        Returns:
            Concrete parallelism value (>= 1).
        """
        if isinstance(parallelism, str):
            return max(1, int(os.cpu_count() or 1))
        return max(1, int(parallelism))

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
        logger.debug(
            "Parameters: matrix_name=%s, iterations=%d, parallelism=%s, placement_rounds=%s, baseline=%s, include_flow_details=%s, failure_policy=%s",
            self.matrix_name,
            self.iterations,
            str(self.parallelism),
            str(self.placement_rounds),
            str(self.baseline),
            str(self.include_flow_details),
            str(self.failure_policy),
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
        logger.debug(
            "Extracted %d demands from matrix '%s' (example: %s)",
            len(demands_config),
            self.matrix_name,
            (
                f"{demands_config[0]['source_path']}->{demands_config[0]['sink_path']} demand={demands_config[0]['demand']}"
                if demands_config
                else "-"
            ),
        )

        # Run via FailureManager convenience method
        fm = FailureManager(
            network=scenario.network,
            failure_policy_set=scenario.failure_policy_set,
            policy_name=self.failure_policy,
        )

        effective_parallelism = self._resolve_parallelism(self.parallelism)

        results = fm.run_demand_placement_monte_carlo(
            demands_config=demands_config,
            iterations=self.iterations,
            parallelism=effective_parallelism,
            placement_rounds=self.placement_rounds,
            baseline=self.baseline,
            seed=self.seed,
            store_failure_patterns=self.store_failure_patterns,
            include_flow_details=self.include_flow_details,
        )
        logger.debug(
            "Placement MC completed: iterations=%d, parallelism=%d, baseline=%s, overall_ratio=%.4f",
            results.metadata.get("iterations", 0),
            results.metadata.get("parallelism", 0),
            str(results.metadata.get("baseline", False)),
            float(results.raw_results.get("overall_placement_ratio", 0.0)),
        )

        # Build per-demand placement envelopes similar to capacity envelopes
        from collections import defaultdict

        from ngraph.results.artifacts import PlacementEnvelope

        # Single-pass accumulation across all iterations
        # - placement ratios always
        # - optional cost distributions and edge usage when include_flow_details=True
        per_demand_ratios: dict[tuple[str, str, int], list[float]] = defaultdict(list)
        cost_map: dict[tuple[str, str, int], dict[float, list[float]]] | None = None
        edge_counts: dict[tuple[str, str, int], dict[str, int]] | None = None

        if self.include_flow_details:
            cost_map = defaultdict(lambda: defaultdict(list))
            edge_counts = defaultdict(lambda: defaultdict(int))

        for iter_result in results.raw_results.get("results", []):
            for d_entry in iter_result.get("demand_results", []):
                src = str(d_entry.get("src", ""))
                dst = str(d_entry.get("dst", ""))
                prio = int(d_entry.get("priority", 0))
                ratio = float(d_entry.get("placement_ratio", 0.0))
                per_demand_ratios[(src, dst, prio)].append(ratio)

                if (
                    self.include_flow_details
                    and cost_map is not None
                    and edge_counts is not None
                ):
                    cd = d_entry.get("cost_distribution")
                    if isinstance(cd, dict):
                        for cost_key, vol in cd.items():
                            try:
                                cost_val = float(cost_key)
                                vol_f = float(vol)
                            except (TypeError, ValueError) as exc:
                                raise ValueError(
                                    f"Invalid cost_distribution entry for {src}->{dst} prio={prio}: {cost_key!r}={vol!r}: {exc}"
                                ) from exc
                            cost_map[(src, dst, prio)][cost_val].append(vol_f)

                    used_edges = d_entry.get("edges_used") or []
                    if isinstance(used_edges, list):
                        for e in used_edges:
                            edge_counts[(src, dst, prio)][str(e)] += 1

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

        # If flow details were requested, aggregate them into per-demand flow_summary_stats
        if (
            self.include_flow_details
            and cost_map is not None
            and edge_counts is not None
        ):
            # Reduce accumulations into stats and attach to envelopes
            for (src, dst, prio), costs in cost_map.items():
                key = f"{src}->{dst}|prio={prio}"
                if key not in envelopes:
                    continue
                cost_stats: dict[float, dict[str, Any]] = {}
                for cost, vols in costs.items():
                    if not vols:
                        continue
                    freq = {v: vols.count(v) for v in set(vols)}
                    cost_stats[float(cost)] = {
                        "mean": sum(vols) / len(vols),
                        "min": min(vols),
                        "max": max(vols),
                        "total_samples": len(vols),
                        "frequencies": freq,
                    }
                flow_stats: dict[str, Any] = {"cost_distribution_stats": cost_stats}
                # Attach edge usage frequencies if collected
                ec = edge_counts.get((src, dst, prio))
                if ec:
                    flow_stats["edge_usage_frequencies"] = dict(ec)
                envelopes[key]["flow_summary_stats"] = flow_stats

        # Convert to serializable dicts for results export
        # Store serializable outputs
        scenario.results.put(self.name, "placement_envelopes", envelopes)
        if self.store_failure_patterns and results.failure_patterns:
            scenario.results.put(
                self.name, "failure_pattern_results", results.failure_patterns
            )
        scenario.results.put(self.name, "metadata", results.metadata)
        # Provide a concise per-step debug summary to aid troubleshooting in CI logs
        try:
            env_count = len(envelopes)
            priorities = sorted({int(k.split("=", 1)[1]) for k in envelopes.keys()})
            logger.debug(
                "Placement envelopes: %d demands; priorities=%s",
                env_count,
                ", ".join(map(str, priorities)) if priorities else "-",
            )
        except Exception:
            pass

        logger.info(
            f"Demand placement analysis completed: {self.name or self.__class__.__name__}"
        )


# Register the workflow step
register_workflow_step("TrafficMatrixPlacementAnalysis")(TrafficMatrixPlacementAnalysis)
