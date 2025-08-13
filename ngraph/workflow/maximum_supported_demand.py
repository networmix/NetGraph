"""Maximum Supported Demand (MSD) search workflow step.

Search for the largest scaling factor ``alpha`` such that the selected traffic
matrix is feasible under the demand placement procedure. The search brackets a
feasible/infeasible interval, then performs bisection on feasibility.

This implementation provides the hard-feasibility rule only: every OD must be
fully placed. The step records search parameters, the decision rule, and the
original (unscaled) demands so the result is interpretable without the scenario.

YAML Configuration Example:
    ```yaml
    workflow:
      - step_type: MaximumSupportedDemandAnalysis
        name: msd_baseline_tm          # Optional step name
        matrix_name: baseline_traffic_matrix
        acceptance_rule: hard          # currently only 'hard' supported
        alpha_start: 1.0
        growth_factor: 2.0
        alpha_min: 1e-6
        alpha_max: 1e9
        resolution: 0.01
        max_bracket_iters: 16
        max_bisect_iters: 32
        seeds_per_alpha: 3
        placement_rounds: auto
    ```

Results stored in `scenario.results` under the step name:
    - alpha_star: Final feasible alpha (float)
    - context: Search parameters and decision rule (dict)
    - base_demands: Unscaled base demands for the matrix (list[dict])
    - probes: Per-alpha probe summaries with feasibility and placement ratio (list)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ngraph.demand.manager.manager import TrafficManager, TrafficResult
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.flows.policy import FlowPolicyConfig
from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

logger = get_logger(__name__)


@dataclass
class MaximumSupportedDemandAnalysis(WorkflowStep):
    """Search for Maximum Supported Demand (MSD) by scaling and bisection.

    Args:
        matrix_name: Name of the traffic matrix to scale and test.
        acceptance_rule: Only "hard" is implemented: all OD pairs must be fully placed.
        alpha_start: Initial guess for alpha.
        growth_factor: Factor g>1 to expand/shrink during bracketing.
        alpha_min: Minimum alpha allowed during bracketing.
        alpha_max: Maximum alpha allowed during bracketing.
        resolution: Stop when upper-lower <= resolution.
        max_bracket_iters: Limit on growth/shrink iterations during bracketing.
        max_bisect_iters: Limit on iterations during bisection.
        seeds_per_alpha: Number of repeated runs per alpha; alpha is feasible if
            majority of seeds satisfy the rule. Deterministic policies will yield identical results.
        placement_rounds: Rounds passed to TrafficManager.place_all_demands().
    """

    matrix_name: str = "default"
    acceptance_rule: str = "hard"
    alpha_start: float = 1.0
    growth_factor: float = 2.0
    alpha_min: float = 1e-6
    alpha_max: float = 1e9
    resolution: float = 0.01
    max_bracket_iters: int = 32
    max_bisect_iters: int = 32
    seeds_per_alpha: int = 1
    placement_rounds: int | str = "auto"

    def __post_init__(self) -> None:
        """Validate configuration parameters for early failure.

        Raises:
            ValueError: If any parameter is invalid (e.g., non-positive seeds or resolution).
        """
        if self.seeds_per_alpha < 1:
            raise ValueError("seeds_per_alpha must be >= 1")
        if self.growth_factor <= 1.0:
            # Duplicated at runtime guard, but validated early for clarity.
            raise ValueError("growth_factor must be > 1.0")
        if self.resolution <= 0.0:
            raise ValueError("resolution must be positive")

    def run(self, scenario: "Any") -> None:  # Scenario type at runtime
        """Execute MSD search and store results.

        The result is stored under this step name with keys:
          - "alpha_star": float
          - "context": dict of search/decision parameters
          - "base_demands": list of serializable demand dicts
          - "probes": list of per-alpha probe summaries
        """
        if self.acceptance_rule != "hard":
            raise ValueError("Only 'hard' acceptance_rule is implemented")

        t0 = time.perf_counter()
        logger.info(
            "Starting MSD analysis: name=%s matrix=%s alpha_start=%.6g growth=%.3f seeds=%d resolution=%.6g",
            self.name or self.__class__.__name__,
            self.matrix_name,
            float(self.alpha_start),
            float(self.growth_factor),
            int(self.seeds_per_alpha),
            float(self.resolution),
        )

        # Snapshot base demands for portability
        base_tds = scenario.traffic_matrix_set.get_matrix(self.matrix_name)
        base_demands: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": getattr(td, "flow_policy_config", None),
            }
            for td in base_tds
        ]

        # Debug: log base demand snapshot summary including an example and policy
        try:
            example = "-"
            if base_demands:
                ex = base_demands[0]
                src = str(ex.get("source_path", ""))
                dst = str(ex.get("sink_path", ""))
                dem = float(ex.get("demand", 0.0))
                cfg = ex.get("flow_policy_config")
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
                "Extracted %d base demands from matrix '%s' (example: %s)",
                len(base_demands),
                self.matrix_name,
                example,
            )
        except Exception:
            pass

        # Bracket: find feasible lower and infeasible upper (or the reverse)
        start_alpha = float(self.alpha_start)
        g = float(self.growth_factor)
        if not (g > 1.0):
            raise ValueError("growth_factor must be > 1.0")
        if self.resolution <= 0.0:
            raise ValueError("resolution must be positive")

        probes: list[dict[str, Any]] = []

        def probe(alpha: float) -> tuple[bool, dict[str, Any]]:
            feasible, details = self._evaluate_alpha(
                alpha=alpha,
                scenario=scenario,
                matrix_name=self.matrix_name,
                placement_rounds=self.placement_rounds,
                seeds=self.seeds_per_alpha,
            )
            probe_entry = {
                "alpha": alpha,
                "feasible": bool(feasible),
            } | details
            probes.append(probe_entry)
            return feasible, details

        # Evaluate starting alpha
        feasible0, _ = probe(start_alpha)

        lower: float | None = None
        upper: float | None = None

        if feasible0:
            lower = start_alpha
            alpha = start_alpha
            for _ in range(self.max_bracket_iters):
                alpha = min(alpha * g, self.alpha_max)
                if alpha == lower:  # reached max bound
                    break
                feas, _ = probe(alpha)
                if not feas:
                    upper = alpha
                    break
                lower = alpha
            if upper is None:
                # Could not find infeasible bound up to alpha_max
                upper = min(self.alpha_max, lower + max(self.resolution, 1.0))
        else:
            upper = start_alpha
            alpha = start_alpha
            for _ in range(self.max_bracket_iters):
                alpha = max(alpha / g, self.alpha_min)
                if alpha == upper:  # reached min bound
                    break
                feas, _ = probe(alpha)
                if feas:
                    lower = alpha
                    break
                upper = alpha
            if lower is None:
                raise ValueError("No feasible alpha found above alpha_min")

        assert lower is not None and upper is not None and lower < upper

        # Bisection on feasibility
        left = lower
        right = upper
        iters = 0
        while (right - left) > self.resolution and iters < self.max_bisect_iters:
            mid = (left + right) / 2.0
            feas, _ = probe(mid)
            if feas:
                left = mid
            else:
                right = mid
            iters += 1

        alpha_star = left

        # Store results
        context = {
            "acceptance_rule": self.acceptance_rule,
            "alpha_start": self.alpha_start,
            "growth_factor": self.growth_factor,
            "alpha_min": self.alpha_min,
            "alpha_max": self.alpha_max,
            "resolution": self.resolution,
            "max_bracket_iters": self.max_bracket_iters,
            "max_bisect_iters": self.max_bisect_iters,
            "seeds_per_alpha": self.seeds_per_alpha,
            "matrix_name": self.matrix_name,
            "placement_rounds": self.placement_rounds,
        }

        step_name = self.name
        scenario.results.put(step_name, "alpha_star", alpha_star)
        scenario.results.put(step_name, "context", context)
        scenario.results.put(step_name, "base_demands", base_demands)
        scenario.results.put(step_name, "probes", probes)

        # INFO-level outcome summary for CLI logs
        try:
            feasible_seeds = 0
            min_ratio = 1.0
            total_probes = len(probes)
            bracket_iters = min(self.max_bracket_iters, total_probes)
            if probes:
                # Find probe closest to alpha_star (last feasible 'left')
                # We logged probes in evaluation order; take the last feasible
                last_feasible = None
                for pr in probes:
                    if (
                        bool(pr.get("feasible"))
                        and float(pr.get("alpha", -1.0)) <= alpha_star + 1e-12
                    ):
                        last_feasible = pr
                if last_feasible is None:
                    last_feasible = probes[-1]
                feasible_seeds = int(last_feasible.get("feasible_seeds", 0))
                min_ratio = float(last_feasible.get("min_placement_ratio", 0.0))

            logger.info(
                (
                    "MSD summary: name=%s matrix=%s alpha_star=%.6g resolution=%.6g "
                    "probes=%d bracket_iters=%d bisect_iters=%d seeds_per_alpha=%d "
                    "duration=%.3fs feasible_seeds=%d min_ratio=%.3f"
                ),
                self.name or self.__class__.__name__,
                self.matrix_name,
                float(alpha_star),
                float(self.resolution),
                total_probes,
                bracket_iters,
                iters,
                int(self.seeds_per_alpha),
                time.perf_counter() - t0,
                feasible_seeds,
                min_ratio,
            )
        except Exception:
            # Logging must not raise
            pass

    # --- Helpers -------------------------------------------------------------

    @staticmethod
    def _build_scaled_matrix(
        base_demands: list[dict[str, Any]], alpha: float
    ) -> TrafficMatrixSet:
        """Create a temporary ``TrafficMatrixSet`` with scaled demands.

        Args:
            base_demands: Serializable base demand dicts.
            alpha: Scaling factor to apply to each demand value.

        Returns:
            A ``TrafficMatrixSet`` containing a single matrix named "temp".
        """
        tmset = TrafficMatrixSet()
        demands: list[TrafficDemand] = []
        for d in base_demands:
            demands.append(
                TrafficDemand(
                    source_path=str(d["source_path"]),
                    sink_path=str(d["sink_path"]),
                    priority=int(d["priority"]),
                    demand=float(d["demand"]) * alpha,
                    flow_policy_config=d.get("flow_policy_config"),
                    mode=str(d.get("mode", "pairwise")),
                )
            )
        tmset.add("temp", demands)
        return tmset

    @classmethod
    def _evaluate_alpha(
        cls,
        *,
        alpha: float,
        scenario: Any,
        matrix_name: str,
        placement_rounds: int | str,
        seeds: int,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate feasibility at ``alpha`` with majority voting over seeds.

        Args:
            alpha: Demand scaling factor to test.
            scenario: Scenario providing network and matrix set.
            matrix_name: Name of the base traffic matrix to scale.
            placement_rounds: Rounds for the placement routine.
            seeds: Number of repetitions per alpha; majority vote determines feasibility.

        Returns:
            Tuple (feasible, details) where ``details`` includes ``seeds``,
            ``feasible_seeds``, and ``min_placement_ratio`` across the seeds.
        """
        # Snapshot base matrix once
        base_tds = scenario.traffic_matrix_set.get_matrix(matrix_name)
        base_demands: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": getattr(td, "flow_policy_config", None),
            }
            for td in base_tds
        ]

        decisions: list[bool] = []
        min_ratios: list[float] = []

        # Build scaled matrix once per alpha and reuse a single TrafficManager across seeds
        tmset = cls._build_scaled_matrix(base_demands, alpha)
        tm = TrafficManager(
            network=scenario.network,
            traffic_matrix_set=tmset,
            matrix_name="temp",
        )
        tm.build_graph(add_reverse=True)

        for _ in range(max(1, int(seeds))):
            # Reset flows and re-expand demands idempotently
            tm.reset_all_flow_usages()
            tm.expand_demands()
            tm.place_all_demands(placement_rounds=placement_rounds)

            # Aggregate top-level placement ratios
            results: list[TrafficResult] = tm.get_traffic_results(detailed=False)
            ratios: list[float] = []
            for r in results:
                total = float(r.total_volume)
                placed = float(r.placed_volume)
                ratio = 1.0 if total == 0.0 else (placed / total)
                ratios.append(ratio)

            is_feasible = all(r >= 1.0 - 1e-12 for r in ratios)
            decisions.append(is_feasible)
            min_ratios.append(min(ratios) if ratios else 1.0)

        # Majority decision
        yes = sum(1 for d in decisions if d)
        required = (len(decisions) // 2) + 1
        feasible = yes >= required

        details = {
            "seeds": len(decisions),
            "feasible_seeds": yes,
            "min_placement_ratio": min(min_ratios) if min_ratios else 1.0,
        }
        return feasible, details


# Register the workflow step
register_workflow_step("MaximumSupportedDemandAnalysis")(MaximumSupportedDemandAnalysis)
