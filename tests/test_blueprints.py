import pytest
from ngraph.network import Network, Node, Link

from ngraph.blueprints import (
    DSLExpansionContext,
    Blueprint,
    _apply_parameters,
    _join_paths,
    _create_link,
    _expand_adjacency_pattern,
    _process_direct_nodes,
    _process_direct_links,
    _expand_blueprint_adjacency,
    _expand_adjacency,
    _expand_group,
    _update_nodes,
    _update_links,
    _process_node_overrides,
    _process_link_overrides,
    expand_network_dsl,
)


def test_join_paths():
    """
    Tests _join_paths for correct handling of leading slash, parent/child combinations, etc.
    """
    # No parent path, no slash
    assert _join_paths("", "SFO") == "SFO"
    # No parent path, child with leading slash => "SFO"
    assert _join_paths("", "/SFO") == "SFO"
    # Parent path plus child => "SEA/leaf"
    assert _join_paths("SEA", "leaf") == "SEA/leaf"
    # Parent path plus leading slash => "SEA/leaf"
    assert _join_paths("SEA", "/leaf") == "SEA/leaf"


def test_apply_parameters():
    """
    Tests _apply_parameters to ensure user-provided overrides get applied
    to the correct subgroup fields.
    """
    original_def = {
        "node_count": 4,
        "name_template": "spine-{node_num}",
        "other_attr": True,
    }
    params = {
        # Overwrite node_count for 'spine'
        "spine.node_count": 6,
        # Overwrite name_template for 'spine'
        "spine.name_template": "myspine-{node_num}",
        # Overwrite a non-existent param => ignored
        "leaf.node_count": 10,
    }
    updated = _apply_parameters("spine", original_def, params)
    assert updated["node_count"] == 6
    assert updated["name_template"] == "myspine-{node_num}"
    # Check that we preserved "other_attr"
    assert updated["other_attr"] is True
    # Check that there's no spurious new key
    assert len(updated) == 3, f"Unexpected keys: {updated.keys()}"


def test_create_link():
    """
    Tests _create_link to verify creation and insertion into a Network.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    _create_link(net, "A", "B", {"capacity": 50, "cost": 5, "attrs": {"color": "red"}})

    assert len(net.links) == 1
    link_obj = list(net.links.values())[0]
    assert link_obj.source == "A"
    assert link_obj.target == "B"
    assert link_obj.capacity == 50
    assert link_obj.cost == 5
    assert link_obj.attrs["color"] == "red"


def test_create_link_multiple():
    """
    Tests _create_link with link_count=2 to ensure multiple parallel links are created.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    _create_link(
        net,
        "A",
        "B",
        {"capacity": 10, "cost": 1, "attrs": {"color": "green"}},
        link_count=2,
    )

    assert len(net.links) == 2
    for link_obj in net.links.values():
        assert link_obj.source == "A"
        assert link_obj.target == "B"
        assert link_obj.capacity == 10
        assert link_obj.cost == 1
        assert link_obj.attrs["color"] == "green"


def test_expand_adjacency_pattern_one_to_one():
    """
    Tests _expand_adjacency_pattern in 'one_to_one' mode for a simple 2:2 case.
    Should produce pairs: (S1->T1), (S2->T2).
    """
    ctx_net = Network()
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext(blueprints={}, network=ctx_net)

    _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {"capacity": 10})
    # We expect 2 links: S1->T1, S2->T2
    assert len(ctx_net.links) == 2
    # Confirm the pairs
    pairs = {(l.source, l.target) for l in ctx_net.links.values()}
    assert pairs == {("S1", "T1"), ("S2", "T2")}

    # Also confirm the capacity
    for l in ctx_net.links.values():
        assert l.capacity == 10


def test_expand_adjacency_pattern_one_to_one_wrap():
    """
    Tests 'one_to_one' with wrapping case: e.g., 4 vs 2. (both sides a multiple).
    => S1->T1, S2->T2, S3->T1, S4->T2 => total 4 links.
    """
    ctx_net = Network()
    # 4 source nodes
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("S3"))
    ctx_net.add_node(Node("S4"))
    # 2 target nodes
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext({}, ctx_net)

    _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {"cost": 99})
    # Expect 4 total links
    assert len(ctx_net.links) == 4
    # Check the actual pairs
    pairs = {(l.source, l.target) for l in ctx_net.links.values()}
    expected = {
        ("S1", "T1"),
        ("S2", "T2"),
        ("S3", "T1"),
        ("S4", "T2"),
    }
    assert pairs == expected
    for l in ctx_net.links.values():
        assert l.cost == 99


def test_expand_adjacency_pattern_one_to_one_mismatch():
    """
    Tests 'one_to_one' with a mismatch (3 vs 2) => raises a ValueError
    since 3 % 2 != 0.
    """
    ctx_net = Network()
    # 3 sources, 2 targets
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("S3"))
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext({}, ctx_net)

    with pytest.raises(ValueError) as exc:
        _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {})
    # Our error text checks
    assert "requires sizes with a multiple factor" in str(exc.value)


def test_expand_adjacency_pattern_mesh():
    """
    Tests _expand_adjacency_pattern in 'mesh' mode: all-to-all links among matched nodes,
    skipping self-loops and deduplicating reversed pairs.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("X1"))
    ctx_net.add_node(Node("X2"))
    ctx_net.add_node(Node("Y1"))
    ctx_net.add_node(Node("Y2"))

    ctx = DSLExpansionContext({}, ctx_net)

    # mesh => X1,X2 => Y1,Y2 => 4 links total
    _expand_adjacency_pattern(ctx, "X", "Y", "mesh", {"capacity": 99})
    assert len(ctx_net.links) == 4
    for link in ctx_net.links.values():
        assert link.capacity == 99


def test_expand_adjacency_pattern_mesh_link_count():
    """
    Tests 'mesh' mode with link_count=2 to ensure multiple parallel links are created per pairing.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("A1"))
    ctx_net.add_node(Node("A2"))
    ctx_net.add_node(Node("B1"))
    ctx_net.add_node(Node("B2"))

    ctx = DSLExpansionContext({}, ctx_net)

    _expand_adjacency_pattern(ctx, "A", "B", "mesh", {"attrs": {"color": "purple"}}, 2)
    # A1->B1, A1->B2, A2->B1, A2->B2 => each repeated 2 times => 8 total links
    assert len(ctx_net.links) == 8
    for link in ctx_net.links.values():
        assert link.attrs.get("color") == "purple"


def test_expand_adjacency_pattern_unknown():
    """
    Tests that an unknown adjacency pattern raises ValueError.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("N1"))
    ctx_net.add_node(Node("N2"))
    ctx = DSLExpansionContext({}, ctx_net)

    with pytest.raises(ValueError) as excinfo:
        _expand_adjacency_pattern(ctx, "N1", "N2", "non_existent_pattern", {})
    assert "Unknown adjacency pattern" in str(excinfo.value)


def test_process_direct_nodes():
    """
    Tests _process_direct_nodes to ensure direct node creation works.
    Existing nodes are not overwritten.
    """
    net = Network()
    net.add_node(Node("Existing"))

    network_data = {
        "nodes": {
            "New1": {"foo": "bar"},
            "Existing": {
                "override": "ignored"
            },  # This won't be merged since node already exists
        },
    }

    _process_direct_nodes(net, network_data)

    # "New1" was created
    assert "New1" in net.nodes
    assert net.nodes["New1"].attrs["foo"] == "bar"
    # "Existing" was not overwritten
    assert "override" not in net.nodes["Existing"].attrs


def test_process_direct_links():
    """
    Tests _process_direct_links to ensure direct link creation works.
    """
    net = Network()
    net.add_node(Node("Existing1"))
    net.add_node(Node("Existing2"))

    network_data = {
        "links": [
            {
                "source": "Existing1",
                "target": "Existing2",
                "link_params": {"capacity": 5},
            }
        ],
    }

    _process_direct_links(net, network_data)

    # Confirm that links were created
    assert len(net.links) == 1
    link = next(iter(net.links.values()))
    assert link.source == "Existing1"
    assert link.target == "Existing2"
    assert link.capacity == 5


def test_process_direct_links_link_count():
    """
    Tests _process_direct_links with link_count > 1 to ensure multiple parallel links.
    """
    net = Network()
    net.add_node(Node("N1"))
    net.add_node(Node("N2"))

    network_data = {
        "links": [
            {
                "source": "N1",
                "target": "N2",
                "link_params": {"capacity": 20},
                "link_count": 3,
            }
        ]
    }
    _process_direct_links(net, network_data)

    assert len(net.links) == 3
    for link_obj in net.links.values():
        assert link_obj.capacity == 20
        assert link_obj.source == "N1"
        assert link_obj.target == "N2"


def test_direct_links_same_node_raises():
    """
    Tests that creating a link that references the same node as source and target
    raises a ValueError.
    """
    net = Network()
    net.add_node(Node("X"))
    network_data = {
        "links": [
            {
                "source": "X",
                "target": "X",
            }
        ]
    }

    with pytest.raises(ValueError) as excinfo:
        _process_direct_links(net, network_data)
    assert "Link cannot have the same source and target" in str(excinfo.value)


def test_expand_blueprint_adjacency():
    """
    Tests _expand_blueprint_adjacency: verifying that relative paths inside a blueprint
    are joined with parent_path, then expanded as normal adjacency.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("Parent/leaf-1"))
    ctx_net.add_node(Node("Parent/leaf-2"))
    ctx_net.add_node(Node("Parent/spine-1"))

    ctx = DSLExpansionContext({}, ctx_net)

    adj_def = {
        "source": "/leaf-1",
        "target": "/spine-1",
        "pattern": "mesh",
        "link_params": {"cost": 999},
    }
    # parent_path => "Parent"
    _expand_blueprint_adjacency(ctx, adj_def, "Parent")

    # Only "Parent/leaf-1" matches the source path => single source node,
    # "Parent/spine-1" => single target node => 1 link
    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    assert link.source == "Parent/leaf-1"
    assert link.target == "Parent/spine-1"
    assert link.cost == 999


def test_expand_adjacency():
    """
    Tests _expand_adjacency for a top-level adjacency definition (non-blueprint),
    verifying that leading '/' is stripped and used to find nodes in the global context.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("Global/A1"))
    ctx_net.add_node(Node("Global/B1"))

    ctx = DSLExpansionContext({}, ctx_net)

    # adjacency => "one_to_one" with /Global/A1 -> /Global/B1
    adj_def = {
        "source": "/Global/A1",
        "target": "/Global/B1",
        "pattern": "one_to_one",
        "link_params": {"capacity": 10},
    }
    _expand_adjacency(ctx, adj_def)

    # single pairing => A1 -> B1
    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    assert link.source == "Global/A1"
    assert link.target == "Global/B1"
    assert link.capacity == 10


def test_expand_group_direct():
    """
    Tests _expand_group for a direct node group (no use_blueprint),
    ensuring node_count and name_template usage.
    """
    ctx_net = Network()
    ctx = DSLExpansionContext({}, ctx_net)

    group_def = {
        "node_count": 3,
        "name_template": "myNode-{node_num}",
        "coords": [1, 2],
    }
    _expand_group(ctx, parent_path="", group_name="TestGroup", group_def=group_def)

    # Expect 3 nodes => "TestGroup/myNode-1" ... "TestGroup/myNode-3"
    assert len(ctx_net.nodes) == 3
    for i in range(1, 4):
        name = f"TestGroup/myNode-{i}"
        assert name in ctx_net.nodes
        node = ctx_net.nodes[name]
        assert node.attrs["coords"] == [1, 2]
        assert node.attrs["type"] == "node"


def test_expand_group_blueprint():
    """
    Tests _expand_group referencing a blueprint (basic subgroups + adjacency).
    We'll create a blueprint 'bp1' with one subgroup and adjacency, then reference it from group 'Main'.
    """
    bp = Blueprint(
        name="bp1",
        groups={
            "leaf": {"node_count": 2},
        },
        adjacency=[
            {
                "source": "/leaf",
                "target": "/leaf",
                "pattern": "mesh",
            }
        ],
    )
    ctx_net = Network()
    ctx = DSLExpansionContext(blueprints={"bp1": bp}, network=ctx_net)

    # group_def referencing the blueprint
    group_def = {
        "use_blueprint": "bp1",
        "coords": [10, 20],
    }
    _expand_group(
        ctx,
        parent_path="",
        group_name="Main",
        group_def=group_def,
    )

    # This expands 2 leaf nodes => "Main/leaf/leaf-1", "Main/leaf/leaf-2"
    # plus adjacency => single link (leaf-1 <-> leaf-2) due to mesh + dedup
    assert len(ctx_net.nodes) == 2
    assert "Main/leaf/leaf-1" in ctx_net.nodes
    assert "Main/leaf/leaf-2" in ctx_net.nodes
    # coords should be carried over
    assert ctx_net.nodes["Main/leaf/leaf-1"].attrs["coords"] == [10, 20]

    # adjacency => mesh => 1 unique link
    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    sources_targets = {link.source, link.target}
    assert sources_targets == {"Main/leaf/leaf-1", "Main/leaf/leaf-2"}


def test_expand_group_blueprint_with_params():
    """
    Tests _expand_group with blueprint usage and parameter overrides.
    """
    bp = Blueprint(
        name="bp1",
        groups={
            "leaf": {
                "node_count": 2,
                "name_template": "leafy-{node_num}",
                "attrs": {"role": "old"},
            },
        },
        adjacency=[],
    )
    ctx_net = Network()
    ctx = DSLExpansionContext(blueprints={"bp1": bp}, network=ctx_net)

    group_def = {
        "use_blueprint": "bp1",
        "parameters": {
            # Overriding the name_template for the subgroup 'leaf'
            "leaf.name_template": "newleaf-{node_num}",
            "leaf.attrs.role": "updated",
        },
    }
    _expand_group(
        ctx,
        parent_path="ZoneA",
        group_name="Main",
        group_def=group_def,
    )

    # We expect 2 nodes => "ZoneA/Main/leaf/newleaf-1" and "...-2"
    # plus the updated role attribute
    assert len(ctx_net.nodes) == 2
    n1_name = "ZoneA/Main/leaf/newleaf-1"
    n2_name = "ZoneA/Main/leaf/newleaf-2"
    assert n1_name in ctx_net.nodes
    assert n2_name in ctx_net.nodes
    assert ctx_net.nodes[n1_name].attrs["role"] == "updated"
    assert ctx_net.nodes[n2_name].attrs["role"] == "updated"


def test_expand_group_blueprint_unknown():
    """
    Tests _expand_group with a reference to an unknown blueprint -> ValueError.
    """
    ctx_net = Network()
    ctx = DSLExpansionContext(blueprints={}, network=ctx_net)

    group_def = {
        "use_blueprint": "non_existent",
    }
    with pytest.raises(ValueError) as exc:
        _expand_group(
            ctx,
            parent_path="",
            group_name="Test",
            group_def=group_def,
        )
    assert "unknown blueprint 'non_existent'" in str(exc.value)


def test_update_nodes():
    """
    Tests _update_nodes to ensure it updates matching node attributes in bulk.
    """
    net = Network()
    net.add_node(Node("N1", attrs={"foo": "old"}))
    net.add_node(Node("N2", attrs={"foo": "old"}))
    net.add_node(Node("M1", attrs={"foo": "unchanged"}))

    # We only want to update nodes whose path matches "N"
    _update_nodes(net, "N", {"hw_type": "X100", "foo": "new"})

    # N1, N2 should get updated
    assert net.nodes["N1"].attrs["hw_type"] == "X100"
    assert net.nodes["N1"].attrs["foo"] == "new"
    assert net.nodes["N2"].attrs["hw_type"] == "X100"
    assert net.nodes["N2"].attrs["foo"] == "new"

    # M1 remains unchanged
    assert "hw_type" not in net.nodes["M1"].attrs
    assert net.nodes["M1"].attrs["foo"] == "unchanged"


def test_update_links():
    """
    Tests _update_links to ensure it updates matching links in bulk.
    """
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("S2"))
    net.add_node(Node("T1"))
    net.add_node(Node("T2"))

    # Create some links
    net.add_link(Link("S1", "T1"))
    net.add_link(Link("S2", "T2"))
    net.add_link(Link("T1", "S2"))  # reversed direction

    # Update all links from S->T with capacity=999
    _update_links(net, "S", "T", {"capacity": 999})

    # The link S1->T1 is updated
    link_st = [l for l in net.links.values() if l.source == "S1" and l.target == "T1"]
    assert link_st[0].capacity == 999

    link_st2 = [l for l in net.links.values() if l.source == "S2" and l.target == "T2"]
    assert link_st2[0].capacity == 999

    # The reversed link T1->S2 also matches if any_direction is True by default
    link_ts = [l for l in net.links.values() if l.source == "T1" and l.target == "S2"]
    assert link_ts[0].capacity == 999


def test_update_links_any_direction_false():
    """
    Tests _update_links with any_direction=False to ensure reversed links are NOT updated.
    """
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("T1"))

    # Create forward and reversed links
    fwd_link = Link("S1", "T1", capacity=10)
    rev_link = Link("T1", "S1", capacity=10)
    net.add_link(fwd_link)
    net.add_link(rev_link)

    # Update only S->T direction
    _update_links(net, "S", "T", {"capacity": 999}, any_direction=False)

    # Only the forward link is updated
    assert net.links[fwd_link.id].capacity == 999
    assert net.links[rev_link.id].capacity == 10


def test_process_node_overrides():
    """
    Tests _process_node_overrides to verify node attributes get updated
    based on the DSL's node_overrides block.
    """
    net = Network()
    net.add_node(Node("A/1"))
    net.add_node(Node("A/2"))
    net.add_node(Node("B/1"))

    network_data = {
        "node_overrides": [
            {
                "path": "A",  # matches "A/1" and "A/2"
                "attrs": {"optics_type": "SR4", "shared_risk_group": "SRG1"},
            }
        ]
    }
    _process_node_overrides(net, network_data)

    # "A/1" and "A/2" should be updated
    assert net.nodes["A/1"].attrs["optics_type"] == "SR4"
    assert net.nodes["A/1"].attrs["shared_risk_group"] == "SRG1"
    assert net.nodes["A/2"].attrs["optics_type"] == "SR4"
    assert net.nodes["A/2"].attrs["shared_risk_group"] == "SRG1"

    # "B/1" remains unchanged
    assert "optics_type" not in net.nodes["B/1"].attrs
    assert "shared_risk_group" not in net.nodes["B/1"].attrs


def test_process_link_overrides():
    """
    Tests _process_link_overrides to verify link attributes get updated
    based on the DSL's link_overrides block.
    """
    net = Network()
    net.add_node(Node("A/1"))
    net.add_node(Node("A/2"))
    net.add_node(Node("B/1"))

    net.add_link(Link("A/1", "A/2", attrs={"color": "red"}))
    net.add_link(Link("A/1", "B/1"))

    network_data = {
        "link_overrides": [
            {
                "source": "A/1",
                "target": "A/2",
                "link_params": {"capacity": 123, "attrs": {"color": "blue"}},
            }
        ]
    }

    _process_link_overrides(net, network_data)

    # Only the link A/1->A/2 is updated
    link1 = [l for l in net.links.values() if l.source == "A/1" and l.target == "A/2"][
        0
    ]
    assert link1.capacity == 123
    assert link1.attrs["color"] == "blue"

    # The other link remains unmodified
    link2 = [l for l in net.links.values() if l.source == "A/1" and l.target == "B/1"][
        0
    ]
    assert link2.capacity == 1.0  # default
    assert "color" not in link2.attrs


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
    # one_to_one => 2 total links
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
    # mesh => 4 unique links
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

    # "one_to_one" with a single node => skipping self-loops => 0 links
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
