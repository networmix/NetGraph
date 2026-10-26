"""Bounded physical-alpha search on one persistent native policy roster."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING

import netgraph_core as ngc

from ngraph.analysis.demands import scaled_expansion
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.placement import (
    _apply_matrix,
    _observation_records,
    policy_roster,
    remove_policies,
)
from ngraph.analysis.precision import placement_inputs, placement_miss
from ngraph.analysis.totals import placement_totals
from ngraph.analysis.units import UnitRangeError
from ngraph.results import (
    MSDAnalysis,
    MSDProbe,
    OutputSelection,
    PlacementRow,
    RangeRefusal,
    ReportLocation,
    ResolvedDemandSet,
    UpperCertificate,
    exact_alpha,
)
from ngraph.utils.values import flag, integer, own, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class MSDQuery:
    demands: ResolvedDemandSet
    alpha_start: float = 1.0
    growth_factor: float = 2.0
    alpha_min: float = 1e-6
    alpha_max: float = 1e9
    alpha_tolerance: float = 0.01
    max_bracket_iters: int = 32
    max_bisect_iters: int = 32
    export_probe_rows: bool = False

    export_details: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.demands, ResolvedDemandSet):
            raise TypeError(
                f"msd.demands: expected ResolvedDemandSet, got {self.demands!r}"
            )
        raw_growth = self.growth_factor
        raw_bounds = (self.alpha_min, self.alpha_start, self.alpha_max)
        for name in (
            "alpha_start",
            "growth_factor",
            "alpha_min",
            "alpha_max",
            "alpha_tolerance",
        ):
            object.__setattr__(
                self, name, physical(getattr(self, name), f"msd.{name}", positive=True)
            )
        if self.growth_factor <= 1:
            raise ValueError(f"msd.growth_factor: must exceed 1, got {raw_growth!r}")
        if not self.alpha_min <= self.alpha_start <= self.alpha_max:
            raise ValueError(
                "msd: require alpha_min <= alpha_start <= alpha_max, "
                f"got {raw_bounds!r}"
            )
        own(
            self,
            max_bracket_iters=integer(
                self.max_bracket_iters, "msd.max_bracket_iters", minimum=1
            ),
            max_bisect_iters=integer(
                self.max_bisect_iters, "msd.max_bisect_iters", minimum=1
            ),
            export_probe_rows=flag(self.export_probe_rows, "msd.export_probe_rows"),
            export_details=flag(self.export_details, "export_details"),
        )


def _proof(demands: ResolvedDemandSet):
    positive_parents = {
        parent.base_id
        for parent in demands.expansion_template
        if parent.physical_volume > 0
    }
    if not any(demand.base_id in positive_parents for demand in demands.demands):
        return "nothing_offered"
    fixed = True
    for demand in demands.demands:
        model = demand.config.routing
        if isinstance(model, ngc.Pinned):
            continue
        if not isinstance(model, ngc.ShortestPaths):
            fixed = False
            break
        if model.tie_break not in (
            ngc.RouteTieBreak.FEWER_HOPS,
            ngc.RouteTieBreak.HIGHER_CAPACITY,
        ):
            fixed = False
            break
        if (
            model.allocation == ngc.RouteAllocation.OPTIMIZED
            or model.weight_basis == ngc.WeightBasis.RESIDUAL_SNAPSHOT
        ):
            fixed = False
            break
    if fixed:
        return "fixed_program"
    if len(demands.demands) == 1:
        model = demands.demands[0].config.routing
        if isinstance(model, ngc.CentralizedTE) and model.tunnel_count is None:
            return "single_controller"
        if (
            isinstance(model, ngc.ShortestPaths)
            and model.allocation == ngc.RouteAllocation.OPTIMIZED
            and model.tie_break
            in (ngc.RouteTieBreak.FEWER_HOPS, ngc.RouteTieBreak.HIGHER_CAPACITY)
        ):
            return "single_controller"
    return "unproved"


def maximum_supported_demand(
    prepared: PreparedScenario, query: MSDQuery
) -> MSDAnalysis:
    topology = prepared.topology
    demands = query.demands
    proof = _proof(demands)
    ledger, owners = policy_roster(topology, demands.demands, topology.disabled)
    history, misses = [], []
    best = None
    best_rows = best_accounting = None
    retained = {} if query.export_probe_rows else None
    positive_parents = {
        p.base_id for p in demands.expansion_template if p.physical_volume > 0
    }

    def rows_of(requests, results):
        return tuple(
            PlacementRow(
                demand.id,
                demand.base_id,
                demand.endpoints,
                request,
                result,
                demand.pool,
                None,
                MappingProxyType({}),
            )
            for demand, request, result in zip(
                demands.demands, requests, results, strict=True
            )
        )

    def probe(alpha):
        nonlocal best, best_rows, best_accounting
        # All prior traffic and holds leave before quantization or native work.
        remove_policies(owners)
        index = len(history)
        exact = exact_alpha(alpha)
        try:
            amounts, accounting = scaled_expansion(demands, exact.value, topology.q)
        except UnitRangeError as exc:
            refusal = RangeRefusal(exc.label, exc.reason, str(exc), exc.binary64_hex)
            history.append(MSDProbe(index, exact, "range", None, refusal))
            return "range"
        requests = tuple(amounts[demand.id] for demand in demands.demands)
        results = _apply_matrix(ledger, owners, requests)
        records = _observation_records(prepared._named, demands, owners)
        totals = placement_totals(
            zip(
                (demand.id for demand in demands.demands),
                requests,
                results,
                strict=True,
            )
        )
        below_resolution = any(
            request == 0 and demand.base_id in positive_parents
            for demand, request in zip(demands.demands, requests, strict=True)
        )
        outcome = (
            "below_resolution"
            if below_resolution
            else ("feasible" if totals.feasible else "infeasible")
        )
        miss = placement_miss(
            prepared,
            demands,
            owners,
            results,
            records,
            topology.disabled,
            exact.value,
            ReportLocation(None, "baseline", index),
            placement_inputs(prepared, demands, exact.value),
        )
        if miss is not None:
            misses.append(miss)
        history.append(MSDProbe(index, exact, outcome, totals, None))
        better = outcome == "feasible" and (
            best is None or alpha > history[best].alpha.value
        )
        # Rows are built only for a retained probe or a new best one.
        rows = rows_of(requests, results) if better or retained is not None else None
        if retained is not None:
            retained[index] = rows
        if better:
            best, best_rows, best_accounting = index, rows, accounting
        return outcome

    def below(alpha):
        amounts, _ = scaled_expansion(demands, alpha, topology.q)
        return any(
            amounts[demand.id] == 0 and demand.base_id in positive_parents
            for demand in demands.demands
        )

    def unit_threshold(lower, upper):
        # Positive binary64 bit patterns have the same order as their values.
        # Search only rounding, then evaluate the first resolvable alpha once.
        low = struct.unpack(">Q", struct.pack(">d", lower))[0]
        high = struct.unpack(">Q", struct.pack(">d", upper))[0]
        while high - low > 1:
            middle = (low + high) // 2
            alpha = struct.unpack(">d", struct.pack(">Q", middle))[0]
            if below(alpha):
                low = middle
            else:
                high = middle
        return struct.unpack(">d", struct.pack(">Q", high))[0]

    status, reason = "limit", "bracket_limit"
    try:
        if proof == "nothing_offered":
            if probe(query.alpha_max) == "range":
                status, reason = "range", "offer_range"
            else:
                status, reason = "trivial", "nothing_offered"
        else:
            alpha = float(query.alpha_start)
            lower = upper = None
            for _iteration in range(query.max_bracket_iters):
                outcome = probe(alpha)
                if outcome == "range":
                    status, reason = "range", "offer_range"
                    break
                if outcome in ("feasible", "below_resolution"):
                    lower = alpha if lower is None else max(lower, alpha)
                else:
                    upper = alpha if upper is None else min(upper, alpha)
                if lower is not None and upper is not None and lower < upper:
                    break
                if outcome in ("feasible", "below_resolution"):
                    next_alpha = min(
                        float(query.alpha_max), alpha * float(query.growth_factor)
                    )
                    bound = query.alpha_max
                else:
                    next_alpha = max(
                        float(query.alpha_min), alpha / float(query.growth_factor)
                    )
                    bound = query.alpha_min
                if alpha == bound:
                    status, reason = "limit", "alpha_bound"
                    break
                if next_alpha == alpha:
                    status, reason = "stagnation", "representable_limit"
                    break
                alpha = next_alpha
            else:
                status, reason = "limit", "bracket_limit"
            if (
                status not in ("range", "stagnation")
                and lower is not None
                and upper is not None
                and lower < upper
            ):
                for _iteration in range(query.max_bisect_iters):
                    if upper - lower <= query.alpha_tolerance:
                        if best is None and below(lower):
                            threshold = unit_threshold(lower, upper)
                            outcome = (
                                "infeasible" if threshold == upper else probe(threshold)
                            )
                            if outcome == "feasible":
                                lower = threshold
                                continue
                            if outcome == "range":
                                status, reason = "range", "offer_range"
                            else:
                                status, reason = "none_feasible", "unit_resolution"
                            break
                        status, reason = "feasible", "tolerance"
                        break
                    midpoint = lower + (upper - lower) / 2
                    if not lower < midpoint < upper:
                        status, reason = "stagnation", "representable_limit"
                        break
                    outcome = probe(midpoint)
                    if outcome == "range":
                        status, reason = "range", "offer_range"
                        break
                    if outcome in ("feasible", "below_resolution"):
                        lower = midpoint
                    else:
                        upper = midpoint
                else:
                    if upper - lower <= query.alpha_tolerance and best is not None:
                        status, reason = "feasible", "tolerance"
                    else:
                        status, reason = "limit", "bisect_limit"
            if best is None and status in ("limit", "feasible"):
                status = "none_feasible"
                if (
                    reason == "alpha_bound"
                    and history[-1].outcome == "below_resolution"
                ):
                    reason = "unit_resolution"
        certificate = None
        if proof in ("fixed_program", "single_controller") and best is not None:
            lower_probe = history[best]
            upper_candidates = [
                row
                for row in history
                if row.outcome == "infeasible"
                and row.alpha.value > lower_probe.alpha.value
            ]
            if upper_candidates:
                upper_probe = min(
                    upper_candidates, key=lambda row: (row.alpha.value, row.index)
                )
                certificate = UpperCertificate(
                    proof,
                    lower_probe.alpha,
                    upper_probe.alpha,
                    lower_probe.index,
                    upper_probe.index,
                )
        return MSDAnalysis(
            prepared,
            tuple(misses),
            analysis_metadata(1),
            OutputSelection(ngc.OutputOptions(), False, query.export_details),
            history[best].alpha if best is not None else None,
            best,
            proof != "unproved",
            proof,
            certificate,
            status,
            reason,
            tuple(history),
            query,
            best_rows,
            best_accounting,
            MappingProxyType(retained) if retained is not None else None,
        )
    finally:
        remove_policies(owners)
