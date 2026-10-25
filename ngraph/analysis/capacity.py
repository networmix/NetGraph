"""Named capacity questions evaluated directly by the native evaluators."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, pooled, selected_pairs
from ngraph.analysis.failures import (
    FailureRequest,
    Workers,
    checked_workers,
    failure_cases,
    resolve_workers,
    schedule_cases,
)
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.precision import query_has_splits, query_inputs, query_miss
from ngraph.analysis.units import quantize
from ngraph.model.selectors import Selector
from ngraph.results import (
    CapacityAnalysis,
    CapacityRow,
    CaseResult,
    CaseState,
    OutputSelection,
    PoolHead,
    PoolMetadata,
    ReportLocation,
    SelfPair,
    SyntheticIngress,
)
from ngraph.utils.values import flag, own, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


def maximum_config() -> ngc.FlowPolicyConfig:
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED),
        admission=ngc.Admission.LOSSLESS,
    )


@dataclass(frozen=True)
class CapacityQuery:
    source: Selector
    target: Selector
    config: ngc.FlowPolicyConfig = field(default_factory=maximum_config)
    mode: Literal["combine", "pairwise"] = "combine"
    offer: float | None = None
    design_demand: float | None = None
    failures: FailureRequest | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_cost_distribution: bool = False
    export_details: bool = False
    # The declared model ``config`` was built from, as a workflow step records
    # it (a preset, a parsed model or PinnedRoutes); None for a supplied config.
    declaration: object = None

    def __post_init__(self) -> None:
        validate_capacity_inputs(
            self.source,
            self.target,
            self.config,
            self.outputs,
        )
        if self.offer is not None:
            object.__setattr__(self, "offer", physical(self.offer, "capacity.offer"))
        if self.design_demand is not None:
            object.__setattr__(
                self,
                "design_demand",
                physical(self.design_demand, "capacity.design_demand"),
            )
        if not isinstance(self.mode, str) or self.mode not in ("combine", "pairwise"):
            raise ValueError(
                f"capacity.mode: expected combine or pairwise, got {self.mode!r}"
            )
        if self.failures is not None and not isinstance(self.failures, FailureRequest):
            raise TypeError(
                f"capacity.failures: expected FailureRequest, got {self.failures!r}"
            )
        own(
            self,
            mode=str.__str__(self.mode),
            workers=checked_workers(self.workers),
            export_cost_distribution=flag(
                self.export_cost_distribution, "export_cost_distribution"
            ),
            export_details=flag(self.export_details, "export_details"),
        )


def validate_capacity_inputs(source, target, config, outputs) -> None:
    if not isinstance(source, Selector) or not isinstance(target, Selector):
        raise TypeError(
            f"capacity endpoints: expected Selectors, got {(source, target)!r}"
        )
    if not isinstance(config, ngc.FlowPolicyConfig):
        raise TypeError(
            f"capacity.config: expected native FlowPolicyConfig, got {config!r}"
        )
    if not isinstance(outputs, ngc.OutputOptions):
        raise TypeError(
            f"capacity.outputs: expected native OutputOptions, got {outputs!r}"
        )


def question_kind(config, offer, design):
    """Name the actual native evaluator question and its offer source."""
    if config.admission == ngc.Admission.LOSSLESS:
        return (
            ("lossless_bound", "unlimited")
            if offer is None
            else ("fixed_offer_delivery", "explicit")
        )
    if offer is not None:
        return "fixed_offer_delivery", "explicit"
    if (
        isinstance(config.routing, ngc.CentralizedTE)
        and config.routing.tunnel_count is not None
        and design is not None
    ):
        return "fixed_offer_delivery", "design"
    if isinstance(config.routing, ngc.ShortestPaths):
        return "first_hop_experiment", "first_hop"
    # The evaluator owns the labelled missing-offer/model refusal.
    return "fixed_offer_delivery", "unlimited"


def evaluation_options(topology, config, offer, design, mask, outputs):
    return ngc.EvaluationOptions(
        config,
        eligibility=mask,
        outputs=outputs,
        offer=None if offer is None else quantize(offer, topology.q, "capacity.offer"),
        design_demand=None
        if design is None
        else quantize(design, topology.q, "capacity.design_demand"),
    )


def _pools(topology, query, jobs, label):
    """Each evaluated pair's prepared pool, when its question pools its sources.

    Every pool is the private ingress of its physical sources, so a pair uses
    the prepared pool of exactly its sources (the first by id).
    """
    if not pooled(query.mode, query.declaration):
        return {}
    sources = {}
    for ref in topology.edge_refs:
        if isinstance(ref, SyntheticIngress):
            sources.setdefault(ref.pool_id, set()).add(ref.source)
    owners = {}
    for pool_id in sorted(sources):
        owners.setdefault(frozenset(sources[pool_id]), pool_id)
    pools = {}
    for index, pair in jobs:
        pool_id = owners.get(frozenset(pair.sources))
        if pool_id is None:
            raise ValueError(
                f"{label}.pair[{index}]: {query.declaration} over combined sources "
                "needs a pool prepared for them; ask it as a MaxFlow step and "
                "prepare again"
            )
        pools[index] = PoolMetadata(PoolHead(pool_id, pair.sources))
    return pools


def question_pairs(prepared: PreparedScenario, query: CapacityQuery, label: str):
    """The question's endpoint pairs; the evaluated ones, indexed; their native
    ids; and the pool of each pooled one, by index.

    A singleton self pair is not evaluated. A pooled pair starts at its pool head.
    """
    topology = prepared.topology
    if controlled(prepared.scenario.wcmp_controller, query.declaration):
        raise ValueError(
            f"{label}: SHORTEST_PATHS_WCMP is programmed by the WCMP controller "
            "for demand sets only; ask a placement, or give the native model"
        )
    endpoints = selected_pairs(
        prepared.scenario.network, query.source, query.target, query.mode, label
    )
    jobs = tuple(
        (index, pair)
        for index, pair in enumerate(endpoints)
        if not (pair.sources == pair.destinations and len(pair.sources) == 1)
    )
    pools = _pools(topology, query, jobs, label)
    native_pairs = tuple(
        (
            [topology.pool_heads[pools[index].head.pool_id]]
            if index in pools
            else [topology.node_id_by_name[name] for name in pair.sources],
            [topology.node_id_by_name[name] for name in pair.destinations],
        )
        for index, pair in jobs
    )
    return endpoints, jobs, native_pairs, pools


def evaluate(topology, query: CapacityQuery, native_pairs, options, workers: int):
    """Evaluate each pair once with the native evaluator the question names."""
    if isinstance(query.config.routing, ngc.Pinned):
        # Supplied programs have fixed endpoints and no native pair batch.
        return schedule_cases(
            native_pairs,
            lambda pair: ngc.evaluate_demand(topology.graph, pair[0], pair[1], options),
            workers,
        )
    if query.mode == "combine":
        return tuple(
            ngc.evaluate_demand(topology.graph, sources, destinations, options)
            for sources, destinations in native_pairs
        )
    return ngc.evaluate_pairs(topology.graph, native_pairs, options, workers=workers)


def capacity(prepared: PreparedScenario, query: CapacityQuery) -> CapacityAnalysis:
    cost_distribution = None
    if query.export_cost_distribution:
        # Cost reports load only when asked for.
        from ngraph.analysis.costs import cost_distribution

    topology = prepared.topology
    endpoints, jobs, native_pairs, pools = question_pairs(prepared, query, "capacity")
    workers = resolve_workers(query.workers)
    cases = failure_cases(prepared, query.failures)
    completed, misses = [], []
    check_splits = query_has_splits(query)
    inputs = query_inputs(prepared, query, "capacity")
    for case in cases:
        options = evaluation_options(
            topology,
            query.config,
            query.offer,
            query.design_demand,
            case.eligibility,
            query.outputs,
        )
        results = evaluate(topology, query, native_pairs, options, workers)
        indexed = {
            index: result for (index, _), result in zip(jobs, results, strict=True)
        }
        rows = []
        report_costs = {}
        for index, pair in enumerate(endpoints):
            identity = f"pair-{index:06d}"
            if index not in indexed:
                rows.append(SelfPair(identity, pair.sources[0]))
                continue
            result = indexed[index]
            distribution, unavailable = None, MappingProxyType({})
            if cost_distribution is not None:
                shortest_costs = None
                if isinstance(query.config.routing, ngc.ShortestPaths):
                    key = pair.destinations
                    if key not in report_costs:
                        search = ngc.spf(
                            topology.graph,
                            [topology.node_id_by_name[name] for name in key],
                            ngc.SpfOptions(
                                ngc.Direction.REVERSE, eligibility=case.eligibility
                            ),
                        )
                        report_costs[key] = search.costs
                    shortest_costs = report_costs[key]
                distribution, unavailable = cost_distribution(
                    topology,
                    query.config,
                    result,
                    [topology.node_id_by_name[name] for name in pair.destinations],
                    case.eligibility,
                    pool=pools.get(index),
                    shortest_costs=shortest_costs,
                )
            rows.append(
                CapacityRow(
                    identity, pair, result, pools.get(index), distribution, unavailable
                )
            )
        completed.append(
            CaseResult(
                case, MappingProxyType({"converged": CaseState(tuple(rows), None)})
            )
        )
        miss = query_miss(
            prepared,
            query,
            tuple(
                (
                    pair,
                    indexed[index].delivered,
                    case.eligibility,
                    f"capacity.pair[{index}]",
                    pools.get(index),
                )
                for index, pair in jobs
            )
            if check_splits
            else (),
            ReportLocation(None, case.id, None),
            inputs,
        )
        if miss is not None:
            misses.append(miss)
    question, source = question_kind(query.config, query.offer, query.design_demand)
    return CapacityAnalysis(
        prepared,
        tuple(misses),
        analysis_metadata(workers, query.failures),
        OutputSelection(
            query.outputs, query.export_cost_distribution, query.export_details
        ),
        question,
        source,
        tuple(completed),
        query,
    )
