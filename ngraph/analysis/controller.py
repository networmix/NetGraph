"""The WCMP controller: one destination-wide weight table per demand set and destination.

A routing domain (an IGP domain and the BGP-edge routers around it) gives
each destination one DAG of routes. The controller programs the source
routers of the ``SHORTEST_PATHS_WCMP`` demands toward that destination:
``next_hop`` weights their next hops by progressive filling, ``group`` uses
their declared forwarding groups, whose root shares are fixed caps. Every
other router keeps equal-cost splitting (ECMP). Each demand forwards on the
one table through its own native program; nothing here forwards traffic.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from math import gcd, lcm
from types import MappingProxyType
from typing import cast

import netgraph_core as ngc

from ngraph.analysis.demands import selected_groups
from ngraph.analysis.precision import effective_rows, propagate
from ngraph.analysis.programs import dag_from_edges, domain_dag, edge_id
from ngraph.analysis.topology import PreparedTopology
from ngraph.model.demand import PRESETS, FlowPolicyPreset, ForwardingGroup
from ngraph.model.network import DirectedLink
from ngraph.results import (
    DeadCap,
    Endpoints,
    MemberWeight,
    ProgrammedRouter,
    SourceWeight,
    TableReport,
    WeightApproximation,
)

LIMIT = 1 << 62


@dataclass(frozen=True)
class DestinationTable:
    """The controller's table toward one destination, on one prepared graph.

    ``weights`` is the one weight vector, by EdgeId: programmed rows carry
    their integer weights, other DAG routers weight 1 on every member.
    ``encoding`` is how the table reaches native forwarding (EQUAL when every
    programmed row that receives traffic is equal and positive).
    ``approximations`` hold each router whose exact weights reached 2^62, with
    the largest relative error of its apportioned shares; for ``all_routers``,
    the one source vector's entry names the source with the largest error.
    ``source_weights`` holds each ``all_routers`` source's nominal physical
    demand and its integer weight. ``leaves`` are the (sources, exact amount)
    the table was built from, so a failure case can build its own.

    A failure case's group table keeps a dead root group's members at their
    nominal shares: ``dropped`` are those members, where its forwarding drops
    the traffic (``holes`` excludes them), and ``dead_caps`` the dead groups.
    """

    destination: int
    dag: ngc.PredecessorDAG
    weights: tuple[int, ...]
    encoding: ngc.RouteAllocation
    programmed: tuple[int, ...]
    approximations: tuple[WeightApproximation, ...]
    source_weights: tuple[tuple[int, Fraction, int], ...] | None = None
    leaves: tuple[tuple[tuple[int, ...], Fraction], ...] = ()
    dropped: tuple[int, ...] = ()
    dead_caps: tuple[DeadCap, ...] = ()
    holes: ngc.Eligibility | None = None


def apportion(exact: Sequence[int], total: int) -> list[int]:
    """Highest averages over ``total`` units with one unit reserved per positive member.

    Equal to giving every positive member one unit, then each further unit to
    the largest ``weight / (held + 1)``, earlier member on ties; computed from
    the proportional floor, then adjusted by the same quotients.
    """
    whole = sum(exact)
    held = [max(1, total * value // whole) if value else 0 for value in exact]
    positive = [i for i, value in enumerate(exact) if value]
    while sum(held) > total:
        j = min(
            (i for i in positive if held[i] > 1),
            key=lambda i: (Fraction(exact[i], held[i]), -i),
        )
        held[j] -= 1
    while sum(held) < total:
        i = max(positive, key=lambda i: (Fraction(exact[i], held[i] + 1), -i))
        held[i] += 1
    return held


def _reduced(values: Sequence[Fraction]) -> list[int]:
    """Nonnegative exact ratios as integers, by common denominator and gcd."""
    if not any(values):
        return [0] * len(values)
    scale = lcm(*(value.denominator for value in values))
    exact = [int(value * scale) for value in values]
    common = gcd(*exact)
    return [value // common for value in exact]


def apportioned(shares: Sequence[Fraction]) -> tuple[list[int], dict[int, Fraction]]:
    """Exact rational shares as reduced integers, and their errors by member.

    Weights that reach 2^62 are apportioned over a total of 2^62 - 1: every
    positive member first holds one unit, then each unit goes to the largest
    ``share / (held + 1)``, earlier member on ties. The second value holds each
    positive member's relative error of its normalized share (empty when exact).
    """
    exact = _reduced(shares)
    if not any(exact) or max(exact) < LIMIT:
        return exact, {}
    total = LIMIT - 1
    whole = sum(exact)
    held = apportion(exact, total)
    errors = {
        i: abs(Fraction(held[i], total) - Fraction(exact[i], whole))
        / Fraction(exact[i], whole)
        for i, value in enumerate(exact)
        if value
    }
    return held, errors


def integer_weights(shares: Sequence[Fraction]) -> tuple[list[int], Fraction | None]:
    """``apportioned`` with the largest relative error (None when exact)."""
    held, errors = apportioned(shares)
    return held, max(errors.values()) if errors else None


def fill(columns: Sequence[Mapping[int, Fraction]], alone, capacity):
    """Normalized progressive filling of one router's members.

    Every active member grows in proportion to what it carries alone; when an
    edge saturates, every active member using it stops. Members that carry
    nothing alone get 0.
    """
    x = [Fraction(0)] * len(columns)
    active = [i for i, value in enumerate(alone) if value > 0]
    frozen: dict[int, Fraction] = {}
    while active:
        rate: dict[int, Fraction] = {}
        for i in active:
            for edge, share in columns[i].items():
                rate[edge] = rate.get(edge, Fraction(0)) + alone[i] * share
        level = min(
            (int(capacity[edge]) - frozen.get(edge, 0)) / value
            for edge, value in rate.items()
        )
        saturated = {
            edge
            for edge, value in rate.items()
            if frozen.get(edge, 0) + level * value == int(capacity[edge])
        }
        remaining = []
        for i in active:
            if saturated.isdisjoint(columns[i]):
                remaining.append(i)
                continue
            x[i] = level * alone[i]
            for edge, share in columns[i].items():
                frozen[edge] = frozen.get(edge, Fraction(0)) + x[i] * share
        active = remaining
    return x


def _live(child, alive) -> bool:
    if child.edge is not None:
        return alive[child.edge]
    return any(_live(c, alive) for c in child.children if c.share > 0)


def flatten(tree: ForwardingGroup, members: Mapping, alive: Mapping) -> list[Fraction]:
    """Each member's share of the router's traffic under the fixed root caps.

    ``members`` maps each declared leaf ``DirectedLink`` to its index; each
    root group re-flattens over its live members only, within its own cap.
    The caller refuses a positive root group with no live member.
    """
    out = [Fraction(0)] * len(members)
    total = sum(group.share for group in tree.groups)

    def visit(children, fraction):
        counted = [c for c in children if c.share > 0 and _live(c, alive)]
        denominator = sum(c.share for c in counted)
        for child in counted:
            share = fraction * child.share / denominator
            if child.edge is not None:
                out[members[child.edge]] += share
            else:
                visit(child.children, share)

    for group in tree.groups:
        if group.share > 0:
            visit(group.children, group.share / total)
    return out


@dataclass(frozen=True)
class ControllerSetup:
    """The controller declaration resolved on one prepared graph."""

    scope: str
    domain: frozenset[int]
    edge: frozenset[int]
    # By router: the tree's name, the tree and its leaves in declaration order.
    trees: Mapping[int, tuple[str, ForwardingGroup, tuple[DirectedLink, ...]]]

    def check_leaf(self, topology: PreparedTopology, endpoints: Endpoints, label):
        """Refuse a programmed demand the declared domain cannot place."""
        destinations = endpoints.destinations
        if len(destinations) != 1:
            raise ValueError(
                f"{label}: the WCMP controller needs one destination router, "
                f"got {list(destinations)}"
            )
        if topology.node_id_by_name[destinations[0]] not in self.edge:
            raise ValueError(
                f"{label}: destination {destinations[0]} is not in routing.bgp_edge"
            )
        outside = [
            name
            for name in endpoints.sources
            if topology.node_id_by_name[name] not in self.domain | self.edge
        ]
        if outside:
            raise ValueError(
                f"{label}: sources {outside} are in neither routing.igp_domain "
                "nor routing.bgp_edge"
            )

    def tables(self, topology, set_name, consumers):
        """One table and its report per destination of a demand set.

        ``consumers`` holds (endpoints, exact physical amount) per leaf.
        """
        by_destination: dict[str, list[tuple[tuple[int, ...], Fraction]]] = {}
        for endpoints, amount in consumers:
            by_destination.setdefault(endpoints.destinations[0], []).append(
                (tuple(topology.node_id_by_name[n] for n in endpoints.sources), amount)
            )
        tables, reports = [], []
        for name, leaves in sorted(by_destination.items()):
            table, members = destination_table(
                topology,
                self,
                set_name,
                topology.node_id_by_name[name],
                leaves,
                topology.disabled,
            )
            tables.append((name, replace(table, leaves=tuple(leaves))))
            reports.append(table_report(topology, table, members))
        return tuple(tables), tuple(reports)

    def leaf_config(
        self,
        topology: PreparedTopology,
        table: DestinationTable,
        endpoints,
        black_holes: ngc.Eligibility | None = None,
    ) -> ngc.FlowPolicyConfig:
        """One demand's native program on the shared table, with its own endpoints.

        A failure case's table forwards with the case's failures and the
        table's dropped members as black holes.
        """
        weighted = table.encoding == ngc.RouteAllocation.WEIGHTED
        program = ngc.ForwardingProgram.from_dag(
            topology.graph,
            [topology.node_id_by_name[name] for name in endpoints.sources],
            [topology.node_id_by_name[name] for name in endpoints.destinations],
            table.dag,
            allocation=ngc.RouteAllocation.WEIGHTED if weighted else None,
            weight_basis=ngc.WeightBasis.EXPLICIT if weighted else None,
            edge_weights=table.weights if weighted else None,
        )
        if black_holes is not None and table.holes is not None:
            black_holes = ngc.Eligibility.intersect(black_holes, table.holes)
        return ngc.FlowPolicyConfig(
            routing=ngc.Pinned(program, black_holes=black_holes),
            admission=PRESETS[FlowPolicyPreset.SHORTEST_PATHS_WCMP].admission,
        )

    def case_tables(self, topology, demands, mask, *, repair=False, context=""):
        """Each destination's table of a demand set in one failure case.

        Converged tables are built on the failed topology; a group repair
        table on the nominal routes that survive the mask. ``context`` names
        the case and state in a refusal.
        """
        return {
            name: destination_table(
                topology,
                self,
                demands.name,
                nominal.destination,
                nominal.leaves,
                mask,
                nominal=nominal if self.scope == "group" else None,
                repair=repair,
                context=context,
            )[0]
            for name, nominal in demands.controller_tables
        }

    def check_failure_states(self, topology, demands, states, label):
        """Refuse group converged and repair at a programmed router inside the domain."""
        if self.scope != "group" or not {"converged", "repair"} & set(states):
            return
        for _, table in demands.controller_tables:
            for router in table.programmed:
                if router in self.domain:
                    raise ValueError(
                        f"{label}: forwarding_groups.{self.trees[router][0]}: router "
                        f"{topology.node_names[router]} is inside routing.igp_domain; "
                        "converged and repair need programmed routers at the BGP edge"
                    )


def _population(topology, network, selector, label) -> frozenset[int]:
    names = {
        name
        for members in selected_groups(network, selector, label).values()
        for name in members
    }
    if not names:
        raise ValueError(f"{label}: empty selection")
    return frozenset(topology.node_id_by_name[name] for name in names)


def _check_share(share, label):
    if share < 0:
        raise ValueError(f"{label}.share: expected a nonnegative share, got {share}")


def _check_children(topology, router, children, label, positive, leaves):
    if not children:
        raise ValueError(f"{label}.children: expected at least one child")
    if positive and all(child.share == 0 for child in children):
        raise ValueError(
            f"{label}: a positive share at router {topology.node_names[router]} "
            "has only zero child shares"
        )
    sources = topology.graph.edge_sources()
    for j, child in enumerate(children):
        child_label = f"{label}.children[{j}]"
        _check_share(child.share, child_label)
        if (child.edge is None) == (child.children is None):
            raise ValueError(
                f"{child_label}: expected exactly one of edge and children"
            )
        if child.edge is None:
            _check_children(
                topology,
                router,
                child.children,
                child_label,
                positive and child.share > 0,
                leaves,
            )
            continue
        edge = edge_id(topology, child.edge, f"{child_label}.edge")
        if int(sources[edge]) != router:
            raise ValueError(
                f"{child_label}.edge: {child.edge.link} {child.edge.direction} "
                f"does not leave router {topology.node_names[router]}"
            )
        if child.edge in leaves:
            raise ValueError(
                f"{child_label}.edge: {child.edge.link} {child.edge.direction} "
                f"is also declared at {leaves[child.edge]}"
            )
        leaves[child.edge] = child_label


def _trees(topology, declared):
    """Every declared tree, checked in every scope, by router id."""
    trees: dict[int, tuple[str, ForwardingGroup, tuple[DirectedLink, ...]]] = {}
    for name, tree in declared.items():
        label = f"forwarding_groups.{name}"
        if tree.router not in topology.node_id_by_name:
            raise ValueError(f"{label}.router: unknown node {tree.router!r}")
        router = topology.node_id_by_name[tree.router]
        if router in trees:
            raise ValueError(
                f"{label}: router {tree.router} already has the tree "
                f"forwarding_groups.{trees[router][0]}"
            )
        if not tree.groups:
            raise ValueError(f"{label}.groups: expected at least one group")
        leaves: dict = {}
        for i, group in enumerate(tree.groups):
            group_label = f"{label}.groups[{i}]"
            _check_share(group.share, group_label)
            _check_children(
                topology, router, group.children, group_label, group.share > 0, leaves
            )
        if sum(group.share for group in tree.groups) == 0:
            raise ValueError(
                f"{label}: the root group shares of router {tree.router} sum to zero"
            )
        trees[router] = (name, tree, tuple(leaves))
    return MappingProxyType(trees)


def compile_setup(topology: PreparedTopology, scenario) -> ControllerSetup:
    """Resolve the domain populations and check every forwarding group once."""
    routing = scenario.routing
    network = scenario.network
    domain = _population(topology, network, routing.igp_domain, "routing.igp_domain")
    edge = _population(topology, network, routing.bgp_edge, "routing.bgp_edge")
    both = sorted(topology.node_names[n] for n in domain & edge)
    if both:
        raise ValueError(f"routing: nodes {both} are in both igp_domain and bgp_edge")
    trees = _trees(topology, scenario.forwarding_groups)
    return ControllerSetup(scenario.wcmp_controller.scope, domain, edge, trees)


def member_column(graph, rows, edge, t) -> tuple[dict[int, Fraction], Fraction]:
    """The load one unit entering ``edge`` puts on every edge, and what it carries alone.

    ``rows`` are the table's rows so far: finalized programmed rows, and every
    member at other routers. A unit that meets a zero-capacity edge, or stops
    at a router other than t with no member, carries nothing alone.
    """
    capacity = graph.edge_capacity_units()
    reached, held, load = propagate(
        graph,
        rows,
        {int(graph.edge_destinations()[edge]): Fraction(1)},
        reached_only=True,
    )
    column = {edge: Fraction(1), **load}
    if any(held[n] > 0 for n in reached if n != t and not rows.get(n)):
        return column, Fraction(0)
    return column, min(
        Fraction(int(capacity[e])) / share for e, share in column.items()
    )


def _heights(graph, members, t):
    """Longest hop distance to t over the DAG's members, in reverse topological order."""
    targets = graph.edge_destinations()
    parents: dict[int, list[int]] = {}
    for node, edges in members.items():
        for edge in edges:
            parents.setdefault(int(targets[edge]), []).append(node)
    waiting = {node: len(edges) for node, edges in members.items()}
    height, ready = {t: 0}, [t]
    while ready:
        child = ready.pop()
        for node in parents.get(child, ()):
            height[node] = max(height.get(node, 0), height[child] + 1)
            waiting[node] -= 1
            if waiting[node] == 0:
                ready.append(node)
    return height


def _group_shares(topology, setup, t, router, members, alone, nominal=None):
    """The router's members and their shares under the fixed root caps.

    With the ``nominal`` table (a failure case), a declared leaf that is no
    member is dead, and a root group with no live member keeps its nominally
    live leaves at their nominal shares within its cap; those members and the
    groups' caps are returned too.
    """
    if router not in setup.trees:
        raise ValueError(
            f"forwarding_groups: router {topology.node_names[router]} is programmed "
            f"toward {topology.node_names[t]} but declares no tree"
        )
    name, tree, declared = setup.trees[router]
    index = {topology.edge_refs[e]: i for i, e in enumerate(members)}
    missing = [ref for ref in index if ref not in declared]
    extra = [] if nominal else [ref for ref in declared if ref not in index]
    if missing or extra:
        raise ValueError(
            f"forwarding_groups.{name}: router {topology.node_names[router]} toward "
            f"{topology.node_names[t]}: members missing from the tree "
            f"{[f'{r.link} {r.direction}' for r in missing]}, leaves that are not "
            f"members {[f'{r.link} {r.direction}' for r in extra]}"
        )
    alive = dict.fromkeys(declared, False)
    alive.update(
        (topology.edge_refs[e], value > 0)
        for e, value in zip(members, alone, strict=True)
    )
    dead = [
        i
        for i, group in enumerate(tree.groups)
        if group.share > 0
        and not any(_live(c, alive) for c in group.children if c.share > 0)
    ]
    if nominal is not None and dead:
        total = sum(group.share for group in tree.groups)
        retained = []
        for i in dead:
            for ref in _leaves(tree.groups[i].children):
                edge = edge_id(topology, ref, f"forwarding_groups.{name}")
                alive[ref] = nominal.weights[edge] > 0
                if alive[ref]:
                    retained.append(edge)
        edges = sorted({*members, *retained})
        index = {topology.edge_refs[e]: i for i, e in enumerate(edges)}
        caps = tuple(
            DeadCap(
                topology.node_names[t],
                topology.node_names[router],
                name,
                i,
                tree.groups[i].share / total,
            )
            for i in dead
        )
        return edges, flatten(tree, index, alive), tuple(retained), caps
    if dead:
        # Lossless admission would stop at the first unit sent into the group.
        raise ValueError(
            f"forwarding_groups.{name}.groups[{dead[0]}]: no member can carry "
            f"traffic from router {topology.node_names[router]} toward "
            f"{topology.node_names[t]}"
        )
    return members, flatten(tree, index, alive), (), ()


def _leaves(children):
    for child in children:
        if child.edge is not None:
            yield child.edge
        else:
            yield from _leaves(child.children)


def destination_table(
    topology,
    setup,
    set_name,
    t,
    leaves,
    mask,
    *,
    nominal: DestinationTable | None = None,
    repair=False,
    context="",
) -> tuple[DestinationTable, dict[int, list[int]]]:
    """The one table toward t and its members by router, from the leaves' (sources, exact amount).

    ``next_hop`` and ``group`` program the sources of positive leaves,
    downstream first; ``all_routers`` programs every router from one flow.
    A failure case's group table passes its ``nominal`` table: dead root
    groups keep their caps (`_group_shares`), and with ``repair`` the routes
    are the nominal ones that survive the mask instead of a new search.
    """
    graph = topology.graph
    sources = graph.edge_sources()
    capacity = graph.edge_capacity_units()
    if repair:
        assert nominal is not None
        dag = surviving_dag(graph, nominal.dag, mask, t)
    else:
        dag = domain_dag(topology, setup.domain, setup.edge, t, mask)
    members: dict[int, list[int]] = {}
    for edge in sorted(int(e) for e in dag.via_edges()):
        members.setdefault(int(sources[edge]), []).append(edge)
    rows = {node: [(e, 1) for e in edges] for node, edges in members.items()}
    weights = [0] * graph.num_edges()
    for edges in members.values():
        for edge in edges:
            weights[edge] = 1
    if setup.scope == "all_routers":
        table = _all_routers(topology, set_name, t, dag, members, rows, weights, leaves)
        return table, members
    programmed = {s for sources, amount in leaves if amount > 0 for s in sources}
    heights = _heights(graph, members, t)
    order = sorted(
        (r for r in programmed if r in members), key=lambda r: (heights[r], r)
    )
    approximations, dropped, caps = [], [], []
    for router in order:
        columns, alone = [], []
        for edge in members[router]:
            column, value = member_column(graph, rows, edge, t)
            columns.append(column)
            alone.append(value)
        if setup.scope == "next_hop":
            shares = fill(columns, alone, capacity)
        else:
            members[router], shares, retained, dead = _group_shares(
                topology, setup, t, router, members[router], alone, nominal
            )
            dropped.extend(retained)
            caps.extend(dead)
        row, error = integer_weights(shares)
        if error is not None:
            approximations.append(
                WeightApproximation(
                    f"controller.{set_name}.{topology.node_names[t]}"
                    f".router.{topology.node_names[router]}",
                    error,
                )
            )
        for edge, weight in zip(members[router], row, strict=True):
            weights[edge] = weight
        rows[router] = [
            (e, w) for e, w in zip(members[router], row, strict=True) if w > 0
        ]
    holes = None
    if dropped:
        assert nominal is not None
        dag = _continue(graph, nominal, dag, dropped, members, rows, weights, t)
        holes = graph.eligibility(excluded_edges=dropped)
    encoding = encode(topology, members, set(order), rows, weights)
    table = DestinationTable(
        t,
        dag,
        tuple(weights),
        encoding,
        tuple(order),
        tuple(approximations),
        dropped=tuple(sorted(dropped)),
        dead_caps=tuple(caps),
        holes=holes,
    )
    if nominal is not None:
        _check_encoding(topology, setup, table, members, context)
    return table, members


def surviving_dag(graph, dag, mask, t) -> ngc.PredecessorDAG:
    """The DAG's edges the mask keeps that still lead to t (native repair's pruning)."""
    allowed, targets = mask.edge_allowed(), graph.edge_destinations()
    kept = [int(e) for e in dag.via_edges() if allowed[int(e)]]
    parents: dict[int, list[int]] = {}
    for edge in kept:
        parents.setdefault(int(targets[edge]), []).append(edge)
    sources = graph.edge_sources()
    reach, pending = {t}, [t]
    while pending:
        for edge in parents.get(pending.pop(), ()):
            if int(sources[edge]) not in reach:
                reach.add(int(sources[edge]))
                pending.append(int(sources[edge]))
    return dag_from_edges(graph, [e for e in kept if int(targets[e]) in reach])


def _continue(graph, nominal, dag, dropped, members, rows, weights, t):
    """Lead each dropped member to t: nominal rows at routers with no row of their own.

    The members' traffic is dropped on them; the walk keeps them in the
    program. A router with rows keeps them, so live traffic is unchanged.
    """
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    nominal_rows: dict[int, list[int]] = {}
    for edge in sorted(int(e) for e in nominal.dag.via_edges()):
        nominal_rows.setdefault(int(sources[edge]), []).append(edge)
    edges = {int(e) for e in dag.via_edges()} | set(dropped)
    pending = [int(targets[e]) for e in dropped]
    while pending:
        node = pending.pop()
        if node == t or node in members:
            continue
        members[node] = nominal_rows.get(node, [])
        rows[node] = [(e, nominal.weights[e]) for e in members[node]]
        for edge in members[node]:
            weights[edge] = nominal.weights[edge]
            edges.add(edge)
            pending.append(int(targets[edge]))
    return dag_from_edges(graph, edges)


def _check_encoding(topology, setup, table, members, context):
    """Refuse a failure table whose native program splits differently from its rows.

    The reference is each programmed router's finalized integer row, a
    dropped member delivering nothing; native preparation's pruning of the
    encoded program must leave every member's delivered fraction unchanged.
    Live members carry something alone, so only a dead group's member can
    make them differ.
    """
    graph, t = topology.graph, table.destination
    targets = graph.edge_destinations()
    edges = [int(e) for e in table.dag.via_edges()]
    native = effective_rows(topology, edges, [t], table.encoding, table.weights)
    dropped = set(table.dropped)
    for router in table.programmed:
        total = sum(table.weights[e] for e in members[router])
        effective = dict(native.get(router, ()))
        for edge in members[router]:
            reference = 0 if edge in dropped else Fraction(table.weights[edge], total)
            encoded = Fraction(0)
            if edge in effective and edge not in dropped:
                start = {int(targets[edge]): 1}
                _, held, _ = propagate(graph, native, start, reached_only=True)
                encoded = held[t] * effective[edge] / sum(effective.values())
            if encoded != reference:
                # Name the dead group whose retained member native pruning removed.
                name, (_, tree, _) = topology.node_names[router], setup.trees[router]
                pruned = {
                    topology.edge_refs[e]
                    for e in members[router]
                    if e in dropped and e not in effective
                }
                dead = [c.group for c in table.dead_caps if c.router == name]
                group = next(
                    (g for g in dead if pruned & set(_leaves(tree.groups[g].children))),
                    dead[0],
                )
                raise ValueError(
                    f"forwarding_groups.{setup.trees[router][0]}.groups[{group}]: "
                    f"{context}: toward {topology.node_names[t]}, router {name} "
                    "forwards this dead group's share differently from its fixed cap"
                )


def _reached(graph, start, out) -> set[int]:
    """The routers reached from ``start`` along the edges ``out`` gives each router."""
    targets = graph.edge_destinations()
    reached, pending = set(start), list(start)
    while pending:
        for edge in out(pending.pop()):
            head = int(targets[edge])
            if head not in reached:
                reached.add(head)
                pending.append(head)
    return reached


def _all_routers(
    topology, set_name, t, dag, members, rows, weights, leaves
) -> DestinationTable:
    """Every router on the sources' walks, from one native flow in demand proportions.

    Each source weighs its leaves' exact nominal amounts, a multi-source
    leaf divided over its sources that reach t; the native weighted solve
    over the DAG apportions whole units by those weights, and its edge flows
    are the table. Native endpoints are the leaves' own sources. Source
    weights that reach 2^62 are apportioned like router weights; the entry
    names the source with the largest relative error, earlier source on ties.
    """
    graph = topology.graph
    nominal: dict[int, Fraction] = {
        s: Fraction(0) for sources, _ in leaves for s in sources
    }
    for sources, amount in leaves:
        roster = [s for s in sources if s in members]
        for source in roster:
            nominal[source] += amount / len(roster)
    order = sorted(nominal)
    held, errors = apportioned([nominal[s] for s in order])
    approximations = []
    if errors:
        worst = max(errors, key=lambda i: (errors[i], -i))
        approximations.append(
            WeightApproximation(
                f"controller.{set_name}.{topology.node_names[t]}"
                f".source.{topology.node_names[order[worst]]}",
                errors[worst],
            )
        )
    vector = [0] * graph.num_nodes()
    for source, weight in zip(order, held, strict=True):
        vector[source] = weight
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.WEIGHTED,
            source_weights=vector,
            support=dag,
        )
    )
    try:
        result = ngc.evaluate_demand(
            graph,
            order,
            [t],
            ngc.EvaluationOptions(config, outputs=ngc.OutputOptions(edge_flows=True)),
        )
    except (ValueError, TypeError) as exc:
        raise type(exc)(f"controller.{topology.node_names[t]}: {exc}") from exc
    flows = result.edge_flows
    assert flows is not None
    reached = _reached(graph, order, lambda router: members.get(router, ()))
    programmed = sorted(r for r in reached if r in members)
    for router in programmed:
        for edge in members[router]:
            weights[edge] = int(flows[edge])
        rows[router] = [(e, weights[e]) for e in members[router] if weights[e] > 0]
    encoding = encode(topology, members, set(programmed), rows, weights)
    return DestinationTable(
        t,
        dag,
        tuple(weights),
        encoding,
        tuple(programmed),
        tuple(approximations),
        tuple(
            (source, nominal[source], weight)
            for source, weight in zip(order, held, strict=True)
        ),
    )


def encode(topology, members, programmed, rows, weights) -> ngc.RouteAllocation:
    """EQUAL when every programmed row that receives traffic is equal and positive.

    Otherwise WEIGHTED, which prunes zero-capacity members and dead branches.
    Zero-alone members carry weight 0 and a root group with no live member is
    refused, so no router that receives traffic keeps a member WEIGHTED prunes.
    """
    graph = topology.graph
    capacity = graph.edge_capacity_units()
    reached = _reached(
        graph,
        programmed,
        lambda router: (e for e, _ in rows.get(router, ()) if capacity[e] > 0),
    )
    if all(
        len({weights[e] for e in members[r]}) == 1 and weights[members[r][0]] > 0
        for r in reached
        if r in programmed and r in members
    ):
        return ngc.RouteAllocation.EQUAL
    return ngc.RouteAllocation.WEIGHTED


def table_report(
    topology: PreparedTopology, table: DestinationTable, members
) -> TableReport:
    """The table by name; ``members`` are its DAG's members by router."""
    return TableReport(
        topology.node_names[table.destination],
        tuple(
            ProgrammedRouter(
                topology.node_names[router],
                tuple(
                    MemberWeight(
                        cast(DirectedLink, topology.edge_refs[e]), table.weights[e]
                    )
                    for e in members[router]
                ),
            )
            for router in sorted(table.programmed)
        ),
        None
        if table.source_weights is None
        else tuple(
            SourceWeight(topology.node_names[source], nominal, weight)
            for source, nominal, weight in table.source_weights
        ),
    )
