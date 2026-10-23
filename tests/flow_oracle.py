"""Independent finite-flow enumeration for the three-node nonuniform-cost witness."""

from itertools import product

# Explicitly independent of production's edge expansion or selection helpers.
EDGES = (
    ("a|b|0", "forward", "a", "b", 2, 1),
    ("a|b|0", "reverse", "b", "a", 2, 1),
    ("b|t|0", "forward", "b", "t", 2, 2),
    ("b|t|0", "reverse", "t", "b", 2, 2),
    ("a|t|0", "forward", "a", "t", 3, 5),
    ("a|t|0", "reverse", "t", "a", 3, 5),
)


def enumerate_optimum(
    request,
    residual,
    excluded_nodes,
    excluded_links,
    shortest_only,
    excluded_edge_indices=(),
):
    allowed = [
        source not in excluded_nodes
        and target not in excluded_nodes
        and link not in excluded_links
        and index not in excluded_edge_indices
        for index, (link, _, source, target, _, _) in enumerate(EDGES)
    ]
    # Derive the static shortest support on this mask, without residual filtering.
    if shortest_only:
        cheap = allowed[0] and allowed[2]
        support = {0, 2} if cheap else {4} if allowed[4] else set()
        allowed = [valid and index in support for index, valid in enumerate(allowed)]
    best = None
    for vector in product(
        *(
            range(residual[index] + 1) if valid else (0,)
            for index, valid in enumerate(allowed)
        )
    ):
        balance = {name: 0 for name in ("a", "b", "t")}
        cost = 0
        for flow, (_, _, source, target, _, unit_cost) in zip(
            vector, EDGES, strict=True
        ):
            balance[source] -= flow
            balance[target] += flow
            cost += flow * unit_cost
        value = balance["t"]
        if balance["b"] or balance["a"] != -value or not 0 <= value <= request:
            continue
        rank = (-value, cost, vector)
        if best is None or rank < best:
            best = rank
    return -best[0], best[1], best[2]


def closest_source_cut(
    vector, excluded_nodes=(), excluded_links=(), excluded_edge_indices=()
):
    adjacency = {name: set() for name in ("a", "b", "t")}
    allowed = []
    for index, (link, _, source, target, capacity, _) in enumerate(EDGES):
        valid = (
            source not in excluded_nodes
            and target not in excluded_nodes
            and link not in excluded_links
            and index not in excluded_edge_indices
        )
        allowed.append(valid)
        if valid:
            if vector[index] < capacity:
                adjacency[source].add(target)
            if vector[index]:
                adjacency[target].add(source)
    reachable = set() if "a" in excluded_nodes else {"a"}
    pending = list(reachable)
    while pending:
        for node in adjacency[pending.pop()]:
            if node not in reachable:
                reachable.add(node)
                pending.append(node)
    return {
        (link, direction)
        for valid, (link, direction, source, target, _, _) in zip(
            allowed, EDGES, strict=True
        )
        if valid and source in reachable and target not in reachable
    }
