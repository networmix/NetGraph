"""Ordered native policy actions and explicit ledger ownership."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, residual_weights, scaled_expansion
from ngraph.analysis.failures import (
    FailureRequest,
    Workers,
    failure_cases,
    resolve_workers,
    schedule_cases,
)
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.precision import placement_inputs, placement_miss
from ngraph.analysis.topology import NamedRoutes, PreparedTopology
from ngraph.analysis.totals import placement_totals
from ngraph.results import (
    CaseResult,
    CaseState,
    OutputSelection,
    PlacementAnalysis,
    PlacementRow,
    ReportLocation,
    ResolvedDemand,
    ResolvedDemandSet,
    exact_alpha,
)
from ngraph.utils.values import physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class PlacementQuery:
    demands: ResolvedDemandSet
    alpha: float = 1.0
    failures: FailureRequest | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_cost_distribution: bool = False
    export_details: bool = False
    # The earlier MSD step whose feasible alpha this question uses, if any.
    alpha_from_step: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.export_details, bool):
            raise ValueError("export_details: expected bool")
        if not isinstance(self.demands, ResolvedDemandSet):
            raise TypeError("placement.demands: expected ResolvedDemandSet")
        if self.alpha_from_step is not None and (
            not isinstance(self.alpha_from_step, str) or not self.alpha_from_step
        ):
            raise ValueError("placement.alpha_from_step: expected nonempty name")
        object.__setattr__(
            self, "alpha", physical(self.alpha, "placement.alpha", positive=True)
        )
        if self.workers != "auto":
            resolve_workers(self.workers)
        if self.failures is not None and not isinstance(self.failures, FailureRequest):
            raise TypeError("placement.failures: expected FailureRequest")
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError("placement.outputs: expected native OutputOptions")
        if not isinstance(self.export_cost_distribution, bool):
            raise ValueError("export_cost_distribution: expected bool")


def remove_policies(policies: Sequence[ngc.FlowPolicy]) -> None:
    """Release every owner explicitly; destruction is not a cleanup operation."""
    for policy in policies:
        policy.remove()


def policy_roster(
    topology: PreparedTopology, demands: Sequence[ResolvedDemand], mask: ngc.Eligibility
) -> tuple[ngc.FlowLedger, tuple[ngc.FlowPolicy, ...]]:
    """Create one private ledger and stable policy identities for a case or series."""
    ledger = ngc.FlowLedger(topology.graph)
    owners = []
    try:
        for demand in demands:
            if demand.pool is None:
                sources = [
                    topology.node_id_by_name[name] for name in demand.endpoints.sources
                ]
            else:
                pool_id = demand.pool.head.pool_id
                if pool_id not in topology.pool_heads:
                    raise ValueError(
                        f"demand.{demand.id}: pool was not included in topology preparation"
                    )
                sources = [topology.pool_heads[pool_id]]
            targets = [
                topology.node_id_by_name[name] for name in demand.endpoints.destinations
            ]
            try:
                policy = ngc.FlowPolicy(ledger, sources, targets, demand.config, mask)
            except (ValueError, TypeError) as exc:
                label = demand.yaml_label
                if label is None:
                    raise
                raise type(exc)(f"{label}: {exc}") from exc
            try:
                owners.append(policy)
            except BaseException:
                policy.remove()
                raise
        return ledger, tuple(owners)
    except BaseException:
        remove_policies(owners)
        raise


def replace_matrix(
    ledger: ngc.FlowLedger,
    policies: Sequence[ngc.FlowPolicy],
    requests: Sequence[int],
    outputs: ngc.OutputOptions | None = None,
) -> tuple[ngc.PlacementResult, ...]:
    """Remove the whole previous matrix, then submit full Replace requests once."""
    if len(policies) != len(requests):
        raise ValueError("placement: requests must align with the stable policy roster")
    remove_policies(policies)
    return _apply_matrix(ledger, policies, requests, outputs)


def _apply_matrix(ledger, policies, requests, outputs=None):
    """Apply to an already released roster; shared by placement and MSD."""
    if len(policies) != len(requests):
        raise ValueError("placement: requests must align with the stable policy roster")
    actions = [
        ngc.Replace(policy, request)
        for policy, request in zip(policies, requests, strict=True)
    ]
    return tuple(
        ngc.apply_actions(ledger, actions, mode=ngc.BatchMode.ORDERED, outputs=outputs)
    )


def _observation_records(
    named: NamedRoutes, demands: ResolvedDemandSet, policies, *, costs=False
):
    """Read records only for split descriptions, residual weights or SPF costs."""
    residual = residual_weights(named, demands.expansion_template)

    def needed(policy):
        model = policy.config.routing
        return (
            residual
            or isinstance(model, ngc.Pinned)
            or (
                isinstance(model, ngc.ShortestPaths)
                and (costs or model.allocation != ngc.RouteAllocation.OPTIMIZED)
            )
            or (
                isinstance(model, ngc.CentralizedTE)
                and model.tunnel_count is None
                and model.source_allocation == ngc.SourceAllocation.EQUAL
            )
        )

    return tuple(
        tuple(policy.records()) if needed(policy) else () for policy in policies
    )


def _place_case(prepared, query, case, amounts, observations, cost_distribution):
    topology = prepared.topology
    ledger, owners = policy_roster(topology, query.demands.demands, case.eligibility)
    try:
        requests = tuple(amounts[demand.id] for demand in query.demands.demands)
        results = replace_matrix(ledger, owners, requests, query.outputs)
        records = _observation_records(
            prepared._named,
            query.demands,
            owners,
            costs=query.export_cost_distribution,
        )
        programmed = {
            parent.base_id
            for parent in query.demands.expansion_template
            if controlled(query.demands.controller, parent.policy)
        }
        rows = []
        for demand, result, snapshots, reference in zip(
            query.demands.demands, results, records, requests, strict=True
        ):
            distribution, unavailable = None, MappingProxyType({})
            if cost_distribution is not None:
                distribution, unavailable = cost_distribution(
                    topology,
                    demand.config,
                    result,
                    [
                        topology.node_id_by_name[name]
                        for name in demand.endpoints.destinations
                    ],
                    case.eligibility,
                    pool=demand.pool,
                    records=snapshots,
                    programmed=demand.base_id in programmed,
                )
            rows.append(
                PlacementRow(
                    demand.id,
                    demand.base_id,
                    demand.endpoints,
                    reference,
                    result,
                    demand.pool,
                    distribution,
                    unavailable,
                )
            )
        rows = tuple(rows)
        miss = placement_miss(
            prepared,
            query.demands,
            owners,
            results,
            records,
            case.eligibility,
            query.alpha,
            ReportLocation(None, case.id, None),
            observations,
        )
        totals = placement_totals(
            (row.id, row.reference_request_units, row.result) for row in rows
        )
        state = CaseState(rows, totals)
        return CaseResult(case, MappingProxyType({"converged": state})), miss
    finally:
        remove_policies(owners)


def place(prepared: PreparedScenario, query: PlacementQuery) -> PlacementAnalysis:
    cost_distribution = None
    if query.export_cost_distribution:
        # Cost reports load only when asked for.
        from ngraph.analysis.costs import cost_distribution

    topology = prepared.topology
    # A request without a policy asks the baseline alone.
    if (
        query.failures is not None
        and query.failures.policy is not None
        and query.demands.controller is not None
    ):
        raise ValueError(
            f"placement.failures: demand set {query.demands.name} is programmed by "
            "the WCMP controller, whose tables are nominal only"
        )
    alpha = exact_alpha(query.alpha)
    amounts, accounting = scaled_expansion(query.demands, alpha.value, topology.q)
    cases = failure_cases(prepared, query.failures)
    workers = resolve_workers(query.workers)
    inputs = placement_inputs(prepared, query.demands, alpha.value)
    observed = schedule_cases(
        cases,
        lambda case: _place_case(
            prepared, query, case, amounts, inputs, cost_distribution
        ),
        workers,
    )
    return PlacementAnalysis(
        prepared,
        tuple(miss for _, miss in observed if miss is not None),
        analysis_metadata(workers, query.failures),
        OutputSelection(
            query.outputs, query.export_cost_distribution, query.export_details
        ),
        alpha,
        tuple(case for case, _ in observed),
        accounting,
        query,
    )
