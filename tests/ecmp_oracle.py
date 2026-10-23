"""Independent integer ECMP admission on a physical network, for integration checks.

This test oracle builds its own graph from input links, computes shortest distances
with NetworkX, and propagates integer equal shares in decreasing distance order.
It imports no NetGraph analysis or numerical helper.
"""

from fractions import Fraction

import networkx as nx


def _units(value, q):
    exact = Fraction(float(value)) / Fraction(q)
    return (2 * exact.numerator + exact.denominator) // (2 * exact.denominator)


def physical_edges(network, q, excluded_nodes=(), excluded_links=()):
    disabled = set(excluded_nodes) | {
        name for name, node in network.nodes.items() if node.disabled
    }
    failed_links = set(excluded_links)
    edges = []
    # The source-grouped stable input order defines the native member order.
    for identity, link in sorted(network.links.items()):
        for source, target in ((link.source, link.target), (link.target, link.source)):
            if (
                not link.disabled
                and identity not in failed_links
                and source not in disabled
                and target not in disabled
            ):
                edges.append((source, target, _units(link.capacity, q), int(link.cost)))
    return sorted(edges, key=lambda edge: edge[0]), disabled


def equal_shortest_capacity(
    network, sources, targets, q, excluded_nodes=(), excluded_links=()
):
    edges, disabled = physical_edges(network, q, excluded_nodes, excluded_links)
    targets = set(targets) - disabled
    graph = nx.DiGraph()
    graph.add_nodes_from(set(network.nodes) - disabled)
    for source, target, _, cost in edges:
        if not graph.has_edge(source, target) or cost < graph[source][target]["weight"]:
            graph.add_edge(source, target, weight=cost)
    if not targets:
        return 0
    distances = nx.multi_source_dijkstra_path_length(
        graph.reverse(), sorted(targets), weight="weight"
    )
    roster = sorted((set(sources) - disabled) & distances.keys())
    if not roster:
        return 0
    successors = {name: [] for name in distances}
    for index, (source, target, _, cost) in enumerate(edges):
        if (
            source in distances
            and target in distances
            and distances[source] == cost + distances[target]
        ):
            successors[source].append(index)
    order = sorted(distances, key=lambda name: (-distances[name], name))

    def feasible(amount):
        arrivals = dict.fromkeys(distances, 0)
        for index, source in enumerate(roster):
            arrivals[source] += amount // len(roster) + (index < amount % len(roster))
        delivered = 0
        for node in order:
            incoming = arrivals[node]
            if node in targets:
                delivered += incoming
                continue
            members = successors[node]
            if not members:
                if incoming:
                    return False
                continue
            for ordinal, edge_index in enumerate(members):
                share = incoming // len(members) + (ordinal < incoming % len(members))
                _, target, capacity, _ = edges[edge_index]
                if share > capacity:
                    return False
                arrivals[target] += share
        return delivered == amount

    source_set = set(roster)
    upper = sum(
        capacity
        for source, target, capacity, _ in edges
        if source in source_set and target not in source_set
    )
    low, high = 0, upper + 1
    while low + 1 < high:
        middle = (low + high) // 2
        if feasible(middle):
            low = middle
        else:
            high = middle
    assert feasible(low) and not feasible(low + 1)
    return low


def ideal_capacity(network, sources, targets, q, excluded_nodes=(), excluded_links=()):
    edges, disabled = physical_edges(network, q, excluded_nodes, excluded_links)
    source_set, target_set = set(sources) - disabled, set(targets) - disabled
    if not source_set or not target_set:
        return 0
    graph = nx.DiGraph()
    graph.add_nodes_from(set(network.nodes) - disabled)
    for source, target, capacity, _ in edges:
        prior = graph.get_edge_data(source, target, {}).get("capacity", 0)
        graph.add_edge(source, target, capacity=prior + capacity)
    bound = sum(capacity for _, _, capacity, _ in edges)
    source_root, target_root = object(), object()
    for source in source_set:
        graph.add_edge(source_root, source, capacity=bound)
    for target in target_set:
        graph.add_edge(target, target_root, capacity=bound)
    maximum = nx.maximum_flow_value(graph, source_root, target_root)
    cut_value, (left, right) = nx.minimum_cut(graph, source_root, target_root)
    assert source_root in left and target_root in right
    assert (
        maximum
        == cut_value
        == sum(
            data["capacity"]
            for source, target, data in graph.edges(data=True)
            if source in left and target in right
        )
    )
    return maximum
