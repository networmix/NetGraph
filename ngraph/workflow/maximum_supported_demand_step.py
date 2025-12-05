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

import netgraph_core

from ngraph.exec.demand.expand import expand_demands
from ngraph.logging import get_logger
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset, create_flow_policy
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

        from ngraph.model.flow.policy_config import serialize_policy_preset

        base_demands: list[dict[str, Any]] = [
            {
                "source_path": getattr(td, "source_path", ""),
                "sink_path": getattr(td, "sink_path", ""),
                "demand": float(getattr(td, "demand", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy_config": serialize_policy_preset(
                    getattr(td, "flow_policy_config", None)
                ),
            }
            for td in base_tds
        ]

        # Validation: Ensure traffic matrix contains demands
        if not base_demands:
            raise ValueError(
                f"Traffic matrix '{self.matrix_name}' contains no demands. "
                "Cannot compute maximum supported demand without traffic specifications."
            )

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
    def _build_scaled_demands(
        base_demands: list[dict[str, Any]], alpha: float
    ) -> list[TrafficDemand]:
        """Build scaled traffic demands for alpha probe."""
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
        return demands

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
        """Evaluate if alpha is feasible using Core-based placement.

        Args:
            alpha: Scale factor to test.
            scenario: Scenario containing network and traffic matrix.
            matrix_name: Name of traffic matrix to use.
            placement_rounds: Placement rounds (unused - Core handles internally).
            seeds: Number of seeds to test.

        Returns:
            Tuple of (feasible, details_dict).
        """
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

        # Build scaled demands
        scaled_demands = cls._build_scaled_demands(base_demands, alpha)

        # Phase 1: Expand demands (get names + augmentations)
        expansion = expand_demands(
            scenario.network,
            scaled_demands,
            default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        )

        # Phase 2: Build Core infrastructure with augmentations
        from ngraph.analysis import AnalysisContext

        ctx = AnalysisContext.from_network(
            scenario.network,
            augmentations=expansion.augmentations,
        )

        # Build masks for disabled nodes/links (using internal methods)
        node_mask = ctx._build_node_mask(excluded_nodes=None)
        edge_mask = ctx._build_edge_mask(excluded_links=None)

        decisions: list[bool] = []
        min_ratios: list[float] = []

        for _ in range(max(1, int(seeds))):
            # Create fresh FlowGraph for each seed
            flow_graph = netgraph_core.FlowGraph(ctx.multidigraph)

            # Phase 3: Place demands using Core
            total_demand = 0.0
            total_placed = 0.0

            for demand in expansion.demands:
                # Resolve node names to IDs (includes pseudo nodes)
                src_id = ctx.node_mapper.to_id(demand.src_name)
                dst_id = ctx.node_mapper.to_id(demand.dst_name)

                policy = create_flow_policy(
                    ctx.algorithms,
                    ctx.handle,
                    demand.policy_preset,
                    node_mask=node_mask,
                    edge_mask=edge_mask,
                )

                placed, _ = policy.place_demand(
                    flow_graph,
                    src_id,
                    dst_id,
                    demand.priority,
                    demand.volume,
                )

                total_demand += demand.volume
                total_placed += placed

            # Validation: Ensure we have non-zero demand to evaluate
            if total_demand == 0.0:
                raise ValueError(
                    f"Cannot evaluate feasibility for alpha={alpha:.6g}: total demand is zero. "
                    "This indicates that no demands were successfully expanded or all demand volumes are zero."
                )

            # Check feasibility
            ratio = total_placed / total_demand
            is_feasible = ratio >= 1.0 - 1e-12
            decisions.append(is_feasible)
            min_ratios.append(ratio)

        # Majority vote across seeds
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
