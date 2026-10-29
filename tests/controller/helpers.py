"""Small controller scenarios and oracles that share no code with the controller.

The oracles recompute what the controller and native forwarding must give,
from the stated rules alone: fluid columns by recursion, progressive filling
event by event over dense loads, and integer no-drop forwarding by highest
averages.
"""

from __future__ import annotations

from fractions import Fraction

import netgraph_core as ngc

from ngraph import (
    ControllerGroup,
    DemandSet,
    DemandSpec,
    DirectedLink,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    Link,
    Network,
    Node,
    PlacementQuery,
    RoutingDomain,
    Scenario,
    Selector,
    UnitsSettings,
    WCMPController,
    place,
    prepare,
)

WCMP = FlowPolicyPreset.SHORTEST_PATHS_WCMP


def network(links, disabled_links=(), disabled_nodes=()):
    """Physical links (source, target, capacity[, cost]) with their default ids."""
    names = sorted({u for u, v, *_ in links} | {v for u, v, *_ in links})
    net = Network(nodes={n: Node(n, disabled=n in disabled_nodes) for n in names})
    for u, v, capacity, *cost in links:
        net.add_link(Link(u, v, capacity, cost[0] if cost else 1))
    for link in disabled_links:
        net.disable_link(link)
    return net


def demand(source, target, volume, policy=WCMP, **fields):
    return DemandSpec(Selector(source), Selector(target), volume, policy, **fields)


def scenario(
    links,
    domain,
    edge,
    demands,
    *,
    scope="next_hop",
    trees=None,
    q=1,
    disabled_links=(),
    disabled_nodes=(),
    sets=None,
    precision=0.001,
):
    """A controller scenario; ``demands`` is the set ``d`` unless ``sets`` names more."""
    named = {"d": DemandSet("d", tuple(demands))}
    for name, values in (sets or {}).items():
        named[name] = DemandSet(name, tuple(values))
    return Scenario(
        network(links, disabled_links, disabled_nodes),
        demand_sets=named,
        units=UnitsSettings(q, precision=precision),
        routing=RoutingDomain(Selector(domain), Selector(edge)),
        wcmp_controller=WCMPController(scope),
        forwarding_groups=trees or {},
    )


def prepared(*args, **kwargs):
    value = scenario(*args, **kwargs)
    return prepare(value, demand_sets=tuple(value.demand_sets))


def edge(link, direction="forward"):
    return DirectedLink(link, direction)


def tree(router, *groups):
    """A tree from groups given as (share, [(share, link) | (share, [children])])."""

    def child(item):
        share, value = item
        if isinstance(value, str):
            return GroupChild(share, edge(value))
        return GroupChild(share, children=tuple(child(c) for c in value))

    return ForwardingGroup(
        router,
        tuple(
            ControllerGroup(tuple(child(c) for c in children), share)
            for share, children in groups
        ),
    )


def table(prep, destination, set_name="d"):
    return prep.demand_sets[set_name].controller_table(destination)


def dag_edges(prep, destination, set_name="d"):
    """The table's DAG as sorted 'source->target' names, one entry per edge."""
    topology = prep.topology
    graph = topology.graph
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    return sorted(
        f"{topology.node_names[int(sources[e])]}->{topology.node_names[int(targets[e])]}"
        for e in table(prep, destination, set_name).dag.via_edges()
    )


def row(prep, destination, router, set_name="d"):
    """A router's reported members: [(link, direction, weight)]."""
    for programmed in prep.demand_sets[set_name].controller:
        if programmed.destination != destination:
            continue
        for item in programmed.programmed:
            if item.router == router:
                return [(m.edge.link, m.edge.direction, m.weight) for m in item.members]
    return None


def delivered(prep, set_name="d", alpha=1.0, outputs=None):
    """Delivered units of each placed demand, by id."""
    query = PlacementQuery(
        prep.demand_sets[set_name],
        alpha=alpha,
        workers=1,
        **({} if outputs is None else {"outputs": outputs}),
    )
    analysis = place(prep, query)
    rows = analysis.cases[0].states["converged"].rows
    return {row.id: row.result.delivered for row in rows}, analysis


# ---- oracles ----


def fluid_column(rows, heads, capacity, start_edge, t):
    """A unit entering ``start_edge``: the load on every edge, by recursion.

    ``rows`` maps a router to its (EdgeId, weight) members (unprogrammed
    routers: weight 1 on every member); ``heads`` gives each edge's head.
    Returns (column, alone); alone is 0 when the unit meets a zero-capacity
    edge or stops at a router other than t without a positive member.
    """
    column = {start_edge: Fraction(1)}
    stuck = []

    def push(node, amount):
        if node == t:
            return
        out = [(e, w) for e, w in rows.get(node, ()) if w > 0]
        if not out:
            stuck.append(node)
            return
        total = sum(w for _, w in out)
        for e, w in out:
            share = amount * Fraction(w, total)
            column[e] = column.get(e, Fraction(0)) + share
            push(heads[e], share)

    push(heads[start_edge], Fraction(1))
    if stuck or any(capacity[e] == 0 for e in column):
        return column, Fraction(0)
    return column, min(Fraction(capacity[e]) / a for e, a in column.items())


def filling_oracle(columns, capacity):
    """Progressive filling, one event at a time, loads recomputed from scratch."""
    n = len(columns)
    alone = []
    for column in columns:
        if any(capacity[e] == 0 for e in column):
            alone.append(Fraction(0))
        else:
            alone.append(min(Fraction(capacity[e]) / a for e, a in column.items()))
    x = [Fraction(0)] * n
    frozen = [a == 0 for a in alone]
    level = Fraction(0)
    while not all(frozen):
        # The next level at which some edge used by an unfrozen member fills.
        candidates = []
        for e in capacity:
            fixed = sum(x[i] * columns[i].get(e, 0) for i in range(n) if frozen[i])
            moving = sum(
                alone[i] * columns[i].get(e, 0) for i in range(n) if not frozen[i]
            )
            if moving > 0:
                candidates.append((Fraction(capacity[e]) - fixed) / moving)
        level = min(candidates)
        for i in range(n):
            if not frozen[i]:
                x[i] = level * alone[i]
        full = [
            e
            for e in capacity
            if sum(x[i] * columns[i].get(e, 0) for i in range(n)) == capacity[e]
        ]
        for i in range(n):
            if not frozen[i] and any(columns[i].get(e, 0) > 0 for e in full):
                frozen[i] = True
    return x


def highest_averages(x, weights):
    """Highest averages, starting at guaranteed lower quotas, with earlier ties."""
    total = sum(weights)
    if not total:
        return [0] * len(weights)
    # The final divisor is at most total/x, so every floor(x*w/total)
    # seat is guaranteed. Only fewer than len(weights) seats remain to rank.
    a = [x * w // total for w in weights]
    for _ in range(x - sum(a)):
        best = None
        for i, w in enumerate(weights):
            if w and (best is None or w * (a[best] + 1) > weights[best] * (a[i] + 1)):
                best = i
        a[best] += 1
    return a


def lossless_oracle(edges, capacity, source, t, weights=None):
    """The largest no-drop total of one source over a DAG, by integer forwarding.

    ``edges`` are (EdgeId, tail, head) in EdgeId order. ``weights`` None means
    equal splitting over every member (zero-capacity ones included); weights
    given mean weighted splitting after pruning zero-capacity members and
    dead branches, as native WCMP prepares a table.
    """
    members: dict[int, list[int]] = {}
    head = {e: v for e, _, v in edges}
    for e, u, _ in edges:
        members.setdefault(u, []).append(e)
    if weights is not None:
        live = {t}
        changed = True
        while changed:
            changed = False
            for u, out in members.items():
                if u not in live and any(
                    capacity[e] > 0 and weights[e] > 0 and head[e] in live for e in out
                ):
                    live.add(u)
                    changed = True
        effective = {
            u: [
                (e, weights[e])
                for e in out
                if capacity[e] > 0 and weights[e] > 0 and head[e] in live
            ]
            for u, out in members.items()
        }
    else:
        effective = {u: [(e, 1) for e in out] for u, out in members.items()}
    order = []
    seen = set()

    def visit(u):
        if u in seen:
            return
        seen.add(u)
        for e, _ in effective.get(u, ()):
            visit(head[e])
        order.append(u)

    visit(source)
    order.reverse()

    def fits(x):
        held = {source: x}
        for u in order:
            amount = held.get(u, 0)
            if u == t or not amount:
                continue
            out = effective.get(u, [])
            if not out:
                return False
            split = highest_averages(amount, [w for _, w in out])
            for (e, _), units in zip(out, split, strict=True):
                if units > capacity[e]:
                    return False
                held[head[e]] = held.get(head[e], 0) + units
        return True

    lo, hi = 0, sum(capacity.values())
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if fits(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def native_graph(edges, q=1.0):
    """A raw native graph of directed (tail, head, capacity) edges."""
    return ngc.Graph(
        1 + max(max(u, v) for u, v, _ in edges),
        [u for u, _, _ in edges],
        [v for _, v, _ in edges],
        [c for _, _, c in edges],
        [1] * len(edges),
        q,
    )
