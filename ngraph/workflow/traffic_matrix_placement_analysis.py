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
        alpha: 1.0                        # Optional scaling factor for all demands

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
        alpha: Scaling factor applied to all demand values prior to analysis.
            Accepts a positive float or the string "auto". When "auto", the
            step looks up the most recent prior MaximumSupportedDemandAnalysis for
            the same matrix with identical base demands and uses its alpha_star.
            Raises ValueError if no suitable MSD result is found or validation fails.
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
            # Unified FlowResult list only (strict)
            if not isinstance(iter_result, list):
                raise TypeError(
                    f"Invalid iteration result type: expected list[FlowResult], got {type(iter_result).__name__}"
                )
            for fr in iter_result:
                if not isinstance(fr, dict):
                    raise TypeError(
                        f"Invalid FlowResult entry: expected dict, got {type(fr).__name__}"
                    )
                metric = fr.get("metric")
                if metric != "placement_ratio":
                    raise ValueError(
                        f"Unexpected FlowResult metric: {metric!r} (expected 'placement_ratio')"
                    )
                src = str(fr.get("src", ""))
                dst = str(fr.get("dst", ""))
                prio = int(fr.get("priority", 0))
                ratio = float(fr.get("value", 0.0))
                per_demand_ratios[(src, dst, prio)].append(ratio)

                if (
                    self.include_flow_details
                    and cost_map is not None
                    and edge_counts is not None
                ):
                    stats = fr.get("stats") or {}
                    cd = (
                        stats.get("cost_distribution")
                        if isinstance(stats, dict)
                        else None
                    )
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

                    edges = stats.get("edges") if isinstance(stats, dict) else None
                    if isinstance(edges, list):
                        for e in edges:
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
                    raise KeyError(
                        f"Envelope not found for demand {key} during flow details aggregation"
                    )
                cost_stats: dict[float, dict[str, Any]] = {}
                for cost, vols in costs.items():
                    if vols:
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

        # INFO-level outcome summary for workflow users
        try:
            from ngraph.monte_carlo.results import DemandPlacementResults

            dpr = DemandPlacementResults(
                raw_results=results.raw_results,
                iterations=results.iterations,
                baseline=results.baseline,
                failure_patterns=results.failure_patterns,
                metadata=results.metadata,
            )

            # Compute per-iteration success rates and summary statistics
            dist_df = dpr.success_rate_distribution()
            stats = dpr.summary_statistics() if not dist_df.empty else {}

            # Also compute an overall demand-level mean from envelopes for validation
            try:
                envelope_means = [
                    float(env.get("mean", 0.0)) for env in envelopes.values()
                ]
                overall_envelope_mean = (
                    sum(envelope_means) / len(envelope_means) if envelope_means else 0.0
                )
            except Exception:
                overall_envelope_mean = 0.0

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
                    "demand_count": len(envelopes),
                    "success_rate_stats": stats or {},
                    "overall_envelope_mean": float(overall_envelope_mean),
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

            mean_v = float(stats.get("mean", 0.0)) if stats else 0.0
            p50_v = float(stats.get("p50", 0.0)) if stats else 0.0
            p95_v = float(stats.get("p95", 0.0)) if stats else 0.0
            min_v = float(stats.get("min", 0.0)) if stats else 0.0
            max_v = float(stats.get("max", 0.0)) if stats else 0.0

            duration_sec = time.perf_counter() - t0
            rounds_str = str(self.placement_rounds)
            seed_str = str(self.seed) if self.seed is not None else "-"
            baseline_str = str(meta.get("baseline", self.baseline))
            logger.info(
                (
                    "Placement summary: name=%s alpha=%.6g source=%s "
                    "demands=%d iters=%d workers=%d rounds=%s baseline=%s "
                    "seed=%s duration=%.3fs iter_mean=%.4f p50=%.4f p95=%.4f "
                    "min=%.4f max=%.4f env_mean=%.4f"
                ),
                self.name,
                alpha_value,
                alpha_source_str,
                len(envelopes),
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
                overall_envelope_mean,
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
