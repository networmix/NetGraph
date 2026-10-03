"""edge_priority reaches both placement engines and keys the DAG cache."""

from __future__ import annotations

import pytest

from ngraph.analysis.functions import demand_placement_analysis
from ngraph.model.network import Link, Network, Node


def _two_path_network() -> Network:
    # A -> B -> D (capacity 100/100) and A -> C -> D (capacity 20/20), equal cost.
    net = Network()
    for name in "ABCD":
        net.add_node(Node(name))
    net.add_link(Link("A", "B", capacity=100.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=100.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=20.0, cost=1.0))
    net.add_link(Link("C", "D", capacity=20.0, cost=1.0))
    return net


@pytest.mark.parametrize(
    "preset", ["SHORTEST_PATHS_ECMP", "SHORTEST_PATHS_WCMP", "TE_WCMP_UNLIM"]
)
@pytest.mark.parametrize("edge_priority", [None, "residual", "capacity", "headroom"])
def test_every_priority_places_through_every_engine(preset, edge_priority):
    net = _two_path_network()
    demands = [
        {
            "source": "^A$",
            "target": "^D$",
            "mode": "pairwise",
            "volume": 30.0,
            "flow_policy": preset,
            "edge_priority": edge_priority,
        }
    ]
    result = demand_placement_analysis(net, set(), set(), demands)
    # Both paths are usable, so a WCMP/TE policy carries the full volume and an
    # ECMP policy is limited by the smaller member (2 x 20).
    expected = 30.0 if preset != "SHORTEST_PATHS_ECMP" else 30.0
    assert result.summary.total_placed == pytest.approx(expected)


def _path_nodes(net: Network, entry) -> set[str]:
    """Node names touched by the links an entry reports in data["edges"]."""
    nodes: set[str] = set()
    for key in entry.data.get("edges", ()):
        link = net.links[key.rsplit(":", 1)[0]]
        nodes.update((link.source, link.target))
    return nodes


def test_single_lsp_disagrees_between_residual_and_headroom():
    # A-B-D is 100/100 loaded to 15 left (headroom 0.15); A-C-D is 10/10 free
    # (headroom 1.0). A single-LSP TE demand of 5 fits either: residual priority
    # prefers the 15 of A-B-D, headroom priority prefers the fully free A-C-D.
    net = Network()
    for name in "ABCD":
        net.add_node(Node(name))
    net.add_link(Link("A", "B", capacity=100.0, cost=1.0))
    net.add_link(Link("B", "D", capacity=100.0, cost=1.0))
    net.add_link(Link("A", "C", capacity=10.0, cost=1.0))
    net.add_link(Link("C", "D", capacity=10.0, cost=1.0))
    base = {"source": "^A$", "target": "^D$", "mode": "pairwise"}
    loader = {
        **base,
        "priority": 0,
        "volume": 85.0,
        "flow_policy": "TE_WCMP_UNLIM",
        "static_paths": [{"nodes": ["A", "B", "D"]}],
    }
    chooser = {
        **base,
        "priority": 1,
        "volume": 5.0,
        "flow_policy": "TE_ECMP_UP_TO_256_LSP",
    }
    outcomes = {}
    for priority in ("residual", "headroom"):
        result = demand_placement_analysis(
            net,
            set(),
            set(),
            [loader, {**chooser, "edge_priority": priority}],
            include_flow_details=True,
            include_used_edges=True,
        )
        assert result.summary.total_placed == pytest.approx(90.0)
        (second,) = [f for f in result.flows if f.priority == 1]
        assert second.placed == pytest.approx(5.0)
        outcomes[priority] = _path_nodes(net, second)
    assert "B" in outcomes["residual"] and "C" not in outcomes["residual"]
    assert "C" in outcomes["headroom"] and "B" not in outcomes["headroom"]
