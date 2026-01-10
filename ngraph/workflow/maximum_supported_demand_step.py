"""MaximumSupportedDemand workflow step.

Searches for the maximum uniform traffic multiplier `alpha_star` that is fully
placeable for a given demand set. Stores results under `data` as:

- `alpha_star`: float
- `context`: parameters used for the search
- `base_demands`: serialized base demand specs
- `probes`: bracket/bisect evaluations with feasibility

Performance: AnalysisContext is built once at search start and reused across
all binary search probes. Only demand volumes change per probe.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import netgraph_core
import numpy as np

from ngraph.analysis.demand import ExpandedDemand, expand_demands
from ngraph.analysis.placement import place_demands
from ngraph.logging import get_logger
from ngraph.model.demand.spec import TrafficDemand
from ngraph.model.flow.policy_config import FlowPolicyPreset
from ngraph.workflow.base import WorkflowStep, register_workflow_step

if TYPE_CHECKING:
    from ngraph.analysis import AnalysisContext

logger = get_logger(__name__)


@dataclass
class _MSDCache:
    """Cache for MSD binary search.

    Attributes:
        ctx: Pre-built AnalysisContext with augmentations.
        node_mask: Pre-built node mask (no exclusions during MSD).
        edge_mask: Pre-built edge mask (no exclusions during MSD).
        base_expanded: Expanded demands with base volumes.
        resolved_ids: Pre-resolved (src_id, dst_id) pairs.
    """

    ctx: "AnalysisContext"
    node_mask: np.ndarray
    edge_mask: np.ndarray
    base_expanded: list[ExpandedDemand]
    resolved_ids: list[tuple[int, int]]


@dataclass
class MaximumSupportedDemand(WorkflowStep):
    """Finds the maximum uniform traffic multiplier that is fully placeable.

    Uses binary search to find alpha_star, the maximum multiplier for all
    demands in the set that can still be fully placed on the network.

    Attributes:
        demand_set: Name of the demand set to analyze.
        acceptance_rule: Currently only "hard" is implemented.
        alpha_start: Starting multiplier for binary search.
        growth_factor: Factor for bracket expansion.
        alpha_min: Minimum allowed alpha value.
        alpha_max: Maximum allowed alpha value.
        resolution: Convergence threshold for binary search.
        max_bracket_iters: Maximum iterations for bracketing phase.
        max_bisect_iters: Maximum iterations for bisection phase.
        seeds_per_alpha: Number of placement attempts per alpha probe.
        placement_rounds: Placement optimization rounds.
    """

    demand_set: str = "default"
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
        logger.info("Starting MaximumSupportedDemand: name=%s", self.name)
        logger.debug(
            "MaximumSupportedDemand params: demand_set=%s alpha_start=%.6g "
            "growth=%.3f seeds=%d resolution=%.6g",
            self.demand_set,
            float(self.alpha_start),
            float(self.growth_factor),
            int(self.seeds_per_alpha),
            float(self.resolution),
        )

        # Serialize base demands for result output
        from ngraph.model.flow.policy_config import serialize_policy_preset

        base_tds = scenario.demand_set.get_set(self.demand_set)
        base_demands: list[dict[str, Any]] = [
            {
                "id": getattr(td, "id", None),
                "source": getattr(td, "source", ""),
                "target": getattr(td, "target", ""),
                "volume": float(getattr(td, "volume", 0.0)),
                "mode": getattr(td, "mode", "pairwise"),
                "priority": int(getattr(td, "priority", 0)),
                "flow_policy": serialize_policy_preset(
                    getattr(td, "flow_policy", None)
                ),
            }
            for td in base_tds
        ]

        if not base_demands:
            raise ValueError(
                f"Demand set '{self.demand_set}' contains no demands. "
                "Cannot compute maximum supported demand without traffic specifications."
            )

        # Build cache once for all probes
        cache = self._build_cache(scenario, self.demand_set)
        logger.debug(
            "MSD cache built: %d expanded demands",
            len(cache.base_expanded),
        )

        # Binary search
        probes: list[dict[str, Any]] = []

        def probe(alpha: float) -> tuple[bool, dict[str, Any]]:
            feasible, details = self._evaluate_alpha(cache, alpha, self.seeds_per_alpha)
            probes.append({"alpha": alpha, "feasible": bool(feasible)} | details)
            return feasible, details

        alpha_star = self._binary_search(probe)

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
            "demand_set": self.demand_set,
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
            "MaximumSupportedDemand completed: name=%s alpha_star=%.6g probes=%d duration=%.3fs",
            self.name,
            float(alpha_star),
            len(probes),
            time.perf_counter() - t0,
        )

    def _binary_search(self, probe: "Any") -> float:
        """Bracket and bisect to find alpha_star."""
        start_alpha = float(self.alpha_start)
        g = float(self.growth_factor)

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

        left, right = lower, upper
        for _ in range(self.max_bisect_iters):
            if (right - left) <= self.resolution:
                break
            mid = (left + right) / 2.0
            feas, _ = probe(mid)
            if feas:
                left = mid
            else:
                right = mid

        return left

    @staticmethod
    def _build_cache(scenario: Any, demand_set_name: str) -> _MSDCache:
        """Build cache for MSD binary search.

        Creates stable TrafficDemand objects, expands them once, and builds
        AnalysisContext. Called once at search start.
        """
        from ngraph.analysis import AnalysisContext

        base_tds = scenario.demand_set.get_set(demand_set_name)

        # Create stable TrafficDemand objects (same IDs for all probes)
        stable_demands: list[TrafficDemand] = [
            TrafficDemand(
                id=getattr(td, "id", "") or "",
                source=getattr(td, "source", ""),
                target=getattr(td, "target", ""),
                priority=int(getattr(td, "priority", 0)),
                volume=float(getattr(td, "volume", 0.0)),
                flow_policy=getattr(td, "flow_policy", None),
                mode=str(getattr(td, "mode", "pairwise")),
                group_mode=str(getattr(td, "group_mode", "flatten")),
            )
            for td in base_tds
        ]

        # Expand once (augmentations depend on td.id, now stable)
        expansion = expand_demands(
            scenario.network,
            stable_demands,
            default_policy_preset=FlowPolicyPreset.SHORTEST_PATHS_ECMP,
        )

        # Build AnalysisContext once
        ctx = AnalysisContext.from_network(
            scenario.network,
            augmentations=expansion.augmentations,
        )

        # Build masks once (no exclusions during MSD)
        node_mask = ctx._build_node_mask(excluded_nodes=None)
        edge_mask = ctx._build_edge_mask(excluded_links=None)

        # Pre-resolve node IDs once
        resolved_ids = [
            (ctx.node_mapper.to_id(d.src_name), ctx.node_mapper.to_id(d.dst_name))
            for d in expansion.demands
        ]

        return _MSDCache(
            ctx=ctx,
            node_mask=node_mask,
            edge_mask=edge_mask,
            base_expanded=expansion.demands,
            resolved_ids=resolved_ids,
        )

    @staticmethod
    def _evaluate_alpha(
        cache: _MSDCache,
        alpha: float,
        seeds: int,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate if alpha is feasible.

        Uses pre-built cache; only scales demand volumes by alpha.
        """
        ctx = cache.ctx
        decisions: list[bool] = []
        min_ratios: list[float] = []

        # Pre-compute scaled volumes once per alpha
        volumes = [d.volume * alpha for d in cache.base_expanded]

        for _ in range(max(1, int(seeds))):
            flow_graph = netgraph_core.FlowGraph(ctx.multidigraph)

            result = place_demands(
                cache.base_expanded,
                volumes,
                flow_graph,
                ctx,
                cache.node_mask,
                cache.edge_mask,
                resolved_ids=cache.resolved_ids,
                collect_entries=False,
            )

            if result.summary.total_demand == 0.0:
                raise ValueError(
                    f"Cannot evaluate feasibility for alpha={alpha:.6g}: "
                    "total demand is zero."
                )

            decisions.append(result.summary.is_feasible)
            min_ratios.append(result.summary.ratio)

        yes = sum(1 for d in decisions if d)
        required = (len(decisions) // 2) + 1
        feasible = yes >= required

        return feasible, {
            "seeds": len(decisions),
            "feasible_seeds": yes,
            "min_placement_ratio": min(min_ratios) if min_ratios else 1.0,
        }

    @staticmethod
    def _build_scaled_demands(
        base_demands: list[dict[str, Any]], alpha: float
    ) -> list[TrafficDemand]:
        """Build scaled TrafficDemand objects from serialized demands.

        Utility for tests to verify results at specific alpha values.
        Preserves ID if present for context caching compatibility.
        """
        return [
            TrafficDemand(
                id=d.get("id") or "",
                source=d["source"],
                target=d["target"],
                priority=int(d["priority"]),
                volume=float(d["volume"]) * alpha,
                flow_policy=d.get("flow_policy"),
                mode=str(d.get("mode", "pairwise")),
                group_mode=str(d.get("group_mode", "flatten")),
            )
            for d in base_demands
        ]


register_workflow_step("MaximumSupportedDemand")(MaximumSupportedDemand)
