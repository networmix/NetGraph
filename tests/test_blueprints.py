import pytest

from ngraph.blueprints import expand_network_dsl
from ngraph.network import Node


def test_minimal_no_blueprints():
    """
    Tests a minimal DSL with no blueprints, no adjacency, and a single direct node/link.
    Ensures the DSL creates expected nodes/links in the simplest scenario.
    """
    scenario_data = {
        "network": {
            "name": "simple_network",
            "nodes": {"A": {"test_attr": 123}, "B": {}},
            "links": [{"source": "A", "target": "B", "link_params": {"capacity": 10}}],
        }
    }

    net = expand_network_dsl(scenario_data)

    assert net.attrs["name"] == "simple_network"
    assert len(net.nodes) == 2
    assert len(net.links) == 1

    assert "A" in net.nodes
    assert net.nodes["A"].attrs["test_attr"] == 123
    assert "B" in net.nodes

    # Grab the first (and only) Link object
    link = next(iter(net.links.values()))
    assert link.source == "A"
    assert link.target == "B"
    assert link.capacity == 10


def test_simple_blueprint():
    """
    Tests a scenario with one blueprint used by one group.
    Verifies that blueprint-based groups expand properly and adjacency is handled.
    """
    scenario_data = {
        "blueprints": {
            "clos_1tier": {
                "groups": {"leaf": {"node_count": 2}},
                "adjacency": [
                    {
                        "source": "/leaf",
                        "target": "/leaf",
                        "pattern": "mesh",
                        "link_params": {"cost": 10},
                    }
                ],
            }
        },
        "network": {
            "name": "test_simple_blueprint",
            "groups": {"R1": {"use_blueprint": "clos_1tier"}},
        },
    }

    net = expand_network_dsl(scenario_data)

    # Expect 2 leaf nodes under path "R1/leaf"
    assert len(net.nodes) == 2
    assert "R1/leaf/leaf-1" in net.nodes
    assert "R1/leaf/leaf-2" in net.nodes

    # The adjacency is "leaf <-> leaf" mesh => leaf-1 <-> leaf-2
    # mesh deduplicates reversed links => single link
    assert len(net.links) == 1
    only_link = next(iter(net.links.values()))
    assert only_link.source.endswith("leaf-1")
    assert only_link.target.endswith("leaf-2")
    assert only_link.cost == 10


def test_blueprint_parameters():
    """
    Tests parameter overrides in a blueprint scenario.
    Ensures that user-provided overrides (e.g., node_count) are applied.
    """
    scenario_data = {
        "blueprints": {
            "multi_layer": {
                "groups": {
                    "layerA": {"node_count": 2, "name_template": "layerA-{node_num}"},
                    "layerB": {"node_count": 2, "name_template": "layerB-{node_num}"},
                },
                "adjacency": [],
            }
        },
        "network": {
            "groups": {
                "MAIN": {
                    "use_blueprint": "multi_layer",
                    "parameters": {
                        "layerA.node_count": 3,
                        "layerA.name_template": "overrideA-{node_num}",
                    },
                }
            }
        },
    }

    net = expand_network_dsl(scenario_data)

    # layerA gets overridden to node_count=3
    # layerB remains node_count=2 => total 5 nodes
    assert len(net.nodes) == 5

    # Confirm naming override
    overrideA_nodes = [n for n in net.nodes if "overrideA-" in n]
    assert len(overrideA_nodes) == 3, "Expected 3 overrideA- nodes"
    layerB_nodes = [n for n in net.nodes if "layerB-" in n]
    assert len(layerB_nodes) == 2, "Expected 2 layerB- nodes"


def test_direct_nodes_and_links_alongside_blueprints():
    """
    Tests mixing a blueprint with direct nodes and links.
    Verifies direct nodes are added, links to blueprint-created nodes are valid.
    """
    scenario_data = {
        "blueprints": {
            "single_group": {
                "groups": {
                    "mygroup": {"node_count": 2, "name_template": "g-{node_num}"}
                },
                "adjacency": [],
            }
        },
        "network": {
            "groups": {"BP1": {"use_blueprint": "single_group"}},
            "nodes": {"ExtraNode": {"tag": "extra"}},
            "links": [
                {
                    "source": "BP1/mygroup/g-1",
                    "target": "ExtraNode",
                    "link_params": {"capacity": 50},
                }
            ],
        },
    }

    net = expand_network_dsl(scenario_data)

    # 2 blueprint nodes + 1 direct node => 3 total
    assert len(net.nodes) == 3
    assert "BP1/mygroup/g-1" in net.nodes
    assert "BP1/mygroup/g-2" in net.nodes
    assert "ExtraNode" in net.nodes

    # One link connecting blueprint node to direct node
    assert len(net.links) == 1
    link = next(iter(net.links.values()))
    assert link.source == "BP1/mygroup/g-1"
    assert link.target == "ExtraNode"
    assert link.capacity == 50


def test_adjacency_one_to_one():
    """
    Tests a one_to_one adjacency among two groups of equal size (2:2).
    We expect each source node pairs with one target node => total 2 links.
    """
    scenario_data = {
        "network": {
            "groups": {"GroupA": {"node_count": 2}, "GroupB": {"node_count": 2}},
            "adjacency": [
                {
                    "source": "/GroupA",
                    "target": "/GroupB",
                    "pattern": "one_to_one",
                    "link_params": {"capacity": 99},
                }
            ],
        }
    }

    net = expand_network_dsl(scenario_data)

    # 4 total nodes
    assert len(net.nodes) == 4
    # one_to_one => 2 total links => (GroupA/GroupA-1->GroupB/GroupB-1, GroupA/GroupA-2->GroupB/GroupB-2)
    assert len(net.links) == 2
    link_names = {(l.source, l.target) for l in net.links.values()}
    expected_links = {
        ("GroupA/GroupA-1", "GroupB/GroupB-1"),
        ("GroupA/GroupA-2", "GroupB/GroupB-2"),
    }
    assert link_names == expected_links
    for l in net.links.values():
        assert l.capacity == 99


def test_adjacency_one_to_one_wrap():
    """
    Tests a one_to_one adjacency among groups of size 4 and 2.
    Because 4%2 == 0, we can wrap around the smaller side => total 4 links.
    """
    scenario_data = {
        "network": {
            "groups": {"Big": {"node_count": 4}, "Small": {"node_count": 2}},
            "adjacency": [
                {
                    "source": "/Big",
                    "target": "/Small",
                    "pattern": "one_to_one",
                    "link_params": {"cost": 555},
                }
            ],
        }
    }

    net = expand_network_dsl(scenario_data)

    # 6 total nodes => Big(4) + Small(2)
    assert len(net.nodes) == 6
    # Wrap => Big-1->Small-1, Big-2->Small-2, Big-3->Small-1, Big-4->Small-2 => 4 links
    assert len(net.links) == 4
    link_pairs = {(l.source, l.target) for l in net.links.values()}
    expected = {
        ("Big/Big-1", "Small/Small-1"),
        ("Big/Big-2", "Small/Small-2"),
        ("Big/Big-3", "Small/Small-1"),
        ("Big/Big-4", "Small/Small-2"),
    }
    assert link_pairs == expected
    for l in net.links.values():
        assert l.cost == 555


def test_adjacency_mesh():
    """
    Tests a mesh adjacency among two groups, ensuring all nodes from each group are interconnected.
    """
    scenario_data = {
        "network": {
            "groups": {
                "Left": {"node_count": 2},  # => Left/Left-1, Left/Left-2
                "Right": {"node_count": 2},  # => Right/Right-1, Right/Right-2
            },
            "adjacency": [
                {
                    "source": "/Left",
                    "target": "/Right",
                    "pattern": "mesh",
                    "link_params": {"cost": 5},
                }
            ],
        }
    }

    net = expand_network_dsl(scenario_data)

    # 4 total nodes
    assert len(net.nodes) == 4
    # mesh => (Left-1->Right-1), (Left-1->Right-2), (Left-2->Right-1), (Left-2->Right-2) => 4 unique links
    assert len(net.links) == 4
    for link in net.links.values():
        assert link.cost == 5


def test_fallback_prefix_behavior():
    """
    Tests the fallback prefix logic. If no normal match, we do partial or 'path-' fallback.
    In this scenario, we have 1 node => "FallbackGroup/FallbackGroup-1".
    The adjacency tries a one_to_one pattern => if we want to skip self-loops in all patterns,
    the result is 0 links.
    """
    scenario_data = {
        "network": {
            "groups": {
                "FallbackGroup": {
                    "node_count": 1,
                    "name_template": "FallbackGroup-{node_num}",
                }
            },
            "adjacency": [
                {
                    "source": "FallbackGroup",
                    "target": "FallbackGroup",
                    "pattern": "one_to_one",
                }
            ],
        }
    }

    net = expand_network_dsl(scenario_data)

    # 1 node => name "FallbackGroup/FallbackGroup-1"
    assert len(net.nodes) == 1
    assert "FallbackGroup/FallbackGroup-1" in net.nodes

    # If we skip self-loops for "one_to_one", we get 0 links.
    # If your code doesn't skip self-loops in "one_to_one", you'll get 1 link.
    # Adjust as needed:
    assert len(net.links) == 0


def test_direct_link_unknown_node_raises():
    """
    Ensures that referencing unknown nodes in a direct link raises an error.
    """
    scenario_data = {
        "network": {
            "nodes": {"KnownNode": {}},
            "links": [{"source": "KnownNode", "target": "UnknownNode"}],
        }
    }

    with pytest.raises(ValueError) as excinfo:
        expand_network_dsl(scenario_data)

    assert "Link references unknown node(s): KnownNode, UnknownNode" in str(
        excinfo.value
    )


def test_existing_node_preserves_attrs():
    """
    Tests that if a node is already present in the network, direct node definitions don't overwrite
    its existing attributes except for 'type' which is ensured by default.
    """
    scenario_data = {
        "network": {
            "groups": {"Foo": {"node_count": 1, "name_template": "X-{node_num}"}},
            "nodes": {"Foo/X-1": {"myattr": 123}},
        }
    }

    net = expand_network_dsl(scenario_data)

    # There's only 1 node => "Foo/X-1"
    assert len(net.nodes) == 1
    node_obj = net.nodes["Foo/X-1"]

    # The code sets "type"="node" if not present but doesn't merge other attributes.
    # So "myattr" won't appear, because the node was created from groups.
    assert "myattr" not in node_obj.attrs
    assert node_obj.attrs["type"] == "node"
