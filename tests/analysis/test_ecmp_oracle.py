"""Hand witnesses distinguish integer admission, source pooling and route costs."""

from tests.ecmp_oracle import equal_shortest_capacity, ideal_capacity
from tests.placement_fixture import network_of


def test_integer_rr_prefix_is_not_a_fluid_minimum():
    network = network_of([("s1", "t", 100, 1), ("s2", "t", 10, 1)])
    assert equal_shortest_capacity(network, ("s1", "s2"), ("t",), 1) == 21
    assert ideal_capacity(network, ("s1", "s2"), ("t",), 1) == 110
    network = network_of([("s1", "h", 100, 1), ("s2", "h", 20, 1), ("h", "t", 60, 1)])
    assert equal_shortest_capacity(network, ("s1", "s2"), ("t",), 1) == 41
    assert ideal_capacity(network, ("s1", "s2"), ("t",), 1) == 60


def test_sources_pool_at_shared_router_and_masks_recompute_support():
    network = network_of(
        [("s1", "r", 1, 1), ("s2", "r", 1, 1), ("r", "t", 1, 1), ("r", "t", 1, 1)]
    )
    assert equal_shortest_capacity(network, ("s1", "s2"), ("t",), 1) == 2
    assert (
        equal_shortest_capacity(
            network, ("s1", "s2"), ("t",), 1, excluded_links=("r|t|0",)
        )
        == 1
    )
    network = network_of(
        [("s", "a", 10, 1), ("a", "t", 10, 1), ("s", "b", 5, 2), ("b", "t", 5, 2)]
    )
    assert equal_shortest_capacity(network, ("s",), ("t",), 1) == 10
    assert ideal_capacity(network, ("s",), ("t",), 1) == 15
    assert (
        equal_shortest_capacity(network, ("s",), ("t",), 1, excluded_nodes=("a",)) == 5
    )
