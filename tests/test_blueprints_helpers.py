import pytest
from ngraph.network import Network, Node, Link

from ngraph.blueprints import (
    DSLExpansionContext,
    Blueprint,
    _apply_parameters,
    _join_paths,
    _find_nodes_by_path,
    _create_link,
    _expand_adjacency_pattern,
    _process_direct_nodes,
    _process_direct_links,
    _expand_blueprint_adjacency,
    _expand_adjacency,
    _expand_group,
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


def test_find_nodes_by_path():
    """
    Tests _find_nodes_by_path for exact matches, slash-based prefix matches, and fallback prefix pattern.
    """
    net = Network()
    # Add some nodes
    net.add_node(Node("SEA/spine/myspine-1"))
    net.add_node(Node("SEA/leaf/leaf-1"))
    net.add_node(Node("SEA-other"))
    net.add_node(Node("SFO"))

    # 1) Exact match => "SFO"
    nodes = _find_nodes_by_path(net, "SFO")
    assert len(nodes) == 1
    assert nodes[0].name == "SFO"

    # 2) Slash prefix => "SEA/spine" matches "SEA/spine/myspine-1"
    nodes = _find_nodes_by_path(net, "SEA/spine")
    assert len(nodes) == 1
    assert nodes[0].name == "SEA/spine/myspine-1"

    # 3) Fallback: "SEA-other" won't be found by slash prefix "SEA/other", but if we search "SEA-other",
    #    we do an exact match or a fallback "SEA-other" => here it's exact, so we get 1 node
    nodes = _find_nodes_by_path(net, "SEA-other")
    assert len(nodes) == 1
    assert nodes[0].name == "SEA-other"

    # 4) If we search just "SEA", we match "SEA/spine/myspine-1" and "SEA/leaf/leaf-1" by slash prefix,
    #    but "SEA-other" won't appear because fallback never triggers (we already found slash matches).
    nodes = _find_nodes_by_path(net, "SEA")
    found = set(n.name for n in nodes)
    assert found == {
        "SEA/spine/myspine-1",
        "SEA/leaf/leaf-1",
    }


def test_apply_parameters():
    """
    Tests _apply_parameters to ensure user-provided overrides get applied to the correct subgroup fields.
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


def test_expand_adjacency_pattern_one_to_one():
    """
    Tests _expand_adjacency_pattern in 'one_to_one' mode for the simplest matching case (2:2).
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
    Tests 'one_to_one' with wrapping case: e.g., 4 vs 2. (both sides a multiple)
    => S1->T1, S2->T2, S3->T1, S4->T2 => total 4 links
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
    since 3 % 2 != 0
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
    assert "requires either equal node counts or a valid wrap-around" in str(exc.value)


def test_expand_adjacency_pattern_mesh():
    """
    Tests _expand_adjacency_pattern in 'mesh' mode: all-to-all links among matched nodes,
    with dedup so we don't double-link reversed pairs.
    """
    ctx_net = Network()
    ctx_net.add_node(Node("X1"))
    ctx_net.add_node(Node("X2"))
    ctx_net.add_node(Node("Y1"))
    ctx_net.add_node(Node("Y2"))

    ctx = DSLExpansionContext({}, ctx_net)

    # mesh => X1, X2 => Y1, Y2 => 4 links total
    _expand_adjacency_pattern(ctx, "X", "Y", "mesh", {"capacity": 99})
    assert len(ctx_net.links) == 4
    for link in ctx_net.links.values():
        assert link.capacity == 99


def test_process_direct_nodes():
    """
    Tests _process_direct_nodes to ensure direct node creation
    works.
    """
    net = Network()
    net.add_node(Node("Existing"))

    network_data = {
        "nodes": {
            "New1": {"foo": "bar"},
            "Existing": {
                "override": "ignored"
            },  # This won't be merged since node exists
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


def test_expand_blueprint_adjacency():
    """
    Tests _expand_blueprint_adjacency: verifying that relative paths inside a blueprint are joined
    with parent_path, then expanded as normal adjacency.
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
    Tests _expand_group for a direct node group (no use_blueprint), ensuring node_count and name_template.
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
        blueprint_expansion=False,
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
