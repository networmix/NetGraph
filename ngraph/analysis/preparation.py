"""Assemble one prepared graph, unit and demand binding for a scenario's questions.

Preparation decides what is asked (which steps, demand sets and capacity
questions are active) and compiles one graph at the chosen unit; the units
module calculates conversions, reports and the choice of resolution.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING, NoReturn

import netgraph_core as ngc

from ngraph.analysis.capacity import (
    CapacityQuery,
    evaluate,
    evaluation_options,
    question_pairs,
)
from ngraph.analysis.demands import (
    bind_plans,
    expansion_plans,
    leaves,
    offer_budgets,
    pool_budgets,
    pool_requirements,
    pooled,
    selected_pairs,
)
from ngraph.analysis.topology import (
    NO_ROUTES,
    NamedRoutes,
    PreparedTopology,
    compile_topology,
    outgoing_units,
)
from ngraph.analysis.units import (
    LIMIT,
    UnitsSettings,
    _InputKind,
    choose_resolution,
    make_report,
    quantize,
    split_count,
)
from ngraph.model.demand import (
    PRESETS,
    FlowPolicyPreset,
    _DistributedTEInput,
    _ParsedModel,
    _ShortestPathsInput,
)
from ngraph.model.risk import MembershipIndex
from ngraph.model.selectors import Selector
from ngraph.results import (
    PreparationScope,
    ResolvedDemandSet,
    UnitsReport,
    approximations,
)
from ngraph.utils.values import _input_error, _shown, physical
from ngraph.workflow.base import WORKFLOW_STEP_REGISTRY, step_name
from ngraph.workflow.diagnostics import (
    _MISSING,
    error_context,
    workflow_error,
    workflow_location,
)

if TYPE_CHECKING:
    from ngraph.analysis.controller import ControllerSetup
    from ngraph.analysis.counts import TunnelCountQuery
    from ngraph.scenario import Scenario
    from ngraph.workflow.base import SeedSource


@dataclass(frozen=True)
class StepNeeds:
    """What preparation must know of one workflow step's question.

    ``numerical`` steps are evaluated at the prepared resolution. A step may
    name a demand set to bind, a failure policy, and an earlier step whose
    feasible alpha it uses (one that ``provides_alpha``). ``capacity`` builds
    the step's capacity question, which preparation validates once after
    final compilation; ``inputs`` are that question's physical amounts, by
    field name. ``pool_endpoints`` are the source and target of a question
    whose combined sources are a pool: preparation gives them a private head.
    ``offer_budget`` is a fixed lossy offer every pool leaf of ``demand_set``
    receives; ``counts`` builds a tunnel-count question, which preparation
    validates once after final binding. ``nodes`` and ``links``
    are names the step reads that must exist in the network.
    """

    numerical: bool = False
    demand_set: str | None = None
    failure_policy: str | None = None
    # The failure states a placement step reports for each case, its
    # interaction, and its scale when known at preparation (None: from MSD).
    states: tuple[str, ...] = ()
    interaction: str = "ordered"
    alpha: float | None = 1.0
    alpha_from_step: str | None = None
    provides_alpha: bool = False
    capacity: Callable[[PreparedScenario], CapacityQuery] | None = None
    inputs: Mapping[str, tuple[_InputKind, float]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    pool_endpoints: tuple[Selector, Selector] | None = None
    offer_budget: float | None = None
    counts: Callable[[PreparedScenario], TunnelCountQuery] | None = None
    nodes: tuple[str, ...] = ()
    links: tuple[str, ...] = ()


@dataclass(frozen=True)
class PreparedScenario:
    """One graph, unit and demand binding over a read-only view of a scenario.

    ``units_report`` records the fixed input/count bounds for every analysis.
    """

    scenario: Scenario
    topology: PreparedTopology
    demand_sets: Mapping[str, ResolvedDemandSet]
    units_report: UnitsReport
    _named: NamedRoutes = field(repr=False, compare=False)
    _membership: MembershipIndex = field(repr=False, compare=False)
    # Each step's name, seed and seed source as prepared.
    _steps: tuple[tuple[str, int | None, SeedSource], ...] = field(
        repr=False, compare=False
    )
    # The WCMP controller resolved on this graph, if the scenario declares one.
    _controller: ControllerSetup | None = field(default=None, repr=False, compare=False)


def _options(topology, query, mask):
    return evaluation_options(
        topology,
        query.config,
        query.offer,
        query.design_demand,
        mask,
        ngc.OutputOptions(),
    )


def _validate_capacity_questions(prepared, capacities, counting):
    """Validate final materialized questions without eligible traffic or a solve."""
    topology = prepared.topology
    nothing = topology.graph.eligibility(
        excluded_nodes=range(topology.graph.num_nodes())
    )
    for step, name, needs in capacities:
        try:
            query = needs.capacity(prepared)
            _, _, native_pairs, _ = question_pairs(prepared, query, f"workflow.{name}")
            if isinstance(query.config.routing, ngc.Pinned):
                # A supplied program checks endpoint identities, not just counts.
                checked_pairs = native_pairs
            else:
                arities = {}
                for pair in native_pairs:
                    arities.setdefault((len(pair[0]), len(pair[1])), pair)
                checked_pairs = tuple(arities.values())
            evaluate(
                topology, query, checked_pairs, _options(topology, query, nothing), 1
            )
        except (ValueError, TypeError) as exc:
            raise _labelled(step, exc, prepared.scenario) from exc
    if not counting:
        return
    from ngraph.analysis.counts import _counted, _group_key, _model
    from ngraph.analysis.placement import _endpoints

    for step, name, needs in counting:
        try:
            query = needs.counts(prepared)
            label = f"workflow.{name}"
            offer = quantize(query.offer, topology.q, f"{label}.offer")
            design = quantize(query.design_demand, topology.q, f"{label}.design_demand")
            checked = set()
            for demand in query.demands.demands:
                model = _model(demand, label)
                if demand.pool is not None and offer > demand.pool.offer_limit_units:
                    raise ValueError(
                        f"{label}.offer: demand {demand.id}: offer {offer} units exceeds the "
                        f"prepared lossy budget {demand.pool.offer_limit_units} units of TE "
                        f"ingress pool {demand.pool.head.pool_id}"
                    )
                pair = _endpoints(topology, demand)
                for count, up_to in query.specs:
                    key = (
                        _group_key(model),
                        tuple(pair[0]),
                        tuple(pair[1]),
                        count,
                        up_to,
                    )
                    if key in checked:
                        continue
                    config = _counted(model, count, up_to)
                    ngc.evaluate_pairs(
                        topology.graph,
                        [pair],
                        ngc.EvaluationOptions(
                            config,
                            eligibility=nothing,
                            outputs=query.outputs,
                            offer=offer,
                            design_demand=design,
                        ),
                        workers=1,
                    )
                    checked.add(key)
        except (ValueError, TypeError) as exc:
            raise _labelled(step, exc, prepared.scenario) from exc


def _declared_counts(declaration, heads):
    """Classify a declaration without materializing graph-bound routes or weights."""
    if isinstance(declaration, FlowPolicyPreset):
        declaration = PRESETS[declaration]
    if not isinstance(declaration, (ngc.FlowPolicyConfig, _ParsedModel)):
        return 0, 0
    model = declaration.routing
    count = getattr(model, "tunnel_count", None)
    if count is not None:
        return 0, heads * count.per_head
    equal = (
        isinstance(model, (ngc.ShortestPaths, _ShortestPathsInput))
        and model.allocation == ngc.RouteAllocation.EQUAL
        and model.source_allocation in (None, ngc.SourceAllocation.EQUAL)
        and declaration.admission == ngc.Admission.LOSSLESS
    )
    return int(equal), 0


def _static_groups(scenario, entries, plans_by_name, requested):
    """Read known workflow declarations and expansion leaves before compilation."""
    declared_sets = set(requested)
    declared_sets.update(
        needs.demand_set
        for _, _, needs in entries
        if needs.demand_set is not None and needs.interaction != "simultaneous"
    )
    groups = []
    for name, plans in plans_by_name.items():
        if name not in declared_sets:
            continue
        k = t = 0
        for plan in plans:
            for leaf in leaves(plan.root):
                if leaf.endpoints is None:
                    continue
                heads = (
                    1
                    if pooled(plan.spec.mode, plan.spec.policy)
                    else len(leaf.endpoints.sources)
                )
                local_k, local_t = _declared_counts(plan.spec.policy, heads)
                k += local_k
                t += local_t
        groups.append((name, k, t))
    for step, name, _ in entries:
        if type(step) is WORKFLOW_STEP_REGISTRY.get("MaxFlow"):
            k, tunnels_per_head = _declared_counts(step.declaration, 1)
            if not tunnels_per_head:
                # Each pair contributes exactly the floor, which wins ties.
                # Final question validation still checks every endpoint.
                continue
            try:
                pairs = selected_pairs(
                    scenario.network,
                    step.source,
                    step.target,
                    step.mode,
                    f"step {name}",
                )
            except (ValueError, TypeError) as exc:
                raise _labelled(step, exc, scenario) from exc
            for pair in pairs:
                heads = 1 if pooled(step.mode, step.declaration) else len(pair.sources)
                groups.append((f"workflow.{name}", k, heads * tunnels_per_head))
        elif type(step) is WORKFLOW_STEP_REGISTRY.get("TunnelCountAnalysis"):
            count = max((*step.counts, step.up_to or 0))
            for plan in plans_by_name[step.demand_set]:
                for leaf in leaves(plan.root):
                    if leaf.endpoints is not None:
                        heads = (
                            1
                            if pooled(plan.spec.mode, plan.spec.policy)
                            else len(leaf.endpoints.sources)
                        )
                        groups.append((f"workflow.{name}", 0, heads * count))
    return groups


def _labelled(step, exc, scenario, value=_MISSING):
    """Relabel built-in refusals; extension exceptions pass through unchanged."""
    if type(exc) not in (ValueError, TypeError):
        raise exc
    index = next(i for i, owner in enumerate(scenario.workflow) if owner is step)
    field, reason = error_context(
        exc,
        (f"step {step_name(step)}", f"workflow.{step_name(step)}", type(step).__name__),
    )
    if value is _MISSING:
        value = getattr(step, field, _MISSING)
        if field == "model.routing.edge_weights":
            value = getattr(exc, "_input_value", _MISSING)
    if not isinstance(value, (str, int, float, bool)):
        value = _MISSING
    error = workflow_error(workflow_location(index, step.name), value, reason, field)
    return TypeError(error.args[0]) if type(exc) is TypeError else error


def _step_pools(scenario, capacities, pools):
    """Give each pooled capacity question's sources a pool, unless one exists."""
    network = scenario.network
    for step, name, needs in capacities:
        if needs.pool_endpoints is None:
            continue
        source, target = needs.pool_endpoints
        try:
            (pair,) = selected_pairs(network, source, target, "combine", f"step {name}")
        except (ValueError, TypeError) as exc:
            raise _labelled(step, exc, scenario) from exc
        if pair.sources == pair.destinations and len(pair.sources) == 1:
            continue
        if any(set(members) == set(pair.sources) for members in pools.values()):
            continue
        pool_id = f"workflow.{name}.pair[0]"
        if pool_id in pools:
            raise _labelled(
                step, ValueError(f"pool {pool_id!r} is also a demand id"), scenario
            )
        pools[pool_id] = pair.sources


def _check_controller(topology, setup, resolved, failing, scenario):
    """Refuse an uncalled controller, an ignored tree and unsupported failure states."""
    if not any(demands.controller is not None for demands in resolved.values()):
        raise ValueError(
            "wcmp_controller: no SHORTEST_PATHS_WCMP demand in the prepared demand sets"
        )
    if setup.scope == "group":
        used = {
            router
            for demands in resolved.values()
            for _, table in demands.controller_tables
            for router in table.programmed
        }
        for router, (name, tree, _) in setup.trees.items():
            if router not in used:
                raise ValueError(
                    f"forwarding_groups.{name}: router {tree.router} is programmed "
                    "toward no destination, so the tree would be ignored"
                )
    for step, name, demand_set, states in failing:
        if resolved[demand_set].controller is not None:
            try:
                setup.check_failure_states(
                    topology,
                    resolved[demand_set],
                    states,
                    f"workflow.{name}.failure_states",
                )
            except ValueError as exc:
                raise _labelled(step, exc, scenario) from exc


def prepare_scenario(
    scenario: Scenario, settings: UnitsSettings, requested: tuple[str, ...]
) -> PreparedScenario:
    """Prepare a read-only scenario view; the steps' needs decide what is bound."""
    numerical, active, capacities, providers, failing = [], [], [], set(), []
    simultaneous, counting, declared_inputs, entries = [], [], [], []
    for index, step in enumerate(scenario.workflow):
        name = step_name(step)
        location = workflow_location(index, step.name)
        try:
            needs = step.needs()
        except (ValueError, TypeError) as exc:
            raise _labelled(step, exc, scenario) from exc
        if needs is None:
            continue
        entries.append((step, name, needs))
        if needs.numerical:
            numerical.append(name)
        for kind, names, known in (
            ("node", needs.nodes, scenario.network.nodes),
            ("link", needs.links, scenario.network.links),
        ):
            unknown = [value for value in names if value not in known]
            if unknown:
                raise workflow_error(
                    location,
                    reason=f"unknown {kind} {_shown(unknown[0])}",
                    field="excluded_nodes" if kind == "node" else "excluded_links",
                )
        if needs.demand_set is not None:
            if needs.demand_set not in scenario.demand_sets:
                raise workflow_error(
                    location, needs.demand_set, "unknown demand set", "demand_set"
                )
            if needs.demand_set not in active:
                active.append(needs.demand_set)
        if needs.failure_policy is not None and needs.demand_set is not None:
            failing.append((step, name, needs.demand_set, needs.states))
        if needs.interaction == "simultaneous" and needs.demand_set is not None:
            simultaneous.append(
                (step, name, needs.demand_set, needs.alpha, needs.alpha_from_step)
            )
        if (
            needs.failure_policy is not None
            and needs.failure_policy not in scenario.failure_policies
        ):
            raise workflow_error(
                location,
                needs.failure_policy,
                "unknown failure policy",
                "failure_policy",
            )
        if needs.alpha_from_step is not None and needs.alpha_from_step not in providers:
            raise workflow_error(
                location,
                needs.alpha_from_step,
                "must name an earlier MSD step",
                "alpha_from_step",
            )
        if needs.provides_alpha:
            providers.add(name)
        if needs.capacity is not None:
            capacities.append((step, name, needs))
        if needs.counts is not None:
            counting.append((step, name, needs))
        declared_inputs.append((step, name, needs.inputs))
    scope = PreparationScope(tuple(numerical), tuple(active), requested)
    network = scenario.network
    plans_by_name = {
        name: expansion_plans(network, scenario.demand_sets[name])
        for name in dict.fromkeys((*active, *requested))
    }
    plans = tuple(plan for values in plans_by_name.values() for plan in values)
    identities = {}
    for name, values in plans_by_name.items():
        for plan in values:
            if plan.base_id in identities:
                raise ValueError(
                    f"demand id {plan.base_id!r}: duplicate across sets {identities[plan.base_id]!r} and {name!r}"
                )
            identities[plan.base_id] = name
    pools = pool_requirements(plans)
    _step_pools(scenario, capacities, pools)
    lossy_plans = []
    for step, name, demand_set, alpha, source in simultaneous:
        values = plans_by_name[demand_set]
        pooled_leaves = [
            leaf.id for plan in values for leaf in leaves(plan.root) if leaf.id in pools
        ]
        if alpha is None and pooled_leaves:
            raise _labelled(
                step,
                _input_error(
                    f"workflow.{name}.interaction",
                    f"demand {pooled_leaves[0]}: its scale comes from MSD step {source}, unknown at "
                    f"preparation, so TE ingress pool {pooled_leaves[0]} has no lossy offer budget",
                ),
                scenario,
            )
        if alpha is not None:
            lossy_plans.extend((plan, alpha) for plan in values)

    offers = [
        (plans_by_name[needs.demand_set], needs.offer_budget, f"workflow.{name}.offer")
        for _, name, needs in counting
        if needs.offer_budget is not None and needs.demand_set is not None
    ]

    @cache
    def budgets(q):
        """Each pool's largest known lossy request in units at q."""
        values = pool_budgets(lossy_plans, q)
        for leaf, units in offer_budgets(offers, q).items():
            values[leaf] = max(values.get(leaf, 0), units)
        return values

    def budget_excess(q):
        """Capacity the budgets add above their sources' outgoing capacity."""
        if not budgets(q):
            return 0
        outgoing = outgoing_units(network, q)
        return sum(
            max(0, budget - outgoing[source])
            for pool, budget in budgets(q).items()
            for source in pools[pool]
        )

    inputs, input_sources = {}, {}
    for step, name, values in declared_inputs:
        for field_name, atom in values.items():
            label = f"workflow.{name}.{field_name}"
            inputs[label] = atom
            input_sources[label] = (step, field_name)
    for link_id, link in network.links.items():
        inputs[f"link.{link_id}.capacity"] = ("capacity", link.capacity)
    for plan in plans:
        inputs[f"demand.{plan.base_id}.volume"] = ("demand", plan.spec.volume)
        policy = plan.spec.policy
        if isinstance(policy, _ParsedModel) and isinstance(
            policy.routing, _DistributedTEInput
        ):
            inputs[f"demand.{plan.base_id}.min_unreserved"] = (
                "min_unreserved",
                policy.routing.min_unreserved_bandwidth,
            )

    def input_refusal(exc) -> NoReturn:
        label = getattr(exc, "_input_label", None)
        if label not in input_sources:
            raise exc
        step, field = input_sources[label]
        routing = getattr(getattr(step, "declaration", None), "routing", None)
        if field == "min_unreserved" and isinstance(routing, _DistributedTEInput):
            field = "model.routing.min_unreserved_bandwidth"
        exc.__dict__["_workflow_field"] = field
        raise _labelled(step, exc, scenario, inputs[label][1]) from exc

    try:
        owned_inputs = MappingProxyType(
            {
                label: (kind, physical(value, label))
                for label, (kind, value) in inputs.items()
            }
        )
    except (ValueError, TypeError) as exc:
        input_refusal(exc)
    occurrences = Counter(source for members in pools.values() for source in members)
    coefficients = {
        link_id: 2 + occurrences[link.source] + occurrences[link.target]
        for link_id, link in network.links.items()
    }
    cost_sum = 2 * sum(link.cost for link in network.links.values()) + sum(
        len(members) for members in pools.values()
    )
    if cost_sum >= LIMIT:
        raise ValueError(f"topology augmented cost sum {cost_sum} must be below 2^62")
    groups = _static_groups(scenario, entries, plans_by_name, requested)
    nodes, directed_links = len(network.nodes), 2 * len(network.links)
    group_count = split_count(nodes, directed_links, groups)
    steps: tuple[tuple[str, int | None, SeedSource], ...] = tuple(
        (
            step_name(step),
            step.seed,
            step.seed_source,
        )
        for step in scenario.workflow
    )
    declared = (scenario.routes, scenario.supports, scenario.weights)
    try:
        q, limited_by, range_limit = choose_resolution(
            settings, owned_inputs, coefficients, group_count[3], budget_excess
        )
    except (ValueError, TypeError) as exc:
        input_refusal(exc)
    membership = MembershipIndex.build(network)
    topology = compile_topology(network, q, pools=pools, budgets=budgets(q))
    named = NO_ROUTES
    if any(declared):
        from ngraph.analysis.programs import compile_named

        named = compile_named(
            topology,
            routes=scenario.routes,
            supports=scenario.supports,
            weights=scenario.weights,
        )
    setup = None
    if scenario.wcmp_controller is not None:
        from ngraph.analysis.controller import compile_setup

        setup = compile_setup(topology, scenario)
    resolved = {
        name: bind_plans(topology, named, name, values, setup)
        for name, values in plans_by_name.items()
    }
    if setup is not None:
        _check_controller(topology, setup, resolved, failing, scenario)
    report = make_report(
        q,
        settings,
        scope,
        owned_inputs,
        nodes,
        directed_links,
        group_count,
        limited_by,
        range_limit,
        int(topology.graph.edge_capacity_units().sum()),
        int(topology.graph.edge_costs().sum()),
    )
    report = report.with_approximations(
        tuple(
            entry for demands in resolved.values() for entry in approximations(demands)
        )
    )
    prepared = PreparedScenario(
        scenario,
        topology,
        MappingProxyType(resolved),
        report,
        named,
        membership,
        steps,
        setup,
    )
    _validate_capacity_questions(prepared, capacities, counting)
    return prepared
