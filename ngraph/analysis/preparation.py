"""Assemble one prepared graph, unit and demand binding for a scenario's questions.

Preparation decides what is asked (which steps, demand sets and capacity
questions are active) and observes each candidate resolution once; the units
module calculates conversions, reports and the choice of resolution.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from functools import cache
from types import MappingProxyType
from typing import TYPE_CHECKING

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
    pool_budgets,
    pool_requirements,
    selected_pairs,
)
from ngraph.analysis.placement import (
    _observation_records,
    policy_roster,
    remove_policies,
    replace_matrix,
)
from ngraph.analysis.precision import (
    expansion_bounds,
    placement_splits,
    query_has_splits,
    query_splits,
)
from ngraph.analysis.topology import (
    NO_ROUTES,
    NamedRoutes,
    PreparedTopology,
    compile_topology,
    cost_units,
    outgoing_units,
)
from ngraph.analysis.units import (
    LIMIT,
    UnitsSettings,
    _InputKind,
    choose_resolution,
    input_observations,
    make_report,
    with_splits,
)
from ngraph.model.demand import _DistributedTEInput, _ParsedModel
from ngraph.model.risk import MembershipIndex
from ngraph.model.selectors import Selector
from ngraph.results import (
    InputConstraint,
    InputQuantization,
    PreparationScope,
    ResolvedDemandSet,
    UnitsReport,
    approximations,
)
from ngraph.utils.values import physical

if TYPE_CHECKING:
    from ngraph.analysis.controller import ControllerSetup
    from ngraph.scenario import Scenario
    from ngraph.workflow.base import SeedSource


@dataclass(frozen=True)
class StepNeeds:
    """What preparation must know of one workflow step's question.

    ``numerical`` steps are evaluated at the prepared resolution. A step may
    name a demand set to bind, a failure policy, and an earlier step whose
    feasible alpha it uses (one that ``provides_alpha``). ``capacity`` builds
    the step's capacity question, which preparation evaluates once per
    candidate resolution; ``inputs`` are that question's physical amounts, by
    field name. ``pool_endpoints`` are the source and target of a question
    whose combined sources are a pool: preparation gives them a private head.
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


@dataclass(frozen=True)
class PreparedScenario:
    """One graph, unit and demand binding over a read-only view of a scenario.

    ``units_report`` is the nominal preparation's report; each analysis
    returns its own precision misses beside it.
    """

    scenario: Scenario
    topology: PreparedTopology
    demand_sets: Mapping[str, ResolvedDemandSet]
    units_report: UnitsReport
    _named: NamedRoutes = field(repr=False, compare=False)
    _membership: MembershipIndex = field(repr=False, compare=False)
    # Each physical input's kind and value, and its exact observation.
    _inputs: Mapping[str, tuple[_InputKind, float]] = field(repr=False, compare=False)
    _input_observations: Mapping[
        str, tuple[InputQuantization, InputConstraint | None]
    ] = field(repr=False, compare=False)
    # Each step's name, seed and seed source as prepared.
    _steps: tuple[tuple[str, int | None, SeedSource], ...] = field(
        repr=False, compare=False
    )
    # The WCMP controller resolved on this graph, if the scenario declares one.
    _controller: ControllerSetup | None = field(default=None, repr=False, compare=False)


def _nominal_splits(prepared, demands, precision):
    """Observe one native nominal placement on a private ledger."""
    topology = prepared.topology
    ledger, owners = policy_roster(topology, demands.demands, topology.disabled)
    try:
        results = replace_matrix(
            ledger, owners, tuple(d.nominal_units for d in demands.demands)
        )
        records = _observation_records(prepared._named, demands, owners)
        return placement_splits(
            topology,
            prepared._named,
            demands,
            owners,
            results,
            records,
            topology.disabled,
            1.0,
            precision,
        )
    finally:
        remove_policies(owners)


def _options(topology, query, mask):
    return evaluation_options(
        topology,
        query.config,
        query.offer,
        query.design_demand,
        mask,
        ngc.OutputOptions(),
    )


def _capacity_splits(prepared, step, name, needs, precision):
    """Observe one capacity question's nominal evaluation."""
    topology = prepared.topology
    try:
        query = needs.capacity(prepared)
        _, jobs, native_pairs, pools = question_pairs(
            prepared, query, f"workflow.{name}"
        )
        if not query_has_splits(query):
            # No split constraint needs this question's amounts; one call with
            # no eligible node applies the native checks without solving.
            nothing = topology.graph.eligibility(
                excluded_nodes=range(topology.graph.num_nodes())
            )
            evaluate(
                topology, query, native_pairs[:1], _options(topology, query, nothing), 1
            )
            return [], []
        splits, unverified = [], []
        observations = evaluate(
            topology,
            query,
            native_pairs,
            _options(topology, query, topology.disabled),
            1,
        )
        for (index, pair), result in zip(jobs, observations, strict=True):
            local, opaque = query_splits(
                topology,
                prepared._named,
                query,
                pair,
                result.delivered,
                topology.disabled,
                f"workflow.{name}.pair[{index}]",
                precision,
                pools.get(index),
            )
            splits.extend(local)
            unverified.extend(opaque)
        return splits, unverified
    except (ValueError, TypeError) as exc:
        raise _labelled(step, exc) from exc


def _labelled(step, exc):
    """A step's refusal, labelled with its YAML declaration if it has one."""
    label = step.yaml_label
    if label is None or str(exc).startswith(label + ":"):
        return exc
    return type(exc)(f"{label}: {exc}")


def _step_pools(network, capacities, pools):
    """Give each pooled capacity question's sources a pool, unless one exists."""
    for step, name, needs in capacities:
        if needs.pool_endpoints is None:
            continue
        source, target = needs.pool_endpoints
        try:
            (pair,) = selected_pairs(network, source, target, "combine", f"step {name}")
        except (ValueError, TypeError) as exc:
            raise _labelled(step, exc) from exc
        if pair.sources == pair.destinations and len(pair.sources) == 1:
            continue
        if any(set(members) == set(pair.sources) for members in pools.values()):
            continue
        pool_id = f"workflow.{name}.pair[0]"
        if pool_id in pools:
            raise ValueError(f"step {name}: pool {pool_id!r} is also a demand id")
        pools[pool_id] = pair.sources


def _check_controller(topology, setup, resolved, failing):
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
                raise _labelled(step, exc) from None


def prepare_scenario(
    scenario: Scenario, settings: UnitsSettings, requested: tuple[str, ...]
) -> PreparedScenario:
    """Prepare a read-only scenario view; the steps' needs decide what is bound."""
    numerical, active, capacities, providers, failing = [], [], [], set(), []
    simultaneous = []
    for step in scenario.workflow:
        name = step.name or type(step).__name__
        needs = step.needs()
        if needs is None:
            continue
        if needs.numerical:
            numerical.append(name)
        if needs.demand_set is not None:
            if needs.demand_set not in scenario.demand_sets:
                raise ValueError(
                    f"step {name}: unknown demand set {needs.demand_set!r}"
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
            raise ValueError(
                f"step {name}: unknown failure policy {needs.failure_policy!r}"
            )
        if needs.alpha_from_step is not None and needs.alpha_from_step not in providers:
            raise ValueError(
                f"step {name}: alpha_from_step {needs.alpha_from_step!r} must name an earlier MSD step"
            )
        if needs.provides_alpha:
            providers.add(name)
        if needs.capacity is not None:
            capacities.append((step, name, needs))
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
    _step_pools(network, capacities, pools)
    lossy_plans = []
    for step, name, demand_set, alpha, source in simultaneous:
        values = plans_by_name[demand_set]
        pooled = [
            leaf.id for plan in values for leaf in leaves(plan.root) if leaf.id in pools
        ]
        if alpha is None and pooled:
            raise _labelled(
                step,
                ValueError(
                    f"workflow.{name}.interaction: demand {pooled[0]}: its scale comes "
                    f"from MSD step {source}, unknown at "
                    f"preparation, so TE ingress pool {pooled[0]} has no lossy offer "
                    "budget"
                ),
            )
        if alpha is not None:
            lossy_plans.extend((plan, alpha) for plan in values)

    @cache
    def budgets(q):
        """Each pool's largest known simultaneous request in units at q."""
        return pool_budgets(lossy_plans, q)

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

    inputs = {}
    for _, name, needs in capacities:
        for field_name, atom in needs.inputs.items():
            inputs[f"workflow.{name}.{field_name}"] = atom
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
    owned_inputs = MappingProxyType(
        {
            label: (kind, physical(value, label))
            for label, (kind, value) in inputs.items()
        }
    )
    occurrences = Counter(source for members in pools.values() for source in members)
    coefficients = {
        link_id: 2 + occurrences[link.source] + occurrences[link.target]
        for link_id, link in network.links.items()
    }
    cost_sum = 2 * sum(
        cost_units(link.cost, f"link.{link_id}.cost")
        for link_id, link in network.links.items()
    ) + sum(len(members) for members in pools.values())
    if cost_sum >= LIMIT:
        raise ValueError(f"topology augmented cost sum {cost_sum} must be below 2^62")
    expansion, _ = expansion_bounds(plans, 1.0, settings.precision)
    steps: tuple[tuple[str, int | None, SeedSource], ...] = tuple(
        (
            step.name or type(step).__name__,
            step.seed,
            step.seed_source,
        )
        for step in scenario.workflow
    )
    declared = (scenario.routes, scenario.supports, scenario.weights)
    membership = None

    def candidate(q):
        nonlocal membership
        if membership is None:
            membership = MembershipIndex.build(network)
        topology = compile_topology(network, q, pools=pools, budgets=budgets(q))
        named = NO_ROUTES
        if any(declared):
            # Programs load only for scenarios that declare routes or weights.
            from ngraph.analysis.programs import compile_named

            named = compile_named(
                topology,
                routes=scenario.routes,
                supports=scenario.supports,
                weights=scenario.weights,
            )
        setup = None
        if scenario.wcmp_controller is not None:
            # The controller loads only for scenarios that declare it.
            from ngraph.analysis.controller import compile_setup

            setup = compile_setup(topology, scenario)
        resolved = {
            name: bind_plans(topology, named, name, values, setup)
            for name, values in plans_by_name.items()
        }
        if setup is not None:
            _check_controller(topology, setup, resolved, failing)
        observations = input_observations(inputs, q, settings.precision)
        report = make_report(
            q,
            settings,
            scope,
            inputs,
            int(topology.graph.edge_capacity_units().sum()),
            int(topology.graph.edge_costs().sum()),
            observations=observations,
        )
        # The chosen candidate's report holds exactly its own tables' approximations.
        report = report.with_approximations(
            tuple(
                entry
                for demands in resolved.values()
                for entry in approximations(demands)
            )
        )
        prepared = PreparedScenario(
            scenario,
            topology,
            MappingProxyType(resolved),
            report,
            named,
            membership,
            owned_inputs,
            observations,
            steps,
            setup,
        )
        splits, unverified = [], []
        for demands in resolved.values():
            local, opaque = _nominal_splits(prepared, demands, settings.precision)
            splits.extend(local)
            unverified.extend(opaque)
        for step, name, needs in capacities:
            local, opaque = _capacity_splits(
                prepared, step, name, needs, settings.precision
            )
            splits.extend(local)
            unverified.extend(opaque)
        report = with_splits(report, tuple(splits), tuple(unverified))
        return replace(prepared, units_report=report), report.target_met

    prepared, finer_failure = choose_resolution(
        settings,
        inputs,
        coefficients,
        (c.q_upper_bound for c in expansion),
        candidate,
        budget_excess,
    )
    if finer_failure is not None:
        report = prepared.units_report
        prepared = replace(
            prepared,
            units_report=replace(
                report, binding_constraints=(*report.binding_constraints, finer_failure)
            ),
        )
    return prepared
