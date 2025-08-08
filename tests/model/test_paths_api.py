from __future__ import annotations

import math

from ngraph.model.network import Link, Network, Node
from ngraph.model.view import NetworkView


def _build_triangle_network() -> Network:
    net = Network()
    net.add_node(Node("S"))
    net.add_node(Node("X"))
    net.add_node(Node("T"))
    net.add_link(Link("S", "X", capacity=10.0, cost=1.0))
    net.add_link(Link("X", "T", capacity=10.0, cost=1.0))
    net.add_link(Link("S", "T", capacity=10.0, cost=5.0))
    return net


def test_network_shortest_path_costs_and_paths_basic() -> None:
    net = _build_triangle_network()

    costs = net.shortest_path_costs("^S$", "^T$")
    assert costs[("^S$", "^T$")] == 2.0

    res = net.shortest_paths("^S$", "^T$")
    paths = res[("^S$", "^T$")]
    assert paths
    # Best path must be S->X->T with cost 2.0
    assert any(
        p.nodes_seq == ("S", "X", "T") and math.isclose(p.cost, 2.0) for p in paths
    )


def test_network_k_shortest_paths_factor_limits_worse_routes() -> None:
    net = Network()
    for n in ["S", "A", "B", "C", "T"]:
        net.add_node(Node(n))
    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))  # cost 2
    net.add_link(Link("S", "B", capacity=10.0, cost=1.0))
    net.add_link(Link("B", "T", capacity=10.0, cost=1.0))  # cost 2
    net.add_link(Link("S", "C", capacity=10.0, cost=2.0))
    net.add_link(Link("C", "T", capacity=10.0, cost=2.0))  # cost 4

    res = net.k_shortest_paths("^S$", "^T$", max_k=5, max_path_cost_factor=1.0)
    paths = res[("^S$", "^T$")]
    assert len(paths) <= 2
    assert all(math.isclose(p.cost, 2.0) for p in paths)
    assert all("C" not in p.nodes_seq for p in paths)


def test_network_split_parallel_edges_enumeration() -> None:
    net = Network()
    for n in ["S", "A", "T"]:
        net.add_node(Node(n))
    # Add two parallel edges per hop with equal cost
    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("S", "A", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))
    net.add_link(Link("A", "T", capacity=10.0, cost=1.0))

    no_split = net.shortest_paths("^S$", "^T$", split_parallel_edges=False)
    assert len(no_split[("^S$", "^T$")]) == 1

    split = net.shortest_paths("^S$", "^T$", split_parallel_edges=True)
    assert len(split[("^S$", "^T$")]) == 4


def test_network_pairwise_labels_mapping() -> None:
    net = Network()
    for n in ["S1", "S2", "T1", "T2"]:
        net.add_node(Node(n))
    net.add_link(Link("S1", "T1", capacity=10.0, cost=3.0))
    net.add_link(Link("S2", "T1", capacity=10.0, cost=1.0))
    # T2 unreachable

    res_costs = net.shortest_path_costs("S(1|2)", "T(1|2)", mode="pairwise")
    assert res_costs[("1", "1")] == 3.0
    assert res_costs[("2", "1")] == 1.0
    assert math.isinf(res_costs[("1", "2")])
    assert math.isinf(res_costs[("2", "2")])


def test_view_respects_exclusions_and_disabled_nodes() -> None:
    net = _build_triangle_network()
    # Exclude the middle node; no path should remain
    view = NetworkView.from_excluded_sets(net, excluded_nodes=["X"])
    costs = view.shortest_path_costs("^S$", "^T$")
    # Path via X is blocked; direct S->T remains with cost 5
    assert math.isclose(costs[("^S$", "^T$")], 5.0, rel_tol=1e-9)
    sp = view.shortest_paths("^S$", "^T$")[("^S$", "^T$")]
    assert sp and all(p.nodes_seq == ("S", "T") for p in sp)

    # Disable T; also no paths
    net.nodes["T"].disabled = True
    costs2 = net.shortest_path_costs("^S$", "^T$")
    assert math.isinf(costs2[("^S$", "^T$")])
