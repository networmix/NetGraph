"""Labels, finite ranges and ownership independently of native input positions."""

from dataclasses import FrozenInstanceError

import pytest

from ngraph import Link, Network, Node
from ngraph.analysis.topology import compile_topology, eligibility
from ngraph.model.network import DirectedLink
from ngraph.results import SyntheticIngress


def sample():
    n = Network()
    for name in ("z", "a", "m"):
        n.add_node(Node(name, attrs={"nested": {"v": 1}}))
    n.add_link(Link("z", "a", 4, 5))
    n.add_link(Link("a", "m", 2, 1))
    n.add_link(Link("a", "m", 3, 2))
    return n


def test_sorted_nodes_outgoing_edge_identity_reverse_parallel_and_ownership():
    n = sample()
    topology = compile_topology(n, 1)
    assert topology.node_names == ("a", "m", "z")
    expected = {}
    for link in n.links.values():
        expected[DirectedLink(link.id, "forward")] = (
            link.source,
            link.target,
            link.capacity,
            link.cost,
        )
        expected[DirectedLink(link.id, "reverse")] = (
            link.target,
            link.source,
            link.capacity,
            link.cost,
        )
    graph = topology.graph
    for i, ref in enumerate(topology.edge_refs):
        s, t, cap, cost = expected[ref]
        assert int(graph.edge_sources()[i]) == topology.node_id_by_name[s]
        assert int(graph.edge_destinations()[i]) == topology.node_id_by_name[t]
        assert int(graph.edge_capacity_units()[i]) == cap
        assert int(graph.edge_costs()[i]) == cost
    capacities = tuple(int(value) for value in graph.edge_capacity_units())
    n.replace_link("z|a|0", capacity=40)
    assert tuple(int(value) for value in graph.edge_capacity_units()) == capacities
    assert not hasattr(topology, "_network")
    with pytest.raises(TypeError):
        topology.node_id_by_name["a"] = 2
    with pytest.raises(FrozenInstanceError):
        topology.q = 2


def test_physical_failure_both_directions_and_directed_exclusion_control():
    topology = compile_topology(sample(), 1)
    forward, reverse = topology.edges_by_link["a|m|0"]
    physical = eligibility(topology, excluded_links=["a|m|0"]).edge_allowed()
    assert not physical[forward] and not physical[reverse]
    directed = topology.graph.eligibility(excluded_edges=[forward]).edge_allowed()
    assert not directed[forward] and directed[reverse]
    assert topology.disabled.edge_allowed().all()


def test_finite_pools_outgoing_sums_positive_cost_and_private_head():
    topology = compile_topology(sample(), 1, pools={"d0": ("a", "m"), "d1": ("a",)})
    assert set(topology.node_id_by_name) == {"a", "m", "z"}
    assert topology.graph.num_nodes() == 5
    caps, costs = topology.graph.edge_capacity_units(), topology.graph.edge_costs()
    found = {
        ref: (int(caps[i]), int(costs[i]))
        for i, ref in enumerate(topology.edge_refs)
        if isinstance(ref, SyntheticIngress)
    }
    assert found == {
        SyntheticIngress("d0", "a"): (9, 1),
        SyntheticIngress("d0", "m"): (5, 1),
        SyntheticIngress("d1", "a"): (9, 1),
    }
    assert int(caps.sum()) == 18 + 9 + 5 + 9
    assert int(costs.sum()) == 16 + 3


@pytest.mark.parametrize("cost", [0, -1, True, 0.5, float("nan"), float("inf"), 2**62])
def test_bad_cost_labels_and_control(cost):
    # The link refuses the cost where it is given, so the network keeps its link.
    n = sample()
    before = n.links["a|m|0"]
    with pytest.raises(ValueError, match=r"^link a->m\.cost: .*got "):
        n.replace_link("a|m|0", cost=cost)
    assert n.links["a|m|0"] is before
    n.replace_link("a|m|0", cost=2.0)
    assert n.links["a|m|0"].cost == 2 and type(n.links["a|m|0"].cost) is int
    assert compile_topology(n, 1).graph.num_edges() == 6


def test_augmented_capacity_sum_refuses_even_when_each_entry_is_legal():
    n = Network()
    n.add_node(Node("a"))
    n.add_node(Node("b"))
    n.add_link(Link("a", "b", 2**60, 1))
    assert int(compile_topology(n, 1).graph.edge_capacity_units().sum()) == 2**61
    with pytest.raises(ValueError, match="augmented capacity sum"):
        compile_topology(n, 1, pools={"p0": ("a", "b"), "p1": ("a",)})


def test_pool_attachments_at_q_2_minus_13_are_finite_and_inside_the_range():
    # At q = 2^-13 a capacity of 100 is 819,200 units. Each source's private ingress
    # attachment is max(B_s, O_limit) = its outgoing capacity (ordered: no offer budget),
    # cost 1. Graph sum: four directed link edges and two attachments of 819,200 =
    # 4,915,200 < 2^62. The old cost-0 sentinel of 10^15 would be 8.192e18 > 2^62.
    from ngraph import Scenario, prepare

    text = """
units: {resolution: 0.0001220703125}
network:
  nodes: {s1: {}, s2: {}, t: {}}
  links:
    - {source: s1, target: t, capacity: 100, cost: 1}
    - {source: s2, target: t, capacity: 100, cost: 1}
demands:
  d:
    - {source: ^(s1|s2)$, target: ^t$, volume: 150, mode: combine, preset: TE_ECMP_16_LSP}
workflow:
  - {type: TrafficMatrixPlacement, name: p, demand_set: d, workers: 1}
"""
    topology = prepare(Scenario.from_yaml(text)).topology
    assert topology.q == 2**-13
    caps, costs = topology.graph.edge_capacity_units(), topology.graph.edge_costs()
    found = {
        ref.source: (int(caps[i]), int(costs[i]))
        for i, ref in enumerate(topology.edge_refs)
        if isinstance(ref, SyntheticIngress)
    }
    assert found == {"s1": (819200, 1), "s2": (819200, 1)}
    assert int(caps.sum()) == 4915200 < 2**62
