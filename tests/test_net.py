import pytest

from ngraph.net import Net, Link, Node
from .sample_data.sample_net import *


def test_net_1(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    assert net.nodes == {
        "bb.ams1": Node(node_id="bb.ams1"),
        "bb.ams2": Node(node_id="bb.ams2"),
        "bb.fra1": Node(node_id="bb.fra1"),
        "bb.fra2": Node(node_id="bb.fra2"),
        "bb.lon1": Node(node_id="bb.lon1"),
        "bb.lon2": Node(node_id="bb.lon2"),
        "bb.par1": Node(node_id="bb.par1"),
        "bb.par2": Node(node_id="bb.par2"),
        "dc1.fra": Node(node_id="dc1.fra"),
        "dc1.lon": Node(node_id="dc1.lon"),
        "dc1.par": Node(node_id="dc1.par"),
        "pop1.ams": Node(node_id="pop1.ams"),
        "pop1.lon": Node(node_id="pop1.lon"),
    }
    assert net.links == {
        0: Link(
            node_a="bb.lon1",
            node_z="bb.ams1",
            metric=175,
            capacity=1200,
            edges=[0, 1],
            link_id=0,
        ),
        1: Link(
            node_a="bb.lon2",
            node_z="bb.ams2",
            metric=175,
            capacity=1200,
            edges=[2, 3],
            link_id=1,
        ),
        2: Link(
            node_a="bb.lon1",
            node_z="bb.lon2",
            metric=10,
            capacity=1500,
            edges=[4, 5],
            link_id=2,
        ),
        3: Link(
            node_a="bb.ams1",
            node_z="bb.ams2",
            metric=10,
            capacity=1500,
            edges=[6, 7],
            link_id=3,
        ),
        4: Link(
            node_a="bb.lon1",
            node_z="bb.fra1",
            metric=310,
            capacity=1200,
            edges=[8, 9],
            link_id=4,
        ),
        5: Link(
            node_a="bb.lon2",
            node_z="bb.fra2",
            metric=310,
            capacity=1200,
            edges=[10, 11],
            link_id=5,
        ),
        6: Link(
            node_a="bb.fra1",
            node_z="bb.fra2",
            metric=10,
            capacity=1500,
            edges=[12, 13],
            link_id=6,
        ),
        7: Link(
            node_a="bb.lon1",
            node_z="bb.par1",
            metric=170,
            capacity=1200,
            edges=[14, 15],
            link_id=7,
        ),
        8: Link(
            node_a="bb.lon2",
            node_z="bb.par2",
            metric=170,
            capacity=1200,
            edges=[16, 17],
            link_id=8,
        ),
        9: Link(
            node_a="bb.par1",
            node_z="bb.par2",
            metric=10,
            capacity=1500,
            edges=[18, 19],
            link_id=9,
        ),
        10: Link(
            node_a="dc1.lon",
            node_z="bb.lon1",
            metric=10,
            capacity=400,
            edges=[20, 21],
            link_id=10,
        ),
        11: Link(
            node_a="dc1.lon",
            node_z="bb.lon2",
            metric=10,
            capacity=400,
            edges=[22, 23],
            link_id=11,
        ),
        12: Link(
            node_a="dc1.fra",
            node_z="bb.fra1",
            metric=10,
            capacity=400,
            edges=[24, 25],
            link_id=12,
        ),
        13: Link(
            node_a="dc1.fra",
            node_z="bb.fra2",
            metric=10,
            capacity=400,
            edges=[26, 27],
            link_id=13,
        ),
        14: Link(
            node_a="dc1.par",
            node_z="bb.par1",
            metric=10,
            capacity=400,
            edges=[28, 29],
            link_id=14,
        ),
        15: Link(
            node_a="dc1.par",
            node_z="bb.par2",
            metric=10,
            capacity=400,
            edges=[30, 31],
            link_id=15,
        ),
        16: Link(
            node_a="pop1.lon",
            node_z="bb.lon1",
            metric=10,
            capacity=200,
            edges=[32, 33],
            link_id=16,
        ),
        17: Link(
            node_a="pop1.lon",
            node_z="bb.lon2",
            metric=10,
            capacity=200,
            edges=[34, 35],
            link_id=17,
        ),
        18: Link(
            node_a="pop1.ams",
            node_z="bb.ams1",
            metric=10,
            capacity=200,
            edges=[36, 37],
            link_id=18,
        ),
        19: Link(
            node_a="pop1.ams",
            node_z="bb.ams2",
            metric=10,
            capacity=200,
            edges=[38, 39],
            link_id=19,
        ),
    }

    assert net.graph.get_edges() == {
        0: (
            "bb.lon1",
            "bb.ams1",
            0,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [0, 1],
                "flow": 0,
                "flows": {},
                "link_id": 0,
                "metric": 175,
                "node_a": "bb.lon1",
                "node_z": "bb.ams1",
            },
        ),
        1: (
            "bb.ams1",
            "bb.lon1",
            1,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [0, 1],
                "flow": 0,
                "flows": {},
                "link_id": 0,
                "metric": 175,
                "node_a": "bb.lon1",
                "node_z": "bb.ams1",
            },
        ),
        2: (
            "bb.lon2",
            "bb.ams2",
            2,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [2, 3],
                "flow": 0,
                "flows": {},
                "link_id": 1,
                "metric": 175,
                "node_a": "bb.lon2",
                "node_z": "bb.ams2",
            },
        ),
        3: (
            "bb.ams2",
            "bb.lon2",
            3,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [2, 3],
                "flow": 0,
                "flows": {},
                "link_id": 1,
                "metric": 175,
                "node_a": "bb.lon2",
                "node_z": "bb.ams2",
            },
        ),
        4: (
            "bb.lon1",
            "bb.lon2",
            4,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [4, 5],
                "flow": 0,
                "flows": {},
                "link_id": 2,
                "metric": 10,
                "node_a": "bb.lon1",
                "node_z": "bb.lon2",
            },
        ),
        5: (
            "bb.lon2",
            "bb.lon1",
            5,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [4, 5],
                "flow": 0,
                "flows": {},
                "link_id": 2,
                "metric": 10,
                "node_a": "bb.lon1",
                "node_z": "bb.lon2",
            },
        ),
        6: (
            "bb.ams1",
            "bb.ams2",
            6,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [6, 7],
                "flow": 0,
                "flows": {},
                "link_id": 3,
                "metric": 10,
                "node_a": "bb.ams1",
                "node_z": "bb.ams2",
            },
        ),
        7: (
            "bb.ams2",
            "bb.ams1",
            7,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [6, 7],
                "flow": 0,
                "flows": {},
                "link_id": 3,
                "metric": 10,
                "node_a": "bb.ams1",
                "node_z": "bb.ams2",
            },
        ),
        8: (
            "bb.lon1",
            "bb.fra1",
            8,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [8, 9],
                "flow": 0,
                "flows": {},
                "link_id": 4,
                "metric": 310,
                "node_a": "bb.lon1",
                "node_z": "bb.fra1",
            },
        ),
        9: (
            "bb.fra1",
            "bb.lon1",
            9,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [8, 9],
                "flow": 0,
                "flows": {},
                "link_id": 4,
                "metric": 310,
                "node_a": "bb.lon1",
                "node_z": "bb.fra1",
            },
        ),
        10: (
            "bb.lon2",
            "bb.fra2",
            10,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [10, 11],
                "flow": 0,
                "flows": {},
                "link_id": 5,
                "metric": 310,
                "node_a": "bb.lon2",
                "node_z": "bb.fra2",
            },
        ),
        11: (
            "bb.fra2",
            "bb.lon2",
            11,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [10, 11],
                "flow": 0,
                "flows": {},
                "link_id": 5,
                "metric": 310,
                "node_a": "bb.lon2",
                "node_z": "bb.fra2",
            },
        ),
        12: (
            "bb.fra1",
            "bb.fra2",
            12,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [12, 13],
                "flow": 0,
                "flows": {},
                "link_id": 6,
                "metric": 10,
                "node_a": "bb.fra1",
                "node_z": "bb.fra2",
            },
        ),
        13: (
            "bb.fra2",
            "bb.fra1",
            13,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [12, 13],
                "flow": 0,
                "flows": {},
                "link_id": 6,
                "metric": 10,
                "node_a": "bb.fra1",
                "node_z": "bb.fra2",
            },
        ),
        14: (
            "bb.lon1",
            "bb.par1",
            14,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [14, 15],
                "flow": 0,
                "flows": {},
                "link_id": 7,
                "metric": 170,
                "node_a": "bb.lon1",
                "node_z": "bb.par1",
            },
        ),
        15: (
            "bb.par1",
            "bb.lon1",
            15,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [14, 15],
                "flow": 0,
                "flows": {},
                "link_id": 7,
                "metric": 170,
                "node_a": "bb.lon1",
                "node_z": "bb.par1",
            },
        ),
        16: (
            "bb.lon2",
            "bb.par2",
            16,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [16, 17],
                "flow": 0,
                "flows": {},
                "link_id": 8,
                "metric": 170,
                "node_a": "bb.lon2",
                "node_z": "bb.par2",
            },
        ),
        17: (
            "bb.par2",
            "bb.lon2",
            17,
            {
                "bidirectional": True,
                "capacity": 1200,
                "edges": [16, 17],
                "flow": 0,
                "flows": {},
                "link_id": 8,
                "metric": 170,
                "node_a": "bb.lon2",
                "node_z": "bb.par2",
            },
        ),
        18: (
            "bb.par1",
            "bb.par2",
            18,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [18, 19],
                "flow": 0,
                "flows": {},
                "link_id": 9,
                "metric": 10,
                "node_a": "bb.par1",
                "node_z": "bb.par2",
            },
        ),
        19: (
            "bb.par2",
            "bb.par1",
            19,
            {
                "bidirectional": True,
                "capacity": 1500,
                "edges": [18, 19],
                "flow": 0,
                "flows": {},
                "link_id": 9,
                "metric": 10,
                "node_a": "bb.par1",
                "node_z": "bb.par2",
            },
        ),
        20: (
            "dc1.lon",
            "bb.lon1",
            20,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [20, 21],
                "flow": 0,
                "flows": {},
                "link_id": 10,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon1",
            },
        ),
        21: (
            "bb.lon1",
            "dc1.lon",
            21,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [20, 21],
                "flow": 0,
                "flows": {},
                "link_id": 10,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon1",
            },
        ),
        22: (
            "dc1.lon",
            "bb.lon2",
            22,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [22, 23],
                "flow": 0,
                "flows": {},
                "link_id": 11,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon2",
            },
        ),
        23: (
            "bb.lon2",
            "dc1.lon",
            23,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [22, 23],
                "flow": 0,
                "flows": {},
                "link_id": 11,
                "metric": 10,
                "node_a": "dc1.lon",
                "node_z": "bb.lon2",
            },
        ),
        24: (
            "dc1.fra",
            "bb.fra1",
            24,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [24, 25],
                "flow": 0,
                "flows": {},
                "link_id": 12,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra1",
            },
        ),
        25: (
            "bb.fra1",
            "dc1.fra",
            25,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [24, 25],
                "flow": 0,
                "flows": {},
                "link_id": 12,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra1",
            },
        ),
        26: (
            "dc1.fra",
            "bb.fra2",
            26,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [26, 27],
                "flow": 0,
                "flows": {},
                "link_id": 13,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra2",
            },
        ),
        27: (
            "bb.fra2",
            "dc1.fra",
            27,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [26, 27],
                "flow": 0,
                "flows": {},
                "link_id": 13,
                "metric": 10,
                "node_a": "dc1.fra",
                "node_z": "bb.fra2",
            },
        ),
        28: (
            "dc1.par",
            "bb.par1",
            28,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [28, 29],
                "flow": 0,
                "flows": {},
                "link_id": 14,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par1",
            },
        ),
        29: (
            "bb.par1",
            "dc1.par",
            29,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [28, 29],
                "flow": 0,
                "flows": {},
                "link_id": 14,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par1",
            },
        ),
        30: (
            "dc1.par",
            "bb.par2",
            30,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [30, 31],
                "flow": 0,
                "flows": {},
                "link_id": 15,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par2",
            },
        ),
        31: (
            "bb.par2",
            "dc1.par",
            31,
            {
                "bidirectional": True,
                "capacity": 400,
                "edges": [30, 31],
                "flow": 0,
                "flows": {},
                "link_id": 15,
                "metric": 10,
                "node_a": "dc1.par",
                "node_z": "bb.par2",
            },
        ),
        32: (
            "pop1.lon",
            "bb.lon1",
            32,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [32, 33],
                "flow": 0,
                "flows": {},
                "link_id": 16,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon1",
            },
        ),
        33: (
            "bb.lon1",
            "pop1.lon",
            33,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [32, 33],
                "flow": 0,
                "flows": {},
                "link_id": 16,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon1",
            },
        ),
        34: (
            "pop1.lon",
            "bb.lon2",
            34,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [34, 35],
                "flow": 0,
                "flows": {},
                "link_id": 17,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon2",
            },
        ),
        35: (
            "bb.lon2",
            "pop1.lon",
            35,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [34, 35],
                "flow": 0,
                "flows": {},
                "link_id": 17,
                "metric": 10,
                "node_a": "pop1.lon",
                "node_z": "bb.lon2",
            },
        ),
        36: (
            "pop1.ams",
            "bb.ams1",
            36,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [36, 37],
                "flow": 0,
                "flows": {},
                "link_id": 18,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams1",
            },
        ),
        37: (
            "bb.ams1",
            "pop1.ams",
            37,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [36, 37],
                "flow": 0,
                "flows": {},
                "link_id": 18,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams1",
            },
        ),
        38: (
            "pop1.ams",
            "bb.ams2",
            38,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [38, 39],
                "flow": 0,
                "flows": {},
                "link_id": 19,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams2",
            },
        ),
        39: (
            "bb.ams2",
            "pop1.ams",
            39,
            {
                "bidirectional": True,
                "capacity": 200,
                "edges": [38, 39],
                "flow": 0,
                "flows": {},
                "link_id": 19,
                "metric": 10,
                "node_a": "pop1.ams",
                "node_z": "bb.ams2",
            },
        ),
    }


def test_net_add_remove_virtual_nodes_1(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    net.create_virtnode("fra")

    with pytest.raises(ValueError):
        net.create_virtnode("fra")

    assert "fra" in net.virtnodes
    assert "fra" not in net.nodes
    assert "fra" in net.graph

    net.remove_virtnode("fra")

    assert "fra" not in net.virtnodes
    assert "fra" not in net.nodes
    assert "fra" not in net.graph


def test_net_add_remove_virtual_nodes_2(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    with pytest.raises(ValueError):
        net.remove_virtnode("fra")

    with pytest.raises(ValueError):
        net.remove_virtnode("bb.fra1")


def test_net_add_remove_virtual_nodes_3(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    with pytest.raises(ValueError):
        net.create_virtlink("fra", "bb.fra1")


def test_net_add_remove_virtual_links_1(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    net.create_virtnode("fra")

    assert "fra" in net.virtnodes
    assert "fra" not in net.nodes
    assert "fra" in net.graph

    virtlink_id = net.create_virtlink("fra", "bb.fra1")
    assert virtlink_id in net.virtlinks
    assert virtlink_id not in net.links
    assert net.graph["fra"]["bb.fra1"] == {
        -1: {"virtual": True, "metric": 0, "capacity": float("inf")}
    }

    virtlink_id = net.create_virtlink("bb.fra1", "fra")
    assert virtlink_id in net.virtlinks
    assert virtlink_id not in net.links
    assert net.graph["bb.fra1"]["fra"] == {
        -2: {"virtual": True, "metric": 0, "capacity": float("inf")}
    }


def test_net_add_remove_virtual_links_2(bb_net_1):
    NODES, LINKS = bb_net_1
    net = Net()
    net.add_nodes_from(NODES)
    net.add_links_from(LINKS)

    net.create_virtnode("fra")
    virtlink_id1 = net.create_virtlink("fra", "bb.fra1")
    virtlink_id2 = net.create_virtlink("bb.fra1", "fra")

    net.remove_virtlink(virtlink_id1)
    assert virtlink_id1 not in net.virtlinks
    assert "bb.fra1" not in net.graph["fra"]

    net.remove_virtnode("fra")
    assert virtlink_id2 not in net.virtlinks
    assert "fra" not in net.graph["bb.fra1"]
    assert "fra" not in net.virtnodes

    with pytest.raises(ValueError):
        net.remove_virtlink(virtlink_id2)
