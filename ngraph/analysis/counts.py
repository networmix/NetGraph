"""Tunnel-count questions: one fresh native T2 evaluation per demand and count.

Every row evaluates one demand's declared centralized-TE model with the
row's tunnel count (or "up to" limit), LOSSY at the query's offer and with
its design demand; the plan, delivery and losses are the native result's.
Every demand of the set uses the same design and offer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import netgraph_core as ngc

from ngraph.analysis.failures import Workers, checked_workers, resolve_workers
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.placement import _endpoints
from ngraph.analysis.precision import _Searched, query_inputs, query_splits
from ngraph.analysis.units import precision_miss, quantize
from ngraph.results import (
    OutputSelection,
    ReportLocation,
    ResolvedDemandSet,
    TunnelCountAnalysis,
    TunnelCountRow,
)
from ngraph.utils.values import flag, integer, own, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario

MAX_COUNT = 10000


def _count(value: object, label: str) -> int:
    try:
        return integer(value, label, minimum=1, maximum=MAX_COUNT + 1)
    except ValueError:
        raise ValueError(
            f"{label}: expected an integer in [1, {MAX_COUNT}], got {value!r}"
        ) from None


@dataclass(frozen=True)
class TunnelCountQuery:
    """A tunnel count question: each tunnelled centralized-TE demand at each count, and
    up to a limit, planned for the design and lossy at the offer.
    """

    demands: ResolvedDemandSet
    counts: tuple[int, ...]
    design_demand: float
    offer: float
    up_to: int | None = None
    eligibility: ngc.Eligibility | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_details: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.demands, ResolvedDemandSet):
            raise TypeError(
                f"tunnel_counts.demands: expected ResolvedDemandSet, got {self.demands!r}"
            )
        if isinstance(self.counts, (str, bytes)) or not hasattr(
            self.counts, "__iter__"
        ):
            raise TypeError(
                f"tunnel_counts.counts: expected a sequence of integers, got {self.counts!r}"
            )
        counts = tuple(
            _count(value, f"tunnel_counts.counts[{index}]")
            for index, value in enumerate(self.counts)
        )
        seen: set[int] = set()
        for value in counts:
            if value in seen:
                raise ValueError(f"tunnel_counts.counts: duplicate count {value}")
            seen.add(value)
        object.__setattr__(self, "counts", counts)
        if self.up_to is not None:
            object.__setattr__(self, "up_to", _count(self.up_to, "tunnel_counts.up_to"))
        if not counts and self.up_to is None:
            raise ValueError("tunnel_counts.counts: give at least one count or up_to")
        for name in ("design_demand", "offer"):
            object.__setattr__(
                self, name, physical(getattr(self, name), f"tunnel_counts.{name}")
            )
        if self.eligibility is not None and not isinstance(
            self.eligibility, ngc.Eligibility
        ):
            raise TypeError(
                f"tunnel_counts.eligibility: expected native Eligibility, got {self.eligibility!r}"
            )
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError(
                f"tunnel_counts.outputs: expected native OutputOptions, got {self.outputs!r}"
            )
        own(
            self,
            workers=checked_workers(self.workers),
            export_details=flag(self.export_details, "export_details"),
        )

    @property
    def specs(self) -> tuple[tuple[int, bool], ...]:
        """The rows of each demand: the counts in order, then the up-to limit."""
        tail = () if self.up_to is None else ((self.up_to, True),)
        return tuple((count, False) for count in self.counts) + tail


@dataclass(frozen=True)
class _Question:
    """One row's question in the shape the split rules read."""

    config: ngc.FlowPolicyConfig
    offer: float
    design_demand: float


def _model(demand, label: str) -> ngc.CentralizedTE:
    model = demand.config.routing
    if not isinstance(model, ngc.CentralizedTE) or model.tunnel_count is None:
        raise ValueError(
            f"{label}.demands: demand {demand.id}: TunnelCountAnalysis needs a "
            "CentralizedTE model with a tunnel count"
        )
    return model


def _counted(model: ngc.CentralizedTE, count: int, up_to: bool) -> ngc.FlowPolicyConfig:
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=model.source_allocation,
            support=model.support,
            tunnel_count=ngc.TunnelCount(count, up_to=up_to),
            prefer_headroom=model.prefer_headroom,
        ),
        admission=ngc.Admission.LOSSY,
    )


def _group_key(model: ngc.CentralizedTE) -> tuple:
    # Native models compare by identity; equal declarations share one call. The
    # key holds the support itself (it compares by structure), never its id().
    return (model.source_allocation, model.prefer_headroom, model.support)


def count_splits(
    prepared: PreparedScenario, query: TunnelCountQuery, label, mask, results=None
):
    """The rows' split constraints, declared from the offer, design and live heads.

    One reverse search per demand finds its live heads for all its rows; no
    traffic is solved.
    """
    topology = prepared.topology
    precision = prepared.units_report.precision
    specs = query.specs
    splits, opaque = [], []
    for index, demand in enumerate(query.demands.demands):
        model = _model(demand, label)
        facts = _Searched(
            topology, prepared._named, model, demand.endpoints, mask, demand.pool
        )
        for count, up_to in specs:
            local, unverified = query_splits(
                topology,
                prepared._named,
                _Question(
                    _counted(model, count, up_to), query.offer, query.design_demand
                ),
                demand.endpoints,
                0,
                mask,
                f"{label}.demand[{demand.id}].{'up_to' if up_to else 'count'}[{count}]",
                precision,
                demand.pool,
                facts,
                result=None if results is None else results[(index, count, up_to)],
            )
            splits.extend(local)
            opaque.extend(unverified)
    return splits, opaque


def tunnel_counts(
    prepared: PreparedScenario, query: TunnelCountQuery
) -> TunnelCountAnalysis:
    """Evaluate tunnelled centralized-TE demands at each tunnel count."""
    topology = prepared.topology
    label = "tunnel_counts"
    demands = query.demands.demands
    mask = (
        topology.disabled
        if query.eligibility is None
        else ngc.Eligibility.intersect(topology.disabled, query.eligibility)
    )
    offer = quantize(query.offer, topology.q, f"{label}.offer")
    design = quantize(query.design_demand, topology.q, f"{label}.design_demand")
    models = [_model(demand, label) for demand in demands]
    for demand in demands:
        if demand.pool is not None and offer > demand.pool.offer_limit_units:
            raise ValueError(
                f"{label}.offer: demand {demand.id}: offer {offer} units exceeds the "
                f"prepared lossy budget {demand.pool.offer_limit_units} units of TE "
                f"ingress pool {demand.pool.head.pool_id}"
            )
    pairs = [_endpoints(topology, demand) for demand in demands]
    groups: dict[tuple, list[int]] = {}
    for index, model in enumerate(models):
        groups.setdefault(_group_key(model), []).append(index)
    workers = resolve_workers(query.workers)
    specs = query.specs
    results: dict[tuple[int, int, bool], ngc.PlacementResult] = {}
    for count, up_to in specs:
        for indices in groups.values():
            options = ngc.EvaluationOptions(
                _counted(models[indices[0]], count, up_to),
                eligibility=mask,
                outputs=query.outputs,
                offer=offer,
                design_demand=design,
            )
            evaluated = ngc.evaluate_pairs(
                topology.graph, [pairs[i] for i in indices], options, workers=workers
            )
            for index, result in zip(indices, evaluated, strict=True):
                results[(index, count, up_to)] = result
    rows = []
    for index, demand in enumerate(demands):
        for count, up_to in specs:
            result = results[(index, count, up_to)]
            plan = result.plan
            cost = None if plan is None else plan.total_tunnel_cost
            size = None if plan is None else plan.max_bandwidth_per_tunnel
            bound = None if plan is None else plan.max_lossless_offer
            live = None if plan is None else plan.heads_with_capacity
            if (
                plan is None
                or cost is None
                or size is None
                or bound is None
                or live is None
            ):
                raise RuntimeError(
                    f"{label}.demand[{demand.id}]: the native result has no T2 plan"
                )
            if demand.pool is not None and size > 0:
                # Each pool tunnel enters through one cost-1 private ingress edge.
                cost -= plan.tunnels_per_head * len(live)
            rows.append(
                TunnelCountRow(
                    demand.id,
                    demand.base_id,
                    demand.endpoints,
                    count,
                    up_to,
                    result,
                    demand.pool,
                    min(design, bound),
                    cost,
                )
            )
    splits, opaque = count_splits(prepared, query, label, mask, results)
    samples, constraints = query_inputs(prepared, query, label)
    miss = precision_miss(
        ReportLocation(None, "baseline", None),
        samples,
        (*constraints, *splits, *opaque),
    )
    return TunnelCountAnalysis(
        prepared,
        () if miss is None else (miss,),
        analysis_metadata(workers),
        OutputSelection(query.outputs, False, query.export_details),
        tuple(rows),
        query,
    )
