import pytest

from ngraph.net import Net, Link, Node
from ngraph.lib.demand import Demand


@pytest.fixture
def bb_net_1():
    NODES = [
        Node("bb.lon1"),
        Node("bb.lon2"),
        Node("bb.ams1"),
        Node("bb.ams2"),
        Node("bb.fra1"),
        Node("bb.fra2"),
        Node("bb.par1"),
        Node("bb.par2"),
        Node("dc1.lon"),
        Node("dc1.fra"),
        Node("dc1.par"),
        Node("pop1.lon"),
        Node("pop1.ams"),
    ]
    LINKS = [
        Link("bb.lon1", "bb.ams1", metric=175, capacity=1200),
        Link("bb.lon2", "bb.ams2", metric=175, capacity=1200),
        Link("bb.lon1", "bb.lon2", metric=10, capacity=1500),
        Link("bb.ams1", "bb.ams2", metric=10, capacity=1500),
        Link("bb.lon1", "bb.fra1", metric=310, capacity=1200),
        Link("bb.lon2", "bb.fra2", metric=310, capacity=1200),
        Link("bb.fra1", "bb.fra2", metric=10, capacity=1500),
        Link("bb.lon1", "bb.par1", metric=170, capacity=1200),
        Link("bb.lon2", "bb.par2", metric=170, capacity=1200),
        Link("bb.par1", "bb.par2", metric=10, capacity=1500),
        Link("dc1.lon", "bb.lon1", metric=10, capacity=400),
        Link("dc1.lon", "bb.lon2", metric=10, capacity=400),
        Link("dc1.fra", "bb.fra1", metric=10, capacity=400),
        Link("dc1.fra", "bb.fra2", metric=10, capacity=400),
        Link("dc1.par", "bb.par1", metric=10, capacity=400),
        Link("dc1.par", "bb.par2", metric=10, capacity=400),
        Link("pop1.lon", "bb.lon1", metric=10, capacity=200),
        Link("pop1.lon", "bb.lon2", metric=10, capacity=200),
        Link("pop1.ams", "bb.ams1", metric=10, capacity=200),
        Link("pop1.ams", "bb.ams2", metric=10, capacity=200),
    ]
    return NODES, LINKS


@pytest.fixture
def bb_net_1_demands():
    DEMANDS = [
        Demand("dc1.lon", "dc1.fra", 100, demand_class=1),
        Demand("dc1.fra", "dc1.lon", 100, demand_class=1),
        Demand("dc1.lon", "dc1.par", 100, demand_class=1),
        Demand("dc1.par", "dc1.lon", 100, demand_class=1),
        Demand("dc1.lon", "dc1.fra", 100, demand_class=2),
        Demand("dc1.fra", "dc1.lon", 100, demand_class=2),
        Demand("dc1.lon", "dc1.par", 100, demand_class=2),
        Demand("dc1.par", "dc1.lon", 100, demand_class=2),
    ]
    return DEMANDS
