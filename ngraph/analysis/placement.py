"""Ordered native policy actions and explicit ledger ownership."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, scaled_expansion
from ngraph.analysis.failures import (
    FailureRequest,
    Workers,
    checked_workers,
    failure_cases,
    resolve_workers,
    schedule_cases,
)
from ngraph.analysis.metadata import analysis_metadata
from ngraph.analysis.outputs import required_outputs
from ngraph.analysis.states import (
    Baseline,
    forwarding_failure,
    participants,
    simultaneous_role,
)
from ngraph.analysis.topology import PreparedTopology, eligibility
from ngraph.analysis.totals import placement_totals
from ngraph.results import (
    STATE_ORDER,
    CaseResult,
    CaseState,
    OutputSelection,
    PlacementAnalysis,
    PlacementRow,
    ResolvedDemand,
    ResolvedDemandSet,
    StateName,
    exact_alpha,
)
from ngraph.utils.values import (
    _located_error,
    _shown,
    flag,
    optional_text,
    own,
    physical,
)

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
        raise _located_error(
            ValueError(
                f"{label}: expected a list of failure states, got {_shown(value)}"
            ),
            label,
            value,
        )
    names = list(value)
    unknown = [name for name in names if name not in STATE_ORDER]
    if unknown or not names or len(set(names)) != len(names):
        raise _located_error(
            ValueError(
                f"{label}: expected distinct states from {list(STATE_ORDER)}, got {_shown(names)}"
            ),
            label,
            value,
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
    preparations=None,
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
        for index, (demand, (config, eligibility, _)) in enumerate(
            zip(demands, entries, strict=True)
        ):
            sources, targets = _endpoints(topology, demand)
            try:
                if preparations is None or preparations[index] is None:
                    policy = ngc.FlowPolicy(
                        ledger, sources, targets, config, eligibility
                    )
                else:
                    policy = ngc.FlowPolicy(
                        ledger,
                        sources,
                        targets,
                        config,
                        eligibility,
                        preparation=preparations[index],
                    )
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


def _place_state(
    prepared,
    query,
    mask,
    state,
    entries,
    tables,
    shared,
    capture_baseline,
    is_baseline=False,
):
    """One state on its own ledger; reports and replay snapshots read live policies.

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
    reuse = shared.reuse[0] if shared.reuse else None
    hints = (
        reuse.prepare(mask)
        if reuse is not None and state == "converged" and not is_baseline
        else None
    )
    ledger, roster = policy_roster(
        topology,
        [demands.demands[i] for i in order],
        mask,
        [entries[i] for i in order],
        preparations=hints,
    )
    owners = tuple(roster[k] for k in sorted(range(len(order)), key=order.__getitem__))
    held = list(owners)
    try:
        if _REUSE_OBSERVER is not None and state == "converged":
            _REUSE_OBSERVER("baseline" if is_baseline else "failure", owners, hints)
        observed = state == "converged" and state in query.states
        outputs = required_outputs(
            query.outputs,
            by_source=query.export_details
            or (
                observed
                and query.export_cost_distribution
                and any(
                    isinstance(config.routing, ngc.ShortestPaths)
                    for config, _, _ in entries
                )
            ),
        )
        try:
            if ordered:
                requests = tuple(r for _, _, r in entries)
                results = replace_matrix(ledger, owners, requests, outputs)
            else:
                owners, results = _forward_simultaneous(
                    topology,
                    demands,
                    ledger,
                    owners,
                    entries,
                    roles,
                    held,
                    outputs,
                )
        except ValueError as exc:
            failure = forwarding_failure(exc)
            if failure is None:
                raise
            failed = CaseState((), None, failure)
            if capture_baseline:
                Baseline.of(failed, demands.demands, owners)
            return failed, None
        if is_baseline and shared.reuse is not None and state == "converged":
            shared.reuse[0] = _capture_reuse(topology, demands, owners, mask)
        costs = shared.costs if observed else None
        rows = []
        for demand, policy, result in zip(
            demands.demands, owners, results, strict=True
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
                    mask,
                    pool=demand.pool,
                    program=policy.program,
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
        totals = placement_totals(
            (row.id, row.reference_request_units, row.result) for row in rows
        )
        value = CaseState(tuple(rows), totals)
        baseline = (
            Baseline.of(value, demands.demands, owners) if capture_baseline else None
        )
        return value, baseline
    finally:
        remove_policies(held)


@dataclass(frozen=True)
class _Shared:
    """What every case and state of one query shares.

    ``programmed`` holds the ids of the demands the WCMP controller programs;
    ``live`` marks each demand whose declared model is a live controller.
    """

    amounts: Mapping[str, int]
    costs: object
    programmed: frozenset[str]
    live: tuple[bool, ...]
    reuse: list[ngc.ShortestPathsReuse | None] | None = None


def _programmed(demands):
    """The ids of the demands the WCMP controller programs."""
    parents = {
        parent.base_id
        for parent in demands.expansion_template
        if controlled(demands.controller, parent.policy)
    }
    return frozenset(d.id for d in demands.demands if d.base_id in parents)


def _place_case(prepared, query, case, mask, shared, baseline):
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
    for state in computed:
        tables = None
        if (
            case.kind == "failure"
            and demands.controller is not None
            and (state == "converged" or (state == "repair" and group))
        ):
            tables = setup.case_tables(
                prepared.topology,
                demands,
                mask,
                repair=state == "repair",
                context=f"case {case.id} state {state}",
            )
        entries = participants(
            prepared.topology,
            setup,
            demands,
            shared.programmed,
            mask,
            state,
            shared.amounts,
            baseline,
            tables,
        )
        capture = (
            baseline is None
            and state == "converged"
            and bool({"stale", "repair"} & set(query.states))
        )
        value, captured = _place_state(
            prepared,
            query,
            mask,
            state,
            entries,
            tables,
            shared,
            capture,
            case.kind == "baseline",
        )
        if captured is not None:
            baseline = captured
        if group and state != "stale":
            dead = tuple(c for t in (tables or {}).values() for c in t.dead_caps)
            value = replace(value, dead_caps=dead)
        states[state] = value
    published = MappingProxyType({s: states[s] for s in query.states})
    return CaseResult(case, published), baseline


# One CLI run owns the optional run-wide capture; the launcher clears it at exit.
_REUSE_MODE = os.environ.get("NETGRAPH_REUSE_LIFETIME", "step")
_REUSE_RUN: dict[tuple, ngc.ShortestPathsReuse] = {}
_REUSE_OBSERVER = None
_REUSE_SCHEDULE_OBSERVER = None


def _reuse_eligible(query):
    if (
        not query.demands.demands
        or query.interaction != "ordered"
        or "converged" not in query.states
    ):
        return False
    for demand in query.demands.demands:
        config = demand.config
        sp = config.routing
        if not (
            isinstance(sp, ngc.ShortestPaths)
            and config.admission == ngc.Admission.LOSSLESS
            and sp.allocation == ngc.RouteAllocation.EQUAL
            and sp.source_allocation in (None, ngc.SourceAllocation.EQUAL)
            and sp.weight_basis is None
            and sp.edge_weights is None
            and sp.tie_break == ngc.RouteTieBreak.FEWER_HOPS
            and sp.multipath
            and sp.parallel_edges
        ):
            return False
    return True


def _reuse_key(topology, demands, mask):
    specs = []
    for demand in demands.demands:
        sources, targets = _endpoints(topology, demand)
        config = demand.config
        sp = config.routing
        source_allocation = (
            ngc.SourceAllocation.EQUAL
            if sp.source_allocation is None
            else sp.source_allocation
        )
        specs.append(
            (
                tuple(sorted(set(sources))),
                tuple(sorted(set(targets))),
                config.admission,
                sp.allocation,
                source_allocation,
                sp.weight_basis,
                None if sp.edge_weights is None else tuple(sp.edge_weights),
                sp.tie_break,
                sp.multipath,
                sp.parallel_edges,
            )
        )
    return (
        topology.graph.uid(),
        tuple(mask.node_allowed().tolist()),
        tuple(mask.edge_allowed().tolist()),
        tuple(specs),
    )


def _capture_reuse(topology, demands, owners, mask):
    key = _reuse_key(topology, demands, mask) if _REUSE_MODE == "run" else None
    if key is not None and key in _REUSE_RUN:
        return _REUSE_RUN[key]
    captured = ngc.ShortestPathsReuse(owners)
    if key is not None:
        _REUSE_RUN[key] = captured
    if _REUSE_OBSERVER is not None:
        _REUSE_OBSERVER("capture", owners, None)
    return captured


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
        cost_distribution,
        _programmed(query.demands),
        tuple(
            simultaneous_role(d.config.routing) == "controller"
            for d in query.demands.demands
        ),
    )

    reuse_enabled = _REUSE_MODE in {"step", "run", "schedule"} and _reuse_eligible(
        query
    )
    if reuse_enabled and _REUSE_MODE != "schedule":
        shared = replace(shared, reuse=[None])
    cached_capture = None
    if reuse_enabled and _REUSE_MODE == "run":
        baseline_mask = eligibility(
            topology, cases[0].pattern.excluded_nodes, cases[0].pattern.excluded_links
        )
        cached_capture = _REUSE_RUN.get(
            _reuse_key(topology, query.demands, baseline_mask)
        )
        shared.reuse[0] = cached_capture
    baseline_barrier = bool({"stale", "repair"} & set(query.states)) or (
        reuse_enabled and cached_capture is None
    )
    if _REUSE_SCHEDULE_OBSERVER is not None:
        _REUSE_SCHEDULE_OBSERVER(
            dict(
                mode=_REUSE_MODE,
                workers=workers,
                baseline_barrier=baseline_barrier,
                cached_capture=cached_capture is not None,
                scheduled_cases=len(cases) - int(baseline_barrier),
                total_cases=len(cases),
            )
        )

    def solve(case, baseline=None):
        mask = eligibility(
            topology, case.pattern.excluded_nodes, case.pattern.excluded_links
        )
        return _place_case(prepared, query, case, mask, shared, baseline)

    if baseline_barrier:
        # Stale and repair replay the baseline programs: the baseline goes first.
        first = solve(cases[0])
        observed = (
            first,
            *schedule_cases(cases[1:], lambda case: solve(case, first[1]), workers),
        )
    else:
        observed = schedule_cases(cases, solve, workers)
    return PlacementAnalysis(
        prepared,
        analysis_metadata(workers, query.failures),
        OutputSelection(
            query.outputs, query.export_cost_distribution, query.export_details
        ),
        alpha,
        tuple(case for case, _ in observed),
        accounting,
        query,
    )
