"""Canonical physical selections and total-preserving demand expansion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import product
from types import MappingProxyType
from typing import TYPE_CHECKING

import netgraph_core as ngc

from ngraph.analysis.topology import NamedRoutes, PreparedTopology
from ngraph.analysis.units import quantize, scaled_units, split_units
from ngraph.model.demand import (
    PRESETS,
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    PinnedRoutes,
    _CentralizedTEInput,
    _DistributedTEInput,
    _ParsedModel,
    _ShortestPathsInput,
)
from ngraph.model.network import Network
from ngraph.model.selectors import Selector, select_nodes
from ngraph.results import (
    DiscardedShare,
    Endpoints,
    ExpansionAccounting,
    ExpansionLeaf,
    ExpansionParent,
    ExpansionSplit,
    PoolHead,
    PoolMetadata,
    ResolvedDemand,
    ResolvedDemandSet,
    SyntheticIngress,
)

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


@dataclass(frozen=True)
class _Expansion:
    """A physical declaration and its ordered tree, before graph-owned binding."""

    spec: DemandSpec
    base_id: str
    declaration_ordinal: int
    expand_leaf_index: int | None
    root: ExpansionSplit | ExpansionLeaf


def selected_groups(
    network: Network, selector: Selector, label: str
) -> dict[str, tuple[str, ...]]:
    if not isinstance(selector, Selector):
        raise TypeError(f"{label}: expected a Selector")
    try:
        groups = select_nodes(network, selector, default_active_only=True)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{label}: {exc}") from exc
    return {
        label: tuple(sorted({node.name for node in nodes}))
        for label, nodes in sorted(groups.items())
    }


def refuse_overlap(
    sources: Sequence[str], destinations: Sequence[str], label: str
) -> None:
    common = set(sources).intersection(destinations)
    if common and not (
        len(sources) == len(destinations) == 1 and tuple(sources) == tuple(destinations)
    ):
        raise ValueError(
            f"{label}: non-diagonal source/target overlap: {sorted(common)}"
        )


def selected_pairs(
    network: Network,
    source: Selector,
    target: Selector,
    mode: str,
    label: str,
) -> tuple[Endpoints, ...]:
    """One shared selection/overlap rule for capacity, paths and sensitivity."""
    sources = selected_groups(network, source, label + ".source")
    targets = selected_groups(network, target, label + ".target")
    if not sources:
        raise ValueError(f"{label}.source: empty selection")
    if not targets:
        raise ValueError(f"{label}.target: empty selection")
    if mode == "combine":
        pairs = [
            Endpoints(
                tuple(sorted({n for group in sources.values() for n in group})),
                tuple(sorted({n for group in targets.values() for n in group})),
            )
        ]
    elif mode == "pairwise":
        pairs = [
            Endpoints(sources[s], targets[t]) for s, t in product(sources, targets)
        ]
    else:
        raise ValueError(f"{label}.mode: expected combine or pairwise")
    for i, pair in enumerate(pairs):
        refuse_overlap(pair.sources, pair.destinations, f"{label}.pair[{i}]")
    return tuple(pairs)


def expansion_plans(network: Network, specs: DemandSet) -> tuple[_Expansion, ...]:
    """Resolve physical endpoints once; zero and discarded leaves remain in the tree."""
    plans = []
    for index, spec in enumerate(specs.demands):
        ordinal = (
            index if spec.declaration_ordinal is None else spec.declaration_ordinal
        )
        expand_index = spec.expand_leaf_index
        base_id = spec.id if spec.id is not None else f"{specs.name}|{ordinal}"
        if expand_index is not None:
            base_id += f"|{expand_index}"
        label = f"demands.{specs.name}[{ordinal}]({base_id})"
        sources = selected_groups(network, spec.source, label + ".source")
        targets = selected_groups(network, spec.target, label + ".target")
        order = 0

        def leaf(src=(), dst=(), reason=None, *, base_id=base_id, label=label):
            nonlocal order
            identity = f"{base_id}|{order}"
            if reason is None:
                if not src or not dst:
                    reason = "empty_selection"
                else:
                    refuse_overlap(src, dst, label)
                    if len(src) == len(dst) == 1 and src == dst:
                        reason = "self_pair"
            item = ExpansionLeaf(
                identity,
                order,
                Endpoints(tuple(src), tuple(dst)) if reason is None else None,
                reason,
            )
            order += 1
            return item

        def expand_groups(src, dst, branch, *, spec=spec, label=label, leaf=leaf):
            if not src or not dst:
                return leaf(reason="empty_selection")
            if spec.mode == "combine":
                return leaf(
                    tuple(sorted({n for group in src.values() for n in group})),
                    tuple(sorted({n for group in dst.values() for n in group})),
                )
            # Pairwise expansion permits singleton matrix diagonals, never overlapping groups.
            for slabel, tlabel in product(src, dst):
                refuse_overlap(src[slabel], dst[tlabel], f"{label}.{slabel}->{tlabel}")
            src_names = sorted({n for group in src.values() for n in group})
            dst_names = sorted({n for group in dst.values() for n in group})
            return ExpansionSplit(
                branch,
                tuple(leaf((s,), (t,)) for s, t in product(src_names, dst_names)),
            )

        if spec.group_mode == "flatten":
            root = expand_groups(sources, targets, label + ".pairs")
        elif spec.group_mode == "per_group":
            labels = (
                list(sources)
                if spec.mode == "combine"
                else sorted(sources.keys() & targets.keys())
            )
            children = [
                expand_groups(
                    {name: sources[name]},
                    targets if spec.mode == "combine" else {name: targets[name]},
                    label + ".group." + name,
                )
                for name in labels
            ]
            root = (
                ExpansionSplit(label + ".groups", tuple(children))
                if children
                else leaf(reason="empty_selection")
            )
        else:
            children = []
            for slabel, tlabel in product(sources, targets):
                children.append(
                    leaf(reason="filtered")
                    if slabel == tlabel
                    else expand_groups(
                        {slabel: sources[slabel]},
                        {tlabel: targets[tlabel]},
                        label + f".groups.{slabel}->{tlabel}",
                    )
                )
            root = (
                ExpansionSplit(label + ".group_pairs", tuple(children))
                if children
                else leaf(reason="empty_selection")
            )
        plans.append(_Expansion(spec, base_id, ordinal, expand_index, root))
    seen = {}
    for plan in plans:
        if plan.base_id in seen:
            raise ValueError(
                f"demands.{specs.name}: duplicate id {plan.base_id!r} at declarations {seen[plan.base_id]} and {plan.declaration_ordinal}"
            )
        seen[plan.base_id] = plan.declaration_ordinal
    return tuple(plans)


def leaves(root: ExpansionSplit | ExpansionLeaf) -> tuple[ExpansionLeaf, ...]:
    if isinstance(root, ExpansionLeaf):
        return (root,)
    return tuple(leaf for child in root.children for leaf in leaves(child))


# Combined sources asked with these presets share one private head (a pool).
POOLED_PRESETS = frozenset(
    (FlowPolicyPreset.TE_ECMP_16_LSP, FlowPolicyPreset.TE_ECMP_UP_TO_256_LSP)
)


def pooled(mode: str, declaration: object) -> bool:
    """Whether a question's combined sources are a pool."""
    return (
        mode == "combine"
        and isinstance(declaration, FlowPolicyPreset)
        and declaration in POOLED_PRESETS
    )


def pool_requirements(plans: Sequence[_Expansion]) -> dict[str, tuple[str, ...]]:
    pools = {}
    for plan in plans:
        if pooled(plan.spec.mode, plan.spec.policy):
            for leaf in leaves(plan.root):
                if leaf.endpoints is not None:
                    pools[leaf.id] = leaf.endpoints.sources
    return pools


def materialize_config(
    topology: PreparedTopology,
    named: NamedRoutes,
    endpoints: Endpoints,
    policy,
) -> ngc.FlowPolicyConfig:
    if isinstance(policy, FlowPolicyPreset):
        return PRESETS[policy]
    if isinstance(policy, ngc.FlowPolicyConfig):
        return policy
    if isinstance(policy, PinnedRoutes):
        # Programs load only for scenarios that pin routes.
        from ngraph.analysis.programs import pinned_config

        return pinned_config(topology, endpoints, policy, named)
    if not isinstance(policy, _ParsedModel):
        raise TypeError("model: expected a declared model or native FlowPolicyConfig")
    model = policy.routing
    if isinstance(model, _ShortestPathsInput):
        vector = None
        if model.edge_weights is not None:
            vector = named.vector(model.edge_weights)
        routing = ngc.ShortestPaths(
            allocation=model.allocation,
            source_allocation=model.source_allocation,
            weight_basis=model.weight_basis,
            edge_weights=vector,
            tie_break=model.tie_break,
            multipath=model.multipath,
            parallel_edges=model.parallel_edges,
        )
    elif isinstance(model, _DistributedTEInput):
        routing = ngc.DistributedTE(
            model.tunnel_count,
            cost_ceiling=model.cost_ceiling,
            min_unreserved_bandwidth=quantize(
                model.min_unreserved_bandwidth,
                topology.q,
                "model.min_unreserved_bandwidth",
            ),
            tie_break=model.tie_break,
            parallel_edges=model.parallel_edges,
        )
    elif isinstance(model, _CentralizedTEInput):
        routing = ngc.CentralizedTE(
            source_allocation=model.source_allocation,
            tunnel_count=model.tunnel_count,
            prefer_headroom=model.prefer_headroom,
        )
    else:
        raise TypeError("model.routing: unknown declared routing")
    return ngc.FlowPolicyConfig(routing=routing, admission=policy.admission)


def declared_split(
    named: NamedRoutes,
    config: ngc.FlowPolicyConfig | None,
    policy: object = None,
) -> tuple[ngc.RouteAllocation | None, ngc.WeightBasis | None]:
    """The route allocation and weight basis a declared model splits by.

    Shortest paths report their native allocation and, when weighted, its
    basis. A named pinned declaration reports them only when one of its
    routes is a support DAG (any other allocation counts as equal). Other
    models split by neither.
    """
    model = None if config is None else config.routing
    if isinstance(model, ngc.ShortestPaths):
        if model.allocation != ngc.RouteAllocation.WEIGHTED:
            return model.allocation, None
        return model.allocation, model.weight_basis or ngc.WeightBasis.CAPACITY
    if isinstance(policy, PinnedRoutes) and any(
        named.route_specs[name].support is not None for name in policy.routes
    ):
        if policy.allocation != ngc.RouteAllocation.WEIGHTED:
            return ngc.RouteAllocation.EQUAL, None
        return ngc.RouteAllocation.WEIGHTED, (
            policy.weight_basis or ngc.WeightBasis.CAPACITY
        )
    return None, None


def residual_weights(named: NamedRoutes, parents) -> bool:
    """Whether any declared demand weights its split by the residual snapshot."""
    return any(
        declared_split(named, parent.config, parent.policy)[1]
        == ngc.WeightBasis.RESIDUAL_SNAPSHOT
        for parent in parents
    )


def expand_units(
    root: ExpansionSplit | ExpansionLeaf, total: int
) -> tuple[tuple[ExpansionLeaf, int], ...]:
    if isinstance(root, ExpansionLeaf):
        return ((root, total),)
    shares = split_units(total, len(root.children))
    return tuple(
        item
        for child, share in zip(root.children, shares, strict=True)
        for item in expand_units(child, share)
    )


def scaled_expansion(
    demands: ResolvedDemandSet, alpha: float, q: float
) -> tuple[Mapping[str, int], tuple[ExpansionAccounting, ...]]:
    """Rescale physical parents; retain exact discard accounting and zero leaves."""
    amounts, accounting = {}, []
    for parent in demands.expansion_template:
        declared = scaled_units(
            parent.physical_volume, alpha, q, f"demand.{parent.base_id}.volume"
        )
        discards = []
        resolved = 0
        for leaf, amount in expand_units(parent.root, declared):
            if leaf.discard_reason is None:
                amounts[leaf.id] = amount
                resolved += amount
            else:
                discards.append(DiscardedShare(leaf.id, amount, leaf.discard_reason))
        accounting.append(
            ExpansionAccounting(
                parent.base_id, declared, resolved, declared - resolved, tuple(discards)
            )
        )
    return MappingProxyType(amounts), tuple(accounting)


def leaf_amounts(root, volume: float) -> dict[str, Fraction]:
    """Each leaf's exact physical share of its declaration, before any rounding."""
    amounts: dict[str, Fraction] = {}

    def visit(node, amount):
        if isinstance(node, ExpansionLeaf):
            amounts[node.id] = amount
            return
        for child in node.children:
            visit(child, amount / len(node.children))

    visit(root, Fraction(volume))
    return amounts


def controlled(controller, policy) -> bool:
    """Whether the WCMP controller programs a demand of this declared policy."""
    return controller is not None and policy == FlowPolicyPreset.SHORTEST_PATHS_WCMP


def _plan_label(plan, name):
    if plan.spec.yaml_label is not None:
        return plan.spec.yaml_label
    return f"demands.{name}[{plan.declaration_ordinal}]({plan.base_id})"


def bind_plans(
    topology: PreparedTopology,
    named: NamedRoutes,
    name: str,
    plans: Sequence[_Expansion],
    controller=None,
) -> ResolvedDemandSet:
    """Bind a demand set's leaves; ``controller`` is the prepared controller setup.

    The controller's tables are built once per destination, from every
    programmed leaf of the set, before any leaf's program.
    """
    tables, reports = (), None
    consumers = [
        (plan, leaf)
        for plan in plans
        if controlled(controller, plan.spec.policy)
        for leaf in leaves(plan.root)
        if leaf.endpoints is not None
    ]
    if consumers:
        assert controller is not None
        for plan, leaf in consumers:
            controller.check_leaf(topology, leaf.endpoints, _plan_label(plan, name))
        amounts = {
            plan.base_id: leaf_amounts(plan.root, plan.spec.volume)
            for plan in plans
            if controlled(controller, plan.spec.policy)
        }
        tables, reports = controller.tables(
            topology,
            name,
            [
                (leaf.endpoints, amounts[plan.base_id][leaf.id])
                for plan, leaf in consumers
            ],
        )
    by_name = dict(tables)
    parents, resolved = [], []
    for plan in plans:
        error_label = plan.spec.yaml_label
        first_config = None
        programmed = controlled(controller, plan.spec.policy)
        for leaf in leaves(plan.root):
            if leaf.endpoints is None:
                continue
            try:
                if programmed:
                    assert controller is not None
                    config = controller.leaf_config(
                        topology,
                        by_name[leaf.endpoints.destinations[0]],
                        leaf.endpoints,
                    )
                elif first_config is not None and not isinstance(
                    plan.spec.policy, PinnedRoutes
                ):
                    config = first_config
                else:
                    config = materialize_config(
                        topology, named, leaf.endpoints, plan.spec.policy
                    )
            except (ValueError, TypeError) as exc:
                if error_label is None:
                    raise
                raise type(exc)(f"{error_label}: {exc}") from exc
            first_config = first_config or config
            pool = None
            if leaf.id in topology.pool_heads:
                pool = PoolMetadata(PoolHead(leaf.id, leaf.endpoints.sources))
            resolved.append(
                ResolvedDemand(
                    leaf.id,
                    plan.base_id,
                    leaf.endpoints,
                    plan.spec.priority,
                    len(resolved),
                    0,
                    config,
                    pool,
                    error_label,
                )
            )
        try:
            if first_config is None:
                # Validate declaration types/options even if its selected share is intentionally discarded.
                if isinstance(plan.spec.policy, PinnedRoutes):
                    from ngraph.analysis.programs import validate_pinned

                    validate_pinned(
                        plan.spec.policy, named.route_specs, named.weight_specs
                    )
                else:
                    first_config = materialize_config(
                        topology, named, Endpoints((), ()), plan.spec.policy
                    )
        except (ValueError, TypeError) as exc:
            if error_label is None:
                raise
            raise type(exc)(f"{error_label}: {exc}") from exc
        parents.append(
            ExpansionParent(
                plan.spec.source,
                plan.spec.target,
                plan.spec.priority,
                plan.spec.policy,
                first_config,
                plan.base_id,
                plan.declaration_ordinal,
                plan.expand_leaf_index,
                float(plan.spec.volume),
                plan.spec.mode,
                plan.spec.group_mode,
                plan.root,
            )
        )
    provisional = ResolvedDemandSet(name, (), (), tuple(parents))
    amounts, accounting = scaled_expansion(provisional, 1.0, topology.q)
    demands = tuple(
        replace(d, nominal_units=amounts[d.id])
        for d in sorted(resolved, key=lambda d: (d.priority, d.order))
    )
    return ResolvedDemandSet(name, demands, accounting, tuple(parents), tables, reports)


def resolve_demands(prepared: PreparedScenario, specs: DemandSet) -> ResolvedDemandSet:
    topology = prepared.topology
    plans = expansion_plans(prepared.scenario.network, specs)
    required = pool_requirements(plans)
    missing = set(required) - topology.pool_heads.keys()
    if missing:
        raise ValueError(
            f"demand set {specs.name}: pools {sorted(missing)} were not included in topology preparation"
        )
    # A pool is the prepared ingress of its sources; other sources need a new one.
    prepared_sources = {}
    for ref in topology.edge_refs:
        if isinstance(ref, SyntheticIngress) and ref.pool_id in required:
            prepared_sources.setdefault(ref.pool_id, set()).add(ref.source)
    changed = sorted(
        pool
        for pool, sources in required.items()
        if set(sources) != prepared_sources[pool]
    )
    if changed:
        raise ValueError(
            f"demand set {specs.name}: pools {changed} select other sources than "
            "their prepared ingress; prepare again"
        )
    return bind_plans(
        topology, prepared._named, specs.name, plans, prepared._controller
    )
