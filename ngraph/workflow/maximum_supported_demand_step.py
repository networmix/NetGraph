"""Maximum Supported Demand (MSD) workflow step.

Searches for the maximum uniform traffic multiplier `alpha_star` that is fully
placeable for a given matrix. Stores results under `data` as:

- `alpha_star`: float
- `context`: parameters used for the search
- `base_demands`: serialized base demand specs
- `probes`: bracket/bisect evaluations with feasibility
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ngraph.demand.manager.manager import TrafficManager, TrafficResult
from ngraph.demand.matrix import TrafficMatrixSet
from ngraph.demand.spec import TrafficDemand
from ngraph.logging import get_logger
from ngraph.workflow.base import WorkflowStep, register_workflow_step

logger = get_logger(__name__)


@dataclass
class MaximumSupportedDemand(WorkflowStep):
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
        try:
            self.alpha_start = float(self.alpha_start)
            self.growth_factor = float(self.growth_factor)
            self.alpha_min = float(self.alpha_min)
            self.alpha_max = float(self.alpha_max)
            self.resolution = float(self.resolution)
            self.max_bracket_iters = int(self.max_bracket_iters)
            self.max_bisect_iters = int(self.max_bisect_iters)
            self.seeds_per_alpha = int(self.seeds_per_alpha)
        except Exception as exc:
            raise ValueError(f"Invalid MSD parameter type: {exc}") from exc
        if self.seeds_per_alpha < 1:
            raise ValueError("seeds_per_alpha must be >= 1")
        if self.growth_factor <= 1.0:
            raise ValueError("growth_factor must be > 1.0")
        if self.resolution <= 0.0:
            raise ValueError("resolution must be positive")

    def run(self, scenario: "Any") -> None:
        if self.acceptance_rule != "hard":
            raise ValueError("Only 'hard' acceptance_rule is implemented")
        t0 = time.perf_counter()
        logger.info(
            "Starting MSD: name=%s matrix=%s alpha_start=%.6g growth=%.3f seeds=%d resolution=%.6g",
            self.name or self.__class__.__name__,
            self.matrix_name,
            float(self.alpha_start),
            float(self.growth_factor),
            int(self.seeds_per_alpha),
            float(self.resolution),
        )
        base_tds = scenario.traffic_matrix_set.get_matrix(self.matrix_name)

        def _serialize_policy(cfg: Any) -> Any:
            try:
                from ngraph.flows.policy import (
                    FlowPolicyConfig,  # local import to avoid heavy deps
                )
            except Exception:  # pragma: no cover - defensive
                return str(cfg) if cfg is not None else None
            if cfg is None:
                return None
            if isinstance(cfg, FlowPolicyConfig):
                return cfg.name
            try:
                return FlowPolicyConfig(int(cfg)).name
            except Exception:
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
            for td in base_tds
        ]

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
            probe_entry = {"alpha": alpha, "feasible": bool(feasible)} | details
            probes.append(probe_entry)
            return feasible, details

        feasible0, _ = probe(start_alpha)
        lower: float | None = None
        upper: float | None = None
        if feasible0:
            lower = start_alpha
            alpha = start_alpha
            for _ in range(self.max_bracket_iters):
                alpha = min(alpha * g, self.alpha_max)
                if alpha == lower:
                    break
                feas, _ = probe(alpha)
                if not feas:
                    upper = alpha
                    break
                lower = alpha
            if upper is None:
                upper = min(self.alpha_max, lower + max(self.resolution, 1.0))
        else:
            upper = start_alpha
            alpha = start_alpha
            for _ in range(self.max_bracket_iters):
                alpha = max(alpha / g, self.alpha_min)
                if alpha == upper:
                    break
                feas, _ = probe(alpha)
                if feas:
                    lower = alpha
                    break
                upper = alpha
            if lower is None:
                raise ValueError("No feasible alpha found above alpha_min")

        assert lower is not None and upper is not None and lower < upper
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
        scenario.results.put("metadata", {})
        scenario.results.put(
            "data",
            {
                "alpha_star": float(alpha_star),
                "context": context,
                "base_demands": base_demands,
                "probes": probes,
            },
        )
        logger.info(
            "MSD completed: name=%s matrix=%s alpha_star=%.6g iterations=%d duration=%.3fs",
            self.name or self.__class__.__name__,
            self.matrix_name,
            float(alpha_star),
            int(self.max_bisect_iters),
            time.perf_counter() - t0,
        )

    @staticmethod
    def _build_scaled_matrix(
        base_demands: list[dict[str, Any]], alpha: float
    ) -> TrafficMatrixSet:
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
        tmset = cls._build_scaled_matrix(base_demands, alpha)
        tm = TrafficManager(
            network=scenario.network, traffic_matrix_set=tmset, matrix_name="temp"
        )
        tm.build_graph(add_reverse=True)
        for _ in range(max(1, int(seeds))):
            tm.reset_all_flow_usages()
            tm.expand_demands()
            tm.place_all_demands(placement_rounds=placement_rounds)
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
        yes = sum(1 for d in decisions if d)
        required = (len(decisions) // 2) + 1
        feasible = yes >= required
        details = {
            "seeds": len(decisions),
            "feasible_seeds": yes,
            "min_placement_ratio": min(min_ratios) if min_ratios else 1.0,
        }
        return feasible, details


register_workflow_step("MaximumSupportedDemand")(MaximumSupportedDemand)
