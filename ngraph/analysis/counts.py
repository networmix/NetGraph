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
from ngraph.analysis.units import quantize
from ngraph.results import (
    OutputSelection,
    ResolvedDemandSet,
    TunnelCountAnalysis,
    TunnelCountRow,
)
from ngraph.utils.values import _located_error, _shown, flag, integer, own, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario

MAX_COUNT = 10000


def _count(value: object, label: str) -> int:
    try:
        return integer(value, label, minimum=1, maximum=MAX_COUNT + 1)
    except ValueError:
        raise _located_error(
            ValueError(
                f"{label}: expected an integer in [1, {MAX_COUNT}], got {_shown(value)}"
            ),
            label,
            value,
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
            raise _located_error(
                TypeError(
                    f"tunnel_counts.counts: expected a sequence of integers, got {_shown(self.counts)}"
                ),
                "tunnel_counts.counts",
                self.counts,
            )
        counts = tuple(
            _count(value, f"tunnel_counts.counts[{index}]")
            for index, value in enumerate(self.counts)
        )
        seen: set[int] = set()
        for value in counts:
            if value in seen:
                raise _located_error(
                    ValueError(
                        f"tunnel_counts.counts: duplicate count {_shown(value)}"
                    ),
                    "tunnel_counts.counts",
                    self.counts,
                )
            seen.add(value)
        object.__setattr__(self, "counts", counts)
        if self.up_to is not None:
            object.__setattr__(self, "up_to", _count(self.up_to, "tunnel_counts.up_to"))
        if not counts and self.up_to is None:
            raise _located_error(
                ValueError(
                    f"tunnel_counts.counts: give at least one count or up_to, got {_shown(self.counts)}"
                ),
                "tunnel_counts.counts",
                self.counts,
            )
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
            raise _located_error(
                TypeError(
                    f"tunnel_counts.outputs: expected native OutputOptions, got {_shown(self.outputs)}"
                ),
                "tunnel_counts.outputs",
                self.outputs,
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


def _model(demand, label: str) -> ngc.CentralizedTE:
    model = demand.config.routing
    if not isinstance(model, ngc.CentralizedTE) or model.tunnel_count is None:
        raise _located_error(
            ValueError(
                f"{label}.demands: demand {demand.id}: TunnelCountAnalysis needs a "
                "CentralizedTE model with a tunnel count"
            ),
            label,
            None,
            field="demand_set",
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
    return TunnelCountAnalysis(
        prepared,
        analysis_metadata(workers),
        OutputSelection(query.outputs, False, query.export_details),
        tuple(rows),
        query,
    )
