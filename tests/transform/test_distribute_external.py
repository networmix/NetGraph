import pytest

from ngraph.network import Network, Node
from ngraph.scenario import Scenario
from ngraph.transform.distribute_external import (
    DistributeExternalConnectivity,
    _StripeChooser,
)


def make_scenario_with_network(net):
    return Scenario(
        network=net, failure_policy=None, traffic_matrix_set={}, workflow=[]
    )


def test_stripe_chooser_stripes_and_select():
    nodes = [Node(name=f"n{i}") for i in range(5)]
    chooser = _StripeChooser(width=3)
    stripes = chooser.stripes(nodes)
    assert len(stripes) == 2
    assert [n.name for n in stripes[0]] == ["n0", "n1", "n2"]
    assert [n.name for n in stripes[1]] == ["n3", "n4"]
    # select round-robin
    assert chooser.select(0, stripes) == stripes[0]
    assert chooser.select(1, stripes) == stripes[1]
    assert chooser.select(2, stripes) == stripes[0]


def test_invalid_stripe_width():
    with pytest.raises(ValueError):
        DistributeExternalConnectivity(
            remote_locations=["r"], attachment_path=".*", stripe_width=0
        )


def test_apply_no_attachments_raises():
    net = Network()
    scenario = make_scenario_with_network(net)
    transform = DistributeExternalConnectivity(
        remote_locations=["r"], attachment_path="^a", stripe_width=1
    )
    with pytest.raises(RuntimeError):
        transform.apply(scenario)


def test_basic_distribution_and_idempotence():
    net = Network()
    # create 4 attachment nodes
    for i in range(1, 5):
        net.add_node(Node(name=f"a{i}"))
    scenario = make_scenario_with_network(net)
    transform = DistributeExternalConnectivity(
        remote_locations=["r1", "r2"],
        attachment_path="^a",
        stripe_width=2,
        link_count=1,
        capacity=5.0,
        cost=10.0,
        remote_prefix="p-",
    )
    # first apply
    transform.apply(scenario)
    # remote nodes created
    assert "p-r1" in net.nodes
    assert "p-r2" in net.nodes
    # links created correctly
    links = []
    for r, stripe in [("p-r1", ["a1", "a2"]), ("p-r2", ["a3", "a4"])]:
        for a in stripe:
            ids = net.get_links_between(r, a)
            assert len(ids) == 1
            link = net.links[ids[0]]
            assert link.capacity == 5.0
            assert link.cost == 10.0
            links.extend(ids)
    assert len(links) == 4
    # second apply should add additional links but not more nodes
    transform.apply(scenario)
    assert len(net.nodes) == 6  # 4 attachments + 2 remotes
    # nodes unchanged, but links doubled
    total_links = sum(
        len(net.get_links_between(r, a)) for r, a in [("p-r1", "a1"), ("p-r2", "a4")]
    )
    assert total_links == 4


def test_link_count_multiple():
    net = Network()
    for i in range(1, 3):
        net.add_node(Node(name=f"a{i}"))
    scenario = make_scenario_with_network(net)
    transform = DistributeExternalConnectivity(
        remote_locations=["r"],
        attachment_path="^a",
        stripe_width=2,
        link_count=2,
    )
    transform.apply(scenario)
    # default prefix "" so remote named 'r'
    ids = net.get_links_between("r", "a1")
    assert len(ids) == 2
