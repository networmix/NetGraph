"""Traffic matrix demand placement workflow component.

Monte Carlo analysis of traffic demand placement under failures using
FailureManager. Produces per-iteration delivered bandwidth samples and
per-demand placed-bandwidth envelopes, enabling direct computation of
delivered bandwidth at availability percentiles.

YAML Configuration Example:

    workflow:
      - step_type: TrafficMatrixPlacementAnalysis
        name: "tm_placement"
        matrix_name: "default"            # Required
        failure_policy: "random_failures"  # Optional
        iterations: 100                    # Monte Carlo trials
        parallelism: auto                  # Workers (int or "auto")
        placement_rounds: "auto"           # Optimization rounds per priority
        baseline: false                    # Include baseline iteration first
        seed: 42                           # Optional seed
        store_failure_patterns: false
        include_flow_details: false
        alpha: 1.0                         # Float or "auto" to use MSD alpha_star
        availability_percentiles: [50, 90, 95, 99, 99.9, 99.99]

Results stored in `scenario.results` under the step name:
    - offered_gbps_by_pair: {"src->dst|prio=K": float}
    - placed_gbps_envelopes: {pair_key: {frequencies, min, max, mean, stdev, total_samples, src, dst, priority}}
    - delivered_gbps_samples: [float, ...]  # total placed per iteration
    - delivered_gbps_stats: {mean, min, max, stdev, samples, percentiles: {"p50": v, ...}}
      Also flattened keys per percentile, e.g., delivered_gbps_p99_99.
    - failure_pattern_results: Failure pattern mapping (if requested)
    - metadata: Execution metadata (iterations, parallelism, baseline, alpha, etc.)
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ngraph.failure.manager.manager import FailureManager
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.scenario import Scenario

logger = get_logger(__name__)


@dataclass
class TrafficMatrixPlacementAnalysis(WorkflowStep):
    """Monte Carlo demand placement analysis using a named traffic matrix.

    Attributes:
        matrix_name: Name of the traffic matrix to analyze.
        failure_policy: Optional policy name in scenario.failure_policy_set.
        iterations: Number of Monte Carlo iterations.
        parallelism: Number of parallel worker processes.
        placement_rounds: Placement optimization rounds (int or "auto").
        baseline: Include baseline iteration without failures first.
        seed: Optional seed for reproducibility.
        store_failure_patterns: Whether to store failure pattern results.
        include_flow_details: If True, include edges used per demand.
        alpha: Float scale or "auto" to use MSD alpha_star.
        availability_percentiles: Percentiles to compute for delivered Gbps.
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
    alpha: float | str = 1.0
    availability_percentiles: list[float] = (
        50.0,
        90.0,
        95.0,
        99.0,
        99.9,
        99.99,
    )  # type: ignore[assignment]

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
        if isinstance(self.alpha, str):
            if self.alpha != "auto":
                raise ValueError("alpha must be a positive float or 'auto'")
        else:
            if not (self.alpha > 0.0):
                raise ValueError("alpha must be > 0.0")

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
        """Execute demand placement Monte Carlo analysis and store results.

        Produces per-pair placed-Gbps envelopes and per-iteration total
        delivered bandwidth samples with percentile statistics.
        """
        if not self.matrix_name:
            raise ValueError(
                "'matrix_name' is required for TrafficMatrixPlacementAnalysis"
            )

        t0 = time.perf_counter()
        logger.info(
            f"Starting demand placement analysis: {self.name or self.__class__.__name__}"
        )
        logger.debug(
            "Parameters: matrix_name=%s, iterations=%d, parallelism=%s, placement_rounds=%s, baseline=%s, include_flow_details=%s, failure_policy=%s, alpha=%s",
            self.matrix_name,
            self.iterations,
            str(self.parallelism),
            str(self.placement_rounds),
            str(self.baseline),
            str(self.include_flow_details),
            str(self.failure_policy),
            str(self.alpha),
        )

        # Extract and serialize the requested traffic matrix to simple dicts
        try:
            td_list = scenario.traffic_matrix_set.get_matrix(self.matrix_name)
        except KeyError as exc:
            raise ValueError(
                f"Traffic matrix '{self.matrix_name}' not found in scenario."
            ) from exc

        # Snapshot base demands (unscaled) for context
        base_demands: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": getattr(td, "flow_policy_config", None),
            }
            for td in td_list
        ]

        # Determine effective alpha
        effective_alpha = self._resolve_alpha_from_results_if_needed(scenario, td_list)
        # Emit the resolved alpha at INFO for visibility in long runs
        try:
            alpha_src = (
                getattr(self, "_alpha_source", None)
                if isinstance(self.alpha, str)
                else "explicit"
            )
            logger.info(
                "Using alpha: value=%.6g source=%s",
                float(effective_alpha),
                str(alpha_src) if alpha_src else "explicit",
            )
        except Exception:
            pass

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
        # Debug summary including an example with policy
        try:
            example = "-"
            if demands_config:
                ex = demands_config[0]
                src = ex.get("source_path", "")
                dst = ex.get("sink_path", "")
                dem = ex.get("demand", 0.0)
                cfg = ex.get("flow_policy_config")
                policy_name: str
                if isinstance(cfg, FlowPolicyConfig):
                    policy_name = cfg.name
                elif cfg is None:
                    policy_name = f"default:{FlowPolicyConfig.SHORTEST_PATHS_ECMP.name}"
                else:
                    try:
                        policy_name = FlowPolicyConfig(int(cfg)).name
                    except Exception:
                        policy_name = str(cfg)
                example = f"{src}->{dst} demand={dem} policy={policy_name}"
            logger.debug(
                "Extracted %d demands from matrix '%s' (example: %s)",
                len(demands_config),
                self.matrix_name,
                example,
            )
        except Exception:
            # Logging must not raise
            pass

        # Run via FailureManager convenience method (returns per-iteration dicts)
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

        # Aggregate per-iteration outputs into:
        # - per-pair placed_gbps envelopes
        # - per-iteration total delivered_gbps samples
        from collections import defaultdict

        per_pair_values: dict[tuple[str, str, int], list[float]] = defaultdict(list)
        per_pair_offered: dict[tuple[str, str, int], float] = {}
        delivered_samples: list[float] = []

        raw_list = results.raw_results.get("results", [])
        for iter_result in raw_list:
            if not isinstance(iter_result, dict):
                raise TypeError(
                    f"Invalid iteration result type: expected dict, got {type(iter_result).__name__}"
                )
            demands_list = iter_result.get("demands")
            summary = iter_result.get("summary")
            if not isinstance(demands_list, list) or not isinstance(summary, dict):
                raise ValueError(
                    "Iteration result must have 'demands' list and 'summary' dict"
                )

            delivered = float(summary.get("total_placed_gbps", 0.0))
            delivered_samples.append(delivered)

            for rec in demands_list:
                src = str(rec.get("src", ""))
                dst = str(rec.get("dst", ""))
                prio = int(rec.get("priority", 0))
                placed = float(rec.get("placed_gbps", 0.0))
                offered = float(rec.get("offered_gbps", 0.0))
                key = (src, dst, prio)
                per_pair_values[key].append(placed)
                # Offered should be constant; set from first occurrence
                if key not in per_pair_offered:
                    per_pair_offered[key] = offered

        # Helper: build envelope dict from values
        def _envelope(values: list[float]) -> dict[str, Any]:
            if not values:
                return {
                    "frequencies": {},
                    "min": 0.0,
                    "max": 0.0,
                    "mean": 0.0,
                    "stdev": 0.0,
                    "total_samples": 0,
                }
            from math import sqrt

            freqs: dict[float, int] = {}
            total = 0.0
            sum_sq = 0.0
            vmin = float("inf")
            vmax = float("-inf")
            for v in values:
                freqs[v] = freqs.get(v, 0) + 1
                total += v
                sum_sq += v * v
                vmin = min(vmin, v)
                vmax = max(vmax, v)
            n = len(values)
            mean = total / n
            var = max(0.0, (sum_sq / n) - (mean * mean))
            return {
                "frequencies": freqs,
                "min": vmin,
                "max": vmax,
                "mean": mean,
                "stdev": sqrt(var),
                "total_samples": n,
            }

        # Build placed_gbps_envelopes
        placed_envs: dict[str, dict[str, Any]] = {}
        for (src, dst, prio), vals in per_pair_values.items():
            env = _envelope(vals)
            env["src"], env["dst"], env["priority"] = src, dst, prio
            placed_envs[f"{src}->{dst}|prio={prio}"] = env

        # Offered map keyed the same way
        offered_by_pair = {
            f"{src}->{dst}|prio={prio}": float(off)
            for (src, dst, prio), off in per_pair_offered.items()
        }

        # Delivered samples + stats
        def _percentile(sorted_vals: list[float], p: float) -> float:
            if not sorted_vals:
                return 0.0
            if p <= 0:
                return sorted_vals[0]
            if p >= 100:
                return sorted_vals[-1]
            k = int(round((p / 100.0) * (len(sorted_vals) - 1)))
            return float(sorted_vals[max(0, min(len(sorted_vals) - 1, k))])

        samples_sorted = sorted(delivered_samples)
        from statistics import mean, pstdev

        stats_obj: dict[str, Any] = {
            "samples": len(samples_sorted),
            "min": float(samples_sorted[0]) if samples_sorted else 0.0,
            "max": float(samples_sorted[-1]) if samples_sorted else 0.0,
            "mean": float(mean(samples_sorted)) if samples_sorted else 0.0,
            "stdev": float(pstdev(samples_sorted)) if samples_sorted else 0.0,
            "percentiles": {},
        }
        # Ensure list for iteration
        pcts = list(self.availability_percentiles)
        # Normalize potential tuple default
        pcts = [float(p) for p in pcts]
        for p in pcts:
            key = f"p{str(p).replace('.', '_')}"
            stats_obj["percentiles"][key] = _percentile(samples_sorted, p)

        # Store outputs
        scenario.results.put(self.name, "offered_gbps_by_pair", offered_by_pair)
        scenario.results.put(self.name, "placed_gbps_envelopes", placed_envs)
        scenario.results.put(self.name, "delivered_gbps_samples", delivered_samples)
        scenario.results.put(self.name, "delivered_gbps_stats", stats_obj)
        # Flatten percentile keys for convenience
        for p, val in stats_obj["percentiles"].items():
            scenario.results.put(self.name, f"delivered_gbps_{p}", float(val))
        if self.store_failure_patterns and results.failure_patterns:
            scenario.results.put(
                self.name, "failure_pattern_results", results.failure_patterns
            )
        # Augment metadata with step-specific parameters for reproducibility
        try:
            step_metadata = dict(results.metadata)
            step_metadata["alpha"] = float(effective_alpha)
            if isinstance(self.alpha, str) and self.alpha == "auto":
                src = self._alpha_source if hasattr(self, "_alpha_source") else "auto"
                step_metadata["alpha_source"] = src
        except Exception:  # Fallback to original metadata if unexpected type
            step_metadata = results.metadata
        scenario.results.put(self.name, "metadata", step_metadata)
        # Store context for reproducibility
        scenario.results.put(
            self.name,
            "context",
            {
                "matrix_name": self.matrix_name,
                "placement_rounds": self.placement_rounds,
                "include_flow_details": self.include_flow_details,
                "availability_percentiles": list(self.availability_percentiles),
            },
        )
        scenario.results.put(self.name, "base_demands", base_demands)
        # Provide a concise per-step debug summary to aid troubleshooting in CI logs
        try:
            env_count = len(placed_envs)
            prios = sorted(
                {int(k.split("=", 1)[1]) for k in placed_envs.keys() if "|prio=" in k}
            )
            logger.debug(
                "Placed-Gbps envelopes: %d demands; priorities=%s",
                env_count,
                ", ".join(map(str, prios)) if prios else "-",
            )
        except Exception:
            pass

        # INFO-level outcome summary for workflow users
        try:
            # Materialize DemandPlacementResults for potential downstream use
            # (not used directly here; kept for API symmetry and debugging hooks)
            from ngraph.monte_carlo.results import DemandPlacementResults

            _ = DemandPlacementResults(
                raw_results=results.raw_results,
                iterations=results.iterations,
                baseline=results.baseline,
                failure_patterns=results.failure_patterns,
                metadata=results.metadata,
            )

            # Compute concise distribution of delivered samples
            try:
                mean_v = float(stats_obj.get("mean", 0.0))
                p50_v = float(stats_obj["percentiles"].get("p50", 0.0))
                p95_v = float(stats_obj["percentiles"].get("p95", 0.0))
                min_v = float(stats_obj.get("min", 0.0))
                max_v = float(stats_obj.get("max", 0.0))
            except Exception:
                mean_v = p50_v = p95_v = min_v = max_v = 0.0

            # Add a concise per-step summary object to the results store
            scenario.results.put(
                self.name,
                "placement_summary",
                {
                    "iterations": int(results.metadata.get("iterations", 0)),
                    "parallelism": int(
                        results.metadata.get(
                            "parallelism", self._resolve_parallelism(self.parallelism)
                        )
                    ),
                    "baseline": bool(results.metadata.get("baseline", False)),
                    "alpha": float(step_metadata.get("alpha", 1.0)),
                    "alpha_source": step_metadata.get("alpha_source", None),
                    "demand_count": len(per_pair_values),
                    "delivered_mean_gbps": mean_v,
                    "delivered_p50_gbps": p50_v,
                    "delivered_p95_gbps": p95_v,
                    "delivered_min_gbps": min_v,
                    "delivered_max_gbps": max_v,
                },
            )

            # Prepare INFO log with consistent fields
            meta = results.metadata or {}
            iterations = int(meta.get("iterations", self.iterations))
            workers = int(
                meta.get("parallelism", self._resolve_parallelism(self.parallelism))
            )
            try:
                alpha_value = float(step_metadata.get("alpha"))  # type: ignore[arg-type]
            except Exception:
                alpha_value = float(effective_alpha) if effective_alpha else 1.0
            alpha_source = (
                step_metadata.get("alpha_source")
                if isinstance(step_metadata, dict)
                else getattr(self, "_alpha_source", None)
            )
            alpha_source_str = (
                str(alpha_source)
                if alpha_source
                else ("explicit" if not isinstance(self.alpha, str) else "auto")
            )

            # Use delivered samples stats for logging
            mean_v = float(stats_obj.get("mean", 0.0))
            p50_v = float(stats_obj["percentiles"].get("p50", 0.0))
            p95_v = float(stats_obj["percentiles"].get("p95", 0.0))
            min_v = float(stats_obj.get("min", 0.0))
            max_v = float(stats_obj.get("max", 0.0))

            duration_sec = time.perf_counter() - t0
            rounds_str = str(self.placement_rounds)
            seed_str = str(self.seed) if self.seed is not None else "-"
            baseline_str = str(meta.get("baseline", self.baseline))
            logger.info(
                (
                    "Placement summary: name=%s alpha=%.6g source=%s "
                    "demands=%d iters=%d workers=%d rounds=%s baseline=%s "
                    "seed=%s duration=%.3fs delivered_mean=%.4f p50=%.4f p95=%.4f "
                    "min=%.4f max=%.4f"
                ),
                self.name,
                alpha_value,
                alpha_source_str,
                len(per_pair_values),
                iterations,
                workers,
                rounds_str,
                baseline_str,
                seed_str,
                duration_sec,
                mean_v,
                p50_v,
                p95_v,
                min_v,
                max_v,
            )
        except Exception:
            # Logging must not raise
            pass

        logger.info(
            f"Demand placement analysis completed: {self.name or self.__class__.__name__}"
        )

    # --- Alpha resolution helpers -------------------------------------------------
    def _resolve_alpha_from_results_if_needed(
        self, scenario: "Scenario", td_list: list[Any]
    ) -> float:
        """Resolve effective alpha.

        If alpha is a float, return it. If alpha == "auto", search prior MSD
        results for a matching matrix and identical base demands, and return
        alpha_star. Raises ValueError if no suitable match is found.

        Args:
            scenario: Scenario with results store.
            td_list: Current traffic demand objects from the matrix.

        Returns:
            Effective numeric alpha.
        """
        if not isinstance(self.alpha, str):
            return float(self.alpha)
        if self.alpha != "auto":  # Defensive; validated earlier
            raise ValueError("alpha must be a positive float or 'auto'")

        # Build current base demands snapshot for strict comparison
        current_base: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": getattr(td, "flow_policy_config", None),
            }
            for td in td_list
        ]

        # Iterate prior steps by execution order; pick most recent matching MSD
        meta = scenario.results.get_all_step_metadata()
        step_names_by_order = sorted(
            meta.keys(), key=lambda name: meta[name].execution_order
        )
        chosen_alpha: float | None = None
        chosen_source: str | None = None
        for step_name in reversed(step_names_by_order):
            md = meta[step_name]
            if md.step_type != "MaximumSupportedDemandAnalysis":
                continue
            ctx = scenario.results.get(step_name, "context")
            if not isinstance(ctx, dict):
                continue
            if ctx.get("matrix_name") != self.matrix_name:
                continue
            base = scenario.results.get(step_name, "base_demands")
            if not isinstance(base, list):
                continue
            if not self._base_demands_match(base, current_base):
                continue
            alpha_star = scenario.results.get(step_name, "alpha_star")
            try:
                chosen_alpha = float(alpha_star)
                chosen_source = f"MSD:{step_name}"
                break
            except (TypeError, ValueError):
                continue

        if chosen_alpha is None:
            raise ValueError(
                "alpha='auto' requires a prior MaximumSupportedDemandAnalysis for "
                f"matrix '{self.matrix_name}' with identical base demands executed earlier in the workflow. "
                "Add an MSD step before this step or set a numeric alpha."
            )

        # Record source for metadata
        self._alpha_source = chosen_source or "auto"
        return chosen_alpha

    @staticmethod
    def _base_demands_match(
        a: list[dict[str, Any]], b: list[dict[str, Any]], tol: float = 1e-12
    ) -> bool:
        """Return True if two base_demand lists are equivalent.

        Compares length and per-entry fields with stable ordering by a key.
        Floats are compared with an absolute tolerance.
        """
        if len(a) != len(b):
            return False

        def key_fn(d: dict[str, Any]) -> tuple:
            return (
                str(d.get("source_path", "")),
                str(d.get("sink_path", "")),
                int(d.get("priority", 0)),
                str(d.get("mode", "pairwise")),
                str(d.get("flow_policy_config", None)),
            )

        a_sorted = sorted(a, key=key_fn)
        b_sorted = sorted(b, key=key_fn)
        for da, db in zip(a_sorted, b_sorted, strict=False):
            if key_fn(da) != key_fn(db):
                return False
            va = float(da.get("demand", 0.0))
            vb = float(db.get("demand", 0.0))
            if abs(va - vb) > tol:
                return False
        return True


# Register the workflow step
register_workflow_step("TrafficMatrixPlacementAnalysis")(TrafficMatrixPlacementAnalysis)
