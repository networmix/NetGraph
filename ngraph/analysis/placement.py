"""Ordered native policy actions and explicit ledger ownership."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, residual_weights, scaled_expansion
from ngraph.analysis.failures import (
    FailureRequest,
    Workers,
    checked_workers,
    failure_cases,
    resolve_workers,
    schedule_cases,
)
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.precision import placement_inputs, placement_miss
from ngraph.analysis.states import (
    Baseline,
    forwarding_failure,
    participants,
    simultaneous_role,
)
from ngraph.analysis.topology import NamedRoutes, PreparedTopology
from ngraph.analysis.totals import placement_totals
from ngraph.results import (
    STATE_ORDER,
    CaseResult,
    CaseState,
    OutputSelection,
    PlacementAnalysis,
    PlacementRow,
    ReportLocation,
    ResolvedDemand,
    ResolvedDemandSet,
    StateName,
    exact_alpha,
)
from ngraph.utils.values import flag, optional_text, own, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class PlacementQuery:
    """A placement question: place a resolved demand set at alpha, with optional
    failures, failure states and interaction.
    """

    demands: ResolvedDemandSet
    alpha: float = 1.0
    failures: FailureRequest | None = None
    workers: Workers = "auto"
    outputs: ngc.OutputOptions = field(default_factory=ngc.OutputOptions)
    export_cost_distribution: bool = False
    export_details: bool = False
    # The earlier MSD step whose feasible alpha this question uses, if any.
    alpha_from_step: str | None = None
    # The failure states each case reports; repair only when listed.
    states: tuple[StateName, ...] = ("converged",)
    # Ordered: priority order; simultaneous: one LOSSY list on fixed programs.
    interaction: Literal["ordered", "simultaneous"] = "ordered"

    def __post_init__(self) -> None:
        object.__setattr__(self, "states", state_names(self.states, "placement.states"))
        if not isinstance(self.interaction, str) or self.interaction not in (
            "ordered",
            "simultaneous",
        ):
            raise ValueError(
                "placement.interaction: expected ordered or simultaneous, got "
                f"{self.interaction!r}"
            )
        if not isinstance(self.demands, ResolvedDemandSet):
            raise TypeError(
                f"placement.demands: expected ResolvedDemandSet, got {self.demands!r}"
            )
        if self.failures is not None and not isinstance(self.failures, FailureRequest):
            raise TypeError(
                f"placement.failures: expected FailureRequest, got {self.failures!r}"
            )
        if not isinstance(self.outputs, ngc.OutputOptions):
            raise TypeError(
                f"placement.outputs: expected native OutputOptions, got {self.outputs!r}"
            )
        own(
            self,
            interaction=str.__str__(self.interaction),
            alpha_from_step=optional_text(
                self.alpha_from_step, "placement.alpha_from_step"
            ),
            alpha=physical(self.alpha, "placement.alpha", positive=True),
            workers=checked_workers(self.workers),
            export_cost_distribution=flag(
                self.export_cost_distribution, "export_cost_distribution"
            ),
            export_details=flag(self.export_details, "export_details"),
        )


def state_names(value, label) -> tuple[StateName, ...]:
    """Requested failure states: nonempty and unique, held in canonical order."""
    if isinstance(value, str) or not isinstance(value, (tuple, list)):
        raise ValueError(f"{label}: expected a list of failure states")
    names = list(value)
    unknown = [name for name in names if name not in STATE_ORDER]
    if unknown or not names or len(set(names)) != len(names):
        raise ValueError(
            f"{label}: expected distinct states from {list(STATE_ORDER)}, got {names}"
        )
    return tuple(name for name in STATE_ORDER if name in names)


def remove_policies(policies: Sequence[ngc.FlowPolicy]) -> None:
    """Release every owner explicitly; destruction is not a cleanup operation."""
    for policy in policies:
        policy.remove()


def _endpoints(topology: PreparedTopology, demand: ResolvedDemand):
    """A demand's native sources (its pool's head, if pooled) and destinations."""
    if demand.pool is None:
        sources = [topology.node_id_by_name[name] for name in demand.endpoints.sources]
    else:
        pool_id = demand.pool.head.pool_id
        if pool_id not in topology.pool_heads:
            raise ValueError(
                f"demand.{demand.id}: pool was not included in topology preparation"
            )
        sources = [topology.pool_heads[pool_id]]
    return sources, [
        topology.node_id_by_name[name] for name in demand.endpoints.destinations
    ]


def policy_roster(
    topology: PreparedTopology,
    demands: Sequence[ResolvedDemand],
    mask: ngc.Eligibility,
    entries=None,
) -> tuple[ngc.FlowLedger, tuple[ngc.FlowPolicy, ...]]:
    """Create one private ledger and stable policy identities for a case or series.

    ``entries`` give each demand its own (config, eligibility, request);
    otherwise every demand uses its declared config under ``mask``.
    """
    ledger = ngc.FlowLedger(topology.graph)
    owners = []
    if entries is None:
        entries = [(demand.config, mask, None) for demand in demands]
    try:
        for demand, (config, eligibility, _) in zip(demands, entries, strict=True):
            sources, targets = _endpoints(topology, demand)
            try:
                policy = ngc.FlowPolicy(ledger, sources, targets, config, eligibility)
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


def _forward_simultaneous(
    topology, demands, ledger, owners, entries, roles, held, outputs
):
    """One SIMULTANEOUS list for a fresh roster of LOSSY copies and live controllers.

    Tunnel models and live controllers are first set up in priority order by
    one ORDERED list; each controller's program is then imported into a LOSSY
    Pinned participant (created after the roster; ``held`` keeps it for
    release). Returns the participants and their results.
    """
    setup = [i for i, role in enumerate(roles) if role != "direct"]
    if setup:
        prepare = [ngc.Replace(owners[i], entries[i][2]) for i in setup]
        ngc.apply_actions(ledger, prepare, mode=ngc.BatchMode.ORDERED)
    members = list(owners)
    for i in setup:
        if roles[i] == "controller":
            program = owners[i].program
            owners[i].remove()
            config = ngc.FlowPolicyConfig(
                routing=ngc.Pinned(program), admission=ngc.Admission.LOSSY
            )
            sources, targets = _endpoints(topology, demands.demands[i])
            members[i] = ngc.FlowPolicy(ledger, sources, targets, config, entries[i][1])
            held.append(members[i])
    actions = [
        (ngc.Forward if role == "tunnels" else ngc.Replace)(member, request)
        for member, role, (_, _, request) in zip(members, roles, entries, strict=True)
    ]
    listed = ngc.apply_actions(
        ledger, actions, mode=ngc.BatchMode.SIMULTANEOUS, outputs=outputs
    )
    return tuple(members), tuple(listed)


def _place_state(prepared, query, case, state, entries, tables, shared):
    """One state of one case on its own ledger; records and reports for published converged.

    ``entries`` give each demand its (config, eligibility, request); a
    simultaneous state forwards their LOSSY copies in one list. Its live
    controllers' participants are created last in every state (as their
    imports are in converged), so one-unit ties fall the same way.
    """
    topology = prepared.topology
    demands = query.demands
    ordered = query.interaction == "ordered"
    order, roles = list(range(len(entries))), None
    if not ordered:
        roles = [simultaneous_role(config.routing) for config, _, _ in entries]
        entries = tuple(
            (
                config
                if role == "controller"
                else ngc.FlowPolicyConfig(
                    routing=config.routing, admission=ngc.Admission.LOSSY
                ),
                eligibility,
                request,
            )
            for role, (config, eligibility, request) in zip(roles, entries, strict=True)
        )
        order.sort(key=shared.live.__getitem__)
    ledger, roster = policy_roster(
        topology,
        [demands.demands[i] for i in order],
        case.eligibility,
        [entries[i] for i in order],
    )
    owners = tuple(roster[k] for k in sorted(range(len(order)), key=order.__getitem__))
    held = list(owners)
    try:
        try:
            if ordered:
                requests = tuple(r for _, _, r in entries)
                results = replace_matrix(ledger, owners, requests, query.outputs)
            else:
                owners, results = _forward_simultaneous(
                    topology,
                    demands,
                    ledger,
                    owners,
                    entries,
                    roles,
                    held,
                    query.outputs,
                )
        except ValueError as exc:
            failure = forwarding_failure(exc)
            if failure is None:
                raise
            return CaseState((), None, failure), None
        observed = state == "converged" and state in query.states
        records = (
            _observation_records(
                prepared._named, demands, owners, costs=query.export_cost_distribution
            )
            if observed
            else ((),) * len(owners)
        )
        costs = shared.costs if observed else None
        rows = []
        for demand, policy, result, snapshots in zip(
            demands.demands, owners, results, records, strict=True
        ):
            distribution, unavailable = None, MappingProxyType({})
            if costs is not None:
                distribution, unavailable = costs(
                    topology,
                    policy.config,
                    result,
                    [
                        topology.node_id_by_name[name]
                        for name in demand.endpoints.destinations
                    ],
                    case.eligibility,
                    pool=demand.pool,
                    records=snapshots,
                    programmed=demand.id in shared.programmed,
                )
            rows.append(
                PlacementRow(
                    demand.id,
                    demand.base_id,
                    demand.endpoints,
                    shared.amounts[demand.id],
                    result,
                    demand.pool,
                    distribution,
                    unavailable,
                )
            )
        miss = None
        if observed:
            miss = placement_miss(
                prepared,
                demands,
                owners,
                results,
                records,
                case.eligibility,
                query.alpha,
                ReportLocation(None, case.id, None),
                shared.inputs,
                tables,
                ordered,
            )
        totals = placement_totals(
            (row.id, row.reference_request_units, row.result) for row in rows
        )
        return CaseState(tuple(rows), totals), miss
    finally:
        remove_policies(held)


@dataclass(frozen=True)
class _Shared:
    """What every case and state of one query shares.

    ``programmed`` holds the ids of the demands the WCMP controller programs;
    ``live`` marks each demand whose declared model is a live controller.
    """

    amounts: Mapping[str, int]
    inputs: object
    costs: object
    programmed: frozenset[str]
    live: tuple[bool, ...]


def _programmed(demands):
    """The ids of the demands the WCMP controller programs."""
    parents = {
        parent.base_id
        for parent in demands.expansion_template
        if controlled(demands.controller, parent.policy)
    }
    return frozenset(d.id for d in demands.demands if d.base_id in parents)


def _place_case(prepared, query, case, shared, baseline):
    """A case's requested states, in canonical order.

    ``baseline`` holds the baseline programs; for the baseline case itself it
    is None, and its converged placement supplies them when stale or repair is
    requested (computed even when converged is not, published only if it is).
    A WCMP controller set forwards a failure case on the case's own tables.
    """
    demands, setup = query.demands, prepared._controller
    computed = query.states
    if baseline is None and {"stale", "repair"} & set(computed):
        computed = ("converged", *(s for s in computed if s != "converged"))
    group = demands.controller is not None and setup.scope == "group"
    states: dict[StateName, CaseState] = {}
    miss = None
    for state in computed:
        if state != "converged" and baseline is None:
            baseline = Baseline.of(states["converged"])
        tables = None
        if (
            case.kind == "failure"
            and demands.controller is not None
            and (state == "converged" or (state == "repair" and group))
        ):
            tables = setup.case_tables(
                prepared.topology,
                demands,
                case.eligibility,
                repair=state == "repair",
                context=f"case {case.id} state {state}",
            )
        entries = participants(
            prepared.topology,
            setup,
            demands,
            shared.programmed,
            case,
            state,
            shared.amounts,
            baseline,
            tables,
        )
        value, observed = _place_state(
            prepared, query, case, state, entries, tables, shared
        )
        if group and state != "stale":
            dead = tuple(c for t in (tables or {}).values() for c in t.dead_caps)
            value = replace(value, dead_caps=dead)
        states[state] = value
        if observed is not None:
            miss = observed
    published = MappingProxyType({s: states[s] for s in query.states})
    return CaseResult(case, published), miss, baseline


def place(prepared: PreparedScenario, query: PlacementQuery) -> PlacementAnalysis:
    """Place a resolved demand set on a prepared scenario, in each failure case and
    requested state.
    """
    cost_distribution = None
    if query.export_cost_distribution:
        # Cost reports load only when asked for.
        from ngraph.analysis.costs import cost_distribution

    topology = prepared.topology
    if (
        query.failures is not None
        and query.failures.policy is not None
        and query.demands.controller is not None
    ):
        setup = prepared._controller
        assert setup is not None
        setup.check_failure_states(
            topology, query.demands, query.states, "placement.states"
        )
    alpha = exact_alpha(query.alpha)
    amounts, accounting = scaled_expansion(query.demands, alpha.value, topology.q)
    for demand in query.demands.demands:
        pool = demand.pool
        if query.interaction == "simultaneous" and pool is not None:
            if amounts[demand.id] > pool.offer_limit_units:
                raise ValueError(
                    f"placement.interaction: demand {demand.id}: offer "
                    f"{amounts[demand.id]} units exceeds the prepared lossy budget "
                    f"{pool.offer_limit_units} units of TE ingress pool "
                    f"{pool.head.pool_id}"
                )
    cases = failure_cases(prepared, query.failures)
    workers = resolve_workers(query.workers)
    shared = _Shared(
        amounts,
        placement_inputs(prepared, query.demands, alpha.value),
        cost_distribution,
        _programmed(query.demands),
        tuple(
            simultaneous_role(d.config.routing) == "controller"
            for d in query.demands.demands
        ),
    )

    def solve(case, baseline=None):
        return _place_case(prepared, query, case, shared, baseline)

    if {"stale", "repair"} & set(query.states):
        # Stale and repair replay the baseline programs: the baseline goes first.
        first = solve(cases[0])
        observed = (
            first,
            *schedule_cases(cases[1:], lambda case: solve(case, first[2]), workers),
        )
    else:
        observed = schedule_cases(cases, solve, workers)
    return PlacementAnalysis(
        prepared,
        tuple(miss for _, miss, _ in observed if miss is not None),
        analysis_metadata(workers, query.failures),
        OutputSelection(
            query.outputs, query.export_cost_distribution, query.export_details
        ),
        alpha,
        tuple(case for case, _, _ in observed),
        accounting,
        query,
    )
