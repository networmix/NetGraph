"""MaximumSupportedDemand workflow step.

Searches for the maximum uniform traffic multiplier `alpha_star` that is fully
placeable for a given demand set. Stores results under `data` as:

- `alpha_star`: float
- `context`: parameters used for the search
- `base_demands`: serialized base demand specs
- `probes`: bracket/bisect evaluations with feasibility

Performance: AnalysisContext is built once at search start and reused across
all binary search probes. Only demand volumes change per probe.

YAML Configuration Example:
    ```yaml
    workflow:
      - type: MaximumSupportedDemand
        name: "msd_search"
        demand_set: "default"
        resolution: 0.01        # Convergence threshold
        max_bisect_iters: 50    # Maximum bisection iterations
        alpha_start: 1.0        # Starting multiplier
        growth_factor: 2.0      # Bracket expansion factor
    ```
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from dataclasses import field as dataclasses_field
from typing import TYPE_CHECKING, Any

import netgraph_core
import numpy as np

from ngraph.analysis.demand import ExpandedDemand
from ngraph.analysis.functions import build_demand_placement_inputs
from ngraph.analysis.placement import place_demands
from ngraph.logging import get_logger
from ngraph.model.demand.spec import TrafficDemand
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
    # Persistent base-SPF DAG cache shared by all probes (masks never change
    # during MSD, so cached DAGs stay valid across alpha evaluations).
    dag_cache: dict = dataclasses_field(default_factory=dict)


@dataclass
class MaximumSupportedDemand(WorkflowStep):
    """Finds the maximum uniform traffic multiplier that is fully placeable.

    Binary search yields alpha_star: the largest multiplier at which every
    demand in the set still places fully on the network.

    Attributes:
        demand_set: Name of the demand set to analyze.
        acceptance_rule: Currently only "hard" is implemented; anything else
            raises ValueError at run time.
        alpha_start: Starting multiplier for binary search.
        growth_factor: Factor for bracket expansion; must be > 1.0.
        alpha_min: Minimum allowed alpha value.
        alpha_max: Maximum allowed alpha value.
        resolution: Convergence threshold for binary search; must be positive.
        max_bracket_iters: Maximum iterations for bracketing phase.
        max_bisect_iters: Maximum iterations for bisection phase.
        placement_rounds: Deprecated; accepted for backward compatibility but
            has no effect (placement optimization is handled by the core engine).
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
    placement_rounds: int | str = "auto"

    def __post_init__(self) -> None:
        if self.placement_rounds != "auto":
            logger.warning(
                "MaximumSupportedDemand 'placement_rounds' is deprecated and has "
                "no effect; placement optimization is handled by the core engine."
            )
        try:
            self.alpha_start = float(self.alpha_start)
            self.growth_factor = float(self.growth_factor)
            self.alpha_min = float(self.alpha_min)
            self.alpha_max = float(self.alpha_max)
            self.resolution = float(self.resolution)
            self.max_bracket_iters = int(self.max_bracket_iters)
            self.max_bisect_iters = int(self.max_bisect_iters)
        except Exception as exc:
            raise ValueError(f"Invalid MSD parameter type: {exc}") from exc
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
            "growth=%.3f resolution=%.6g",
            self.demand_set,
            float(self.alpha_start),
            float(self.growth_factor),
            float(self.resolution),
        )

        # Serialize base demands for result output
        base_tds = scenario.demand_set.get_set(self.demand_set)
        base_demands: list[dict[str, Any]] = [td.to_dict() for td in base_tds]

        if not base_demands:
            raise ValueError(
                f"Demand set '{self.demand_set}' contains no demands. "
                "Cannot compute maximum supported demand without traffic specifications."
            )

        # Build cache once for all probes
        cache = self._build_cache(scenario, base_tds)
        logger.debug(
            "MSD cache built: %d expanded demands",
            len(cache.base_expanded),
        )

        # Binary search
        probes: list[dict[str, Any]] = []

        def probe(alpha: float) -> tuple[bool, dict[str, Any]]:
            feasible, details = self._evaluate_alpha(cache, alpha)
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
            "demand_set": self.demand_set,
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
                # All probed alphas were feasible.
                # If lower has reached alpha_max, the answer is alpha_max.
                if lower >= self.alpha_max:
                    return lower
                # Bracket iters exhausted before reaching alpha_max.
                # Probe alpha_max directly.
                feas, _ = probe(self.alpha_max)
                if feas:
                    return self.alpha_max
                # alpha_max is infeasible: valid bracket for bisection.
                upper = self.alpha_max
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
                # Mirror the upward branch: bracket iterations can run out
                # before the halving sequence reaches alpha_min (e.g. a large
                # alpha_start), so probe alpha_min directly before giving up.
                if upper <= self.alpha_min:
                    raise ValueError("No feasible alpha found above alpha_min")
                feas, _ = probe(self.alpha_min)
                if not feas:
                    raise ValueError("No feasible alpha found above alpha_min")
                lower = self.alpha_min

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
    def _build_cache(scenario: Any, base_tds: list[TrafficDemand]) -> _MSDCache:
        """Build cache for MSD binary search.

        Reuses build_demand_placement_inputs for the expand-once context and
        resolved node IDs, then adds the no-exclusion masks shared by all
        probes. TrafficDemand ids are stable, so pseudo-node names (which
        embed them) stay consistent across probes. Called once at search
        start.
        """
        ctx, expansion, resolved_ids = build_demand_placement_inputs(
            scenario.network,
            [{**td.to_dict(), "flow_policy": td.flow_policy} for td in base_tds],
        )

        # Build masks once (no exclusions during MSD)
        node_mask = ctx.build_node_mask(excluded_nodes=None)
        edge_mask = ctx.build_edge_mask(excluded_links=None)

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
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate if alpha is feasible.

        Uses pre-built cache; only scales demand volumes by alpha.
        Placement is deterministic so a single evaluation is sufficient.
        """
        ctx = cache.ctx
        volumes = [d.volume * alpha for d in cache.base_expanded]

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
            dag_cache=cache.dag_cache,
        )

        if result.summary.total_demand == 0.0:
            raise ValueError(
                f"Cannot evaluate feasibility for alpha={alpha:.6g}: "
                "total demand is zero."
            )

        return result.summary.is_feasible, {
            "placement_ratio": result.summary.ratio,
        }


register_workflow_step("MaximumSupportedDemand")(MaximumSupportedDemand)
