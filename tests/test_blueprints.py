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
    """Tests _join_paths for correct handling of leading slash, parent/child combinations, etc."""
    assert _join_paths("", "SFO") == "SFO"
    assert _join_paths("", "/SFO") == "SFO"
    assert _join_paths("SEA", "leaf") == "SEA/leaf"
    assert _join_paths("SEA", "/leaf") == "SEA/leaf"


def test_apply_parameters():
    """Tests _apply_parameters to ensure user-provided overrides get applied correctly."""
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
    """Tests _create_link to verify creation and insertion into a Network."""
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
    # risk_groups defaults empty
    assert link_obj.risk_groups == set()


def test_create_link_risk_groups():
    """Tests _create_link with 'risk_groups' in link_params => sets link.risk_groups."""
    net = Network()
    net.add_node(Node("X"))
    net.add_node(Node("Y"))

    _create_link(
        net,
        "X",
        "Y",
        {
            "capacity": 20,
            "risk_groups": ["RG1", "RG2"],
            "attrs": {"line_type": "fiber"},
        },
    )
    assert len(net.links) == 1
    link_obj = next(iter(net.links.values()))
    assert link_obj.risk_groups == {"RG1", "RG2"}
    assert link_obj.attrs["line_type"] == "fiber"


def test_create_link_multiple():
    """Tests _create_link with link_count=2 => multiple parallel links are created."""
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
    """Tests _expand_adjacency_pattern in 'one_to_one' mode for a simple 2:2 case."""
    ctx_net = Network()
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext(blueprints={}, network=ctx_net)

    _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {"capacity": 10})
    # We expect 2 links: S1->T1, S2->T2
    assert len(ctx_net.links) == 2
    pairs = {(l.source, l.target) for l in ctx_net.links.values()}
    assert pairs == {("S1", "T1"), ("S2", "T2")}
    for l in ctx_net.links.values():
        assert l.capacity == 10


def test_expand_adjacency_pattern_one_to_one_wrap():
    """Tests 'one_to_one' with wrapping case: 4 vs 2 => total 4 links."""
    ctx_net = Network()
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("S3"))
    ctx_net.add_node(Node("S4"))
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext({}, ctx_net)

    _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {"cost": 99})
    # Expect 4 total links
    assert len(ctx_net.links) == 4
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
    """Tests 'one_to_one' with mismatch => raises ValueError."""
    ctx_net = Network()
    ctx_net.add_node(Node("S1"))
    ctx_net.add_node(Node("S2"))
    ctx_net.add_node(Node("S3"))
    ctx_net.add_node(Node("T1"))
    ctx_net.add_node(Node("T2"))

    ctx = DSLExpansionContext({}, ctx_net)

    with pytest.raises(ValueError) as exc:
        _expand_adjacency_pattern(ctx, "S", "T", "one_to_one", {})
    assert "requires sizes with a multiple factor" in str(exc.value)


def test_expand_adjacency_pattern_mesh():
    """Tests _expand_adjacency_pattern in 'mesh' mode: all-to-all, skipping self-loops."""
    ctx_net = Network()
    ctx_net.add_node(Node("X1"))
    ctx_net.add_node(Node("X2"))
    ctx_net.add_node(Node("Y1"))
    ctx_net.add_node(Node("Y2"))

    ctx = DSLExpansionContext({}, ctx_net)
    _expand_adjacency_pattern(ctx, "X", "Y", "mesh", {"capacity": 99})
    assert len(ctx_net.links) == 4
    for link in ctx_net.links.values():
        assert link.capacity == 99


def test_expand_adjacency_pattern_mesh_link_count():
    """Tests 'mesh' mode with link_count=2 => multiple parallel links per pairing."""
    ctx_net = Network()
    ctx_net.add_node(Node("A1"))
    ctx_net.add_node(Node("A2"))
    ctx_net.add_node(Node("B1"))
    ctx_net.add_node(Node("B2"))

    ctx = DSLExpansionContext({}, ctx_net)
    _expand_adjacency_pattern(ctx, "A", "B", "mesh", {"attrs": {"color": "purple"}}, 2)
    assert len(ctx_net.links) == 8
    for link in ctx_net.links.values():
        assert link.attrs.get("color") == "purple"


def test_expand_adjacency_pattern_unknown():
    """Tests that an unknown adjacency pattern raises ValueError."""
    ctx_net = Network()
    ctx_net.add_node(Node("N1"))
    ctx_net.add_node(Node("N2"))
    ctx = DSLExpansionContext({}, ctx_net)

    with pytest.raises(ValueError) as excinfo:
        _expand_adjacency_pattern(ctx, "N1", "N2", "non_existent_pattern", {})
    assert "Unknown adjacency pattern" in str(excinfo.value)


def test_process_direct_nodes():
    """
    Tests _process_direct_nodes with recognized top-level keys (disabled, attrs, risk_groups).
    We must put anything else inside 'attrs' or it triggers an error.
    """
    net = Network()
    net.add_node(Node("Existing"))

    network_data = {
        "nodes": {
            # 'New1' node
            "New1": {
                "disabled": True,
                "attrs": {
                    "foo": "bar",
                },
                "risk_groups": ["RGalpha"],
            },
            # "Existing" won't be changed because it's already present
            "Existing": {"attrs": {"would": "be_ignored"}, "risk_groups": ["RGbeta"]},
        },
    }

    _process_direct_nodes(net, network_data)
    # "New1" is added
    assert "New1" in net.nodes
    assert net.nodes["New1"].disabled is True
    assert net.nodes["New1"].attrs["foo"] == "bar"
    assert net.nodes["New1"].risk_groups == {"RGalpha"}

    # "Existing" => not overwritten
    assert net.nodes["Existing"].attrs == {}
    assert net.nodes["Existing"].risk_groups == set()


def test_process_direct_links():
    """Tests _process_direct_links to ensure direct link creation works under the new rules."""
    net = Network()
    net.add_node(Node("Existing1"))
    net.add_node(Node("Existing2"))

    network_data = {
        "links": [
            {
                "source": "Existing1",
                "target": "Existing2",
                "link_params": {"capacity": 5, "risk_groups": ["RGlink"]},
            }
        ],
    }

    _process_direct_links(net, network_data)
    assert len(net.links) == 1
    link = next(iter(net.links.values()))
    assert link.source == "Existing1"
    assert link.target == "Existing2"
    assert link.capacity == 5
    assert link.risk_groups == {"RGlink"}


def test_process_direct_links_link_count():
    """Tests _process_direct_links with link_count > 1 => multiple parallel links."""
    net = Network()
    net.add_node(Node("N1"))
    net.add_node(Node("N2"))

    network_data = {
        "links": [
            {
                "source": "N1",
                "target": "N2",
                "link_params": {"capacity": 20, "risk_groups": ["RGmulti"]},
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
        assert link_obj.risk_groups == {"RGmulti"}


def test_direct_links_same_node_raises():
    """Tests that creating a link with same source & target raises ValueError."""
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
    Tests _expand_blueprint_adjacency with local parent_path => verifying
    that relative paths get joined with parent_path.
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
    _expand_blueprint_adjacency(ctx, adj_def, "Parent")

    # leaf-1 => spine-1 => single link
    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    assert link.source == "Parent/leaf-1"
    assert link.target == "Parent/spine-1"
    assert link.cost == 999


def test_expand_adjacency():
    """Tests _expand_adjacency for a top-level adjacency definition."""
    ctx_net = Network()
    ctx_net.add_node(Node("Global/A1"))
    ctx_net.add_node(Node("Global/B1"))

    ctx = DSLExpansionContext({}, ctx_net)

    adj_def = {
        "source": "/Global/A1",
        "target": "/Global/B1",
        "pattern": "one_to_one",
        "link_params": {"capacity": 10},
    }
    _expand_adjacency(ctx, adj_def)

    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    assert link.source == "Global/A1"
    assert link.target == "Global/B1"
    assert link.capacity == 10


def test_expand_group_direct():
    """
    Tests _expand_group for a direct node group, ensuring node_count,
    name_template usage, plus optional risk_groups.
    """
    ctx_net = Network()
    ctx = DSLExpansionContext({}, ctx_net)

    group_def = {
        "node_count": 3,
        "name_template": "myNode-{node_num}",
        "attrs": {"coords": [1, 2]},
        "risk_groups": ["RGtest"],
    }
    _expand_group(ctx, parent_path="", group_name="TestGroup", group_def=group_def)

    # 3 nodes => "TestGroup/myNode-1..3"
    assert len(ctx_net.nodes) == 3
    for i in range(1, 4):
        name = f"TestGroup/myNode-{i}"
        assert name in ctx_net.nodes
        node_obj = ctx_net.nodes[name]
        assert node_obj.attrs["coords"] == [1, 2]
        assert node_obj.attrs["type"] == "node"
        assert node_obj.risk_groups == {"RGtest"}


def test_expand_group_blueprint():
    """
    Tests _expand_group referencing a blueprint. The parent's 'attrs' and 'risk_groups'
    are merged into the child nodes. We expect child nodes to have parent's coords
    plus parent's risk group.
    """
    bp = Blueprint(
        name="bp1",
        groups={
            "leaf": {"node_count": 2, "risk_groups": ["RGblue"]},
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

    group_def = {
        "use_blueprint": "bp1",
        "attrs": {"coords": [10, 20]},
        "risk_groups": ["RGparent"],
    }
    _expand_group(
        ctx,
        parent_path="",
        group_name="Main",
        group_def=group_def,
    )

    # expands 2 leaf nodes => "Main/leaf/leaf-1", "Main/leaf/leaf-2"
    assert len(ctx_net.nodes) == 2
    assert "Main/leaf/leaf-1" in ctx_net.nodes
    assert "Main/leaf/leaf-2" in ctx_net.nodes

    # parent's risk group => RGparent, child's => RGblue => union => {RGparent, RGblue}
    assert ctx_net.nodes["Main/leaf/leaf-1"].risk_groups == {"RGparent", "RGblue"}
    assert ctx_net.nodes["Main/leaf/leaf-1"].attrs["coords"] == [10, 20]

    # adjacency => single link
    assert len(ctx_net.links) == 1
    link = next(iter(ctx_net.links.values()))
    assert set([link.source, link.target]) == {"Main/leaf/leaf-1", "Main/leaf/leaf-2"}


def test_expand_group_blueprint_with_params():
    """Tests blueprint usage + parameter overrides + parent attrs + risk_groups merging."""
    bp = Blueprint(
        name="bp1",
        groups={
            "leaf": {
                "node_count": 2,
                "name_template": "leafy-{node_num}",
                "risk_groups": ["RGchild"],
            },
        },
        adjacency=[],
    )
    ctx_net = Network()
    ctx = DSLExpansionContext(blueprints={"bp1": bp}, network=ctx_net)

    group_def = {
        "use_blueprint": "bp1",
        "parameters": {
            "leaf.name_template": "newleaf-{node_num}",
        },
        "attrs": {"coords": [10, 20]},
        "risk_groups": ["RGparent"],
    }
    _expand_group(
        ctx,
        parent_path="ZoneA",
        group_name="Main",
        group_def=group_def,
    )

    # 2 nodes => "ZoneA/Main/leaf/newleaf-1" & "ZoneA/Main/leaf/newleaf-2"
    assert len(ctx_net.nodes) == 2
    n1 = "ZoneA/Main/leaf/newleaf-1"
    n2 = "ZoneA/Main/leaf/newleaf-2"
    assert n1 in ctx_net.nodes
    assert n2 in ctx_net.nodes

    # risk_groups => {RGparent, RGchild}
    assert ctx_net.nodes[n1].risk_groups == {"RGparent", "RGchild"}
    assert ctx_net.nodes[n1].attrs["coords"] == [10, 20]


def test_expand_group_blueprint_unknown():
    """Tests referencing an unknown blueprint => ValueError."""
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
    If 'disabled_val' is provided, sets node.disabled. If 'risk_groups_val' is provided,
    it replaces the node's existing risk_groups. Everything else merges into node.attrs.
    """
    net = Network()
    net.add_node(Node("N1", attrs={"foo": "old"}, risk_groups={"RGold"}))
    net.add_node(Node("N2", attrs={"foo": "old"}, risk_groups={"RGold"}))
    net.add_node(Node("M1", attrs={"foo": "unchanged"}))

    # Force N* nodes to disabled, replace risk_groups with RGnew, plus merge new attrs
    _update_nodes(
        net,
        "N",
        {"hw_type": "X100", "foo": "new"},
        disabled_val=True,
        risk_groups_val=["RGnew"],
    )
    # N1, N2 => updated
    assert net.nodes["N1"].disabled is True
    assert net.nodes["N1"].risk_groups == {"RGnew"}
    assert net.nodes["N1"].attrs["foo"] == "new"
    assert net.nodes["N1"].attrs["hw_type"] == "X100"

    assert net.nodes["N2"].disabled is True
    assert net.nodes["N2"].risk_groups == {"RGnew"}
    assert net.nodes["N2"].attrs["foo"] == "new"
    assert net.nodes["N2"].attrs["hw_type"] == "X100"

    # M1 => unchanged
    assert net.nodes["M1"].disabled is False
    assert net.nodes["M1"].attrs["foo"] == "unchanged"


def test_update_links():
    """
    Tests _update_links to ensure it updates matching links in bulk,
    using recognized link_params fields only, replacing risk_groups if provided.
    """
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("S2"))
    net.add_node(Node("T1"))
    net.add_node(Node("T2"))

    ln1 = Link("S1", "T1", risk_groups={"RGold"})
    ln2 = Link("S2", "T2")
    ln3 = Link("T1", "S2")  # reversed direction
    net.add_link(ln1)
    net.add_link(ln2)
    net.add_link(ln3)

    _update_links(
        net,
        "S",
        "T",
        {"capacity": 999, "risk_groups": ["RGoverride"]},
    )

    # S1->T1 updated
    link_st1 = net.links[ln1.id]
    assert link_st1.capacity == 999
    assert link_st1.risk_groups == {"RGoverride"}

    link_st2 = net.links[ln2.id]
    assert link_st2.capacity == 999
    assert link_st2.risk_groups == {"RGoverride"}

    # reversed T1->S2 also updated (any_direction=True by default)
    link_ts = net.links[ln3.id]
    assert link_ts.capacity == 999
    assert link_ts.risk_groups == {"RGoverride"}


def test_update_links_any_direction_false():
    """
    Tests _update_links with any_direction=False => only forward direction updated.
    """
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("T1"))

    fwd_link = Link("S1", "T1", capacity=10, risk_groups={"RGinit"})
    rev_link = Link("T1", "S1", capacity=10, risk_groups={"RGinit"})
    net.add_link(fwd_link)
    net.add_link(rev_link)

    _update_links(
        net, "S", "T", {"capacity": 999, "risk_groups": ["RGnew"]}, any_direction=False
    )
    assert net.links[fwd_link.id].capacity == 999
    assert net.links[fwd_link.id].risk_groups == {"RGnew"}

    # Reverse link is not updated
    assert net.links[rev_link.id].capacity == 10
    assert net.links[rev_link.id].risk_groups == {"RGinit"}


def test_process_node_overrides():
    """
    Tests _process_node_overrides => merges top-level 'disabled', 'risk_groups'
    and merges 'attrs' into node.attrs.
    """
    net = Network()
    net.add_node(Node("A/1", risk_groups={"RGold"}))
    net.add_node(Node("A/2", risk_groups={"RGold"}))
    net.add_node(Node("B/1"))

    network_data = {
        "node_overrides": [
            {
                "path": "A",
                "disabled": True,
                "risk_groups": ["RGnew"],
                "attrs": {"optics_type": "SR4"},
            }
        ]
    }
    _process_node_overrides(net, network_data)

    # A/1, A/2 => updated
    assert net.nodes["A/1"].disabled is True
    assert net.nodes["A/1"].risk_groups == {"RGnew"}
    assert net.nodes["A/1"].attrs["optics_type"] == "SR4"
    assert net.nodes["A/2"].disabled is True
    assert net.nodes["A/2"].risk_groups == {"RGnew"}
    assert net.nodes["A/2"].attrs["optics_type"] == "SR4"

    # B/1 => unchanged
    assert net.nodes["B/1"].disabled is False
    assert net.nodes["B/1"].risk_groups == set()
    assert "optics_type" not in net.nodes["B/1"].attrs


def test_process_link_overrides():
    """
    Tests _process_link_overrides => recognized top-level keys are source/target/link_params/any_direction,
    plus recognized link_params keys. No unknown keys are allowed.
    Also checks that 'risk_groups' in link_params replaces existing.
    """
    net = Network()
    net.add_node(Node("A/1"))
    net.add_node(Node("A/2"))
    net.add_node(Node("B/1"))

    l1 = Link("A/1", "A/2", attrs={"color": "red"}, risk_groups={"RGold"})
    l2 = Link("A/1", "B/1", risk_groups={"RGx"})
    net.add_link(l1)
    net.add_link(l2)

    network_data = {
        "link_overrides": [
            {
                "source": "A/1",
                "target": "A/2",
                "link_params": {
                    "capacity": 123,
                    "attrs": {"color": "blue"},
                    "risk_groups": ["RGnew"],
                },
            }
        ]
    }
    _process_link_overrides(net, network_data)

    # Only A/1->A/2 updated
    assert net.links[l1.id].capacity == 123
    assert net.links[l1.id].attrs["color"] == "blue"
    assert net.links[l1.id].risk_groups == {"RGnew"}

    # A/1->B/1 => not updated
    assert net.links[l2.id].capacity == 1.0
    assert net.links[l2.id].risk_groups == {"RGx"}


def test_minimal_no_blueprints():
    """Tests a minimal DSL with no blueprints, a single direct node, and link."""
    scenario_data = {
        "network": {
            "name": "simple_network",
            "nodes": {"A": {"attrs": {"test_attr": 123}}, "B": {"attrs": {}}},
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
    link = next(iter(net.links.values()))
    assert link.source == "A"
    assert link.target == "B"
    assert link.capacity == 10


def test_simple_blueprint():
    """
    Tests a scenario with one blueprint used by one group, verifying adjacency.
    This also tests that no unknown keys are present in the blueprint or group usage.
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
            "groups": {
                "R1": {
                    "use_blueprint": "clos_1tier",
                    # we could add "attrs", "disabled" or "risk_groups" here if we wanted
                },
            },
        },
    }

    net = expand_network_dsl(scenario_data)
    assert net.attrs["name"] == "test_simple_blueprint"
    assert len(net.nodes) == 2
    assert "R1/leaf/leaf-1" in net.nodes
    assert "R1/leaf/leaf-2" in net.nodes
    assert len(net.links) == 1
    only_link = next(iter(net.links.values()))
    assert only_link.source.endswith("leaf-1")
    assert only_link.target.endswith("leaf-2")
    assert only_link.cost == 10


def test_blueprint_parameters():
    """Tests parameter overrides in a blueprint scenario."""
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
    # layerA => 3, layerB => 2 => total 5 nodes
    assert len(net.nodes) == 5
    overrideA_nodes = [n for n in net.nodes if "overrideA-" in n]
    assert len(overrideA_nodes) == 3
    layerB_nodes = [n for n in net.nodes if "layerB-" in n]
    assert len(layerB_nodes) == 2


def test_direct_nodes_and_links_alongside_blueprints():
    """
    Tests mixing blueprint with direct nodes/links. All extra keys
    must be inside 'attrs' or recognized fields like 'risk_groups'.
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
            "nodes": {
                "ExtraNode": {"attrs": {"tag": "extra"}, "risk_groups": ["RGextra"]}
            },
            "links": [
                {
                    "source": "BP1/mygroup/g-1",
                    "target": "ExtraNode",
                    "link_params": {"capacity": 50, "risk_groups": ["RGlink"]},
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
    assert net.nodes["ExtraNode"].risk_groups == {"RGextra"}

    # 1 link connecting blueprint node to direct node
    assert len(net.links) == 1
    link = next(iter(net.links.values()))
    assert link.source == "BP1/mygroup/g-1"
    assert link.target == "ExtraNode"
    assert link.capacity == 50
    assert link.risk_groups == {"RGlink"}


def test_adjacency_one_to_one():
    """Tests a one_to_one adjacency among two groups of equal size (2:2)."""
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
    # 4 total nodes => 2 from each group
    assert len(net.nodes) == 4
    # one_to_one => 2 links
    pairs = {(l.source, l.target) for l in net.links.values()}
    expected = {
        ("GroupA/GroupA-1", "GroupB/GroupB-1"),
        ("GroupA/GroupA-2", "GroupB/GroupB-2"),
    }
    assert pairs == expected
    for l in net.links.values():
        assert l.capacity == 99


def test_adjacency_one_to_one_wrap():
    """Tests a one_to_one adjacency among groups of size 4 vs 2 => wrap => 4 links."""
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
    # 6 total => Big(4) + Small(2)
    assert len(net.nodes) == 6
    # wrap => 4 links
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
    """Tests a mesh adjacency among two groups => all nodes cross-connected."""
    scenario_data = {
        "network": {
            "groups": {
                "Left": {"node_count": 2},
                "Right": {"node_count": 2},
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


def test_fallback_small_single_node():
    """
    Just a small check: 1 group => 1 node => adjacency among same group => one_to_one
    => but single node => no link created if skipping self-loops.
    """
    scenario_data = {
        "network": {
            "groups": {
                "FallbackGroup": {
                    "node_count": 1,
                    "name_template": "X-{node_num}",
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
    # 1 node => "FallbackGroup/X-1"
    assert len(net.nodes) == 1
    # adjacency => single node => no link
    assert len(net.links) == 0


def test_direct_link_unknown_node_raises():
    """Ensures referencing unknown nodes in a direct link => ValueError."""
    scenario_data = {
        "network": {
            "nodes": {"KnownNode": {"attrs": {}}},
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
    Tests that if a node is already present (like from a group),
    direct node definition with same name does nothing (we skip).
    """
    scenario_data = {
        "network": {
            "groups": {"Foo": {"node_count": 1, "name_template": "X-{node_num}"}},
            # We'll define the same node here. The code should skip, leaving it as-is.
            "nodes": {"Foo/X-1": {"attrs": {"myattr": 123}, "disabled": True}},
        }
    }

    net = expand_network_dsl(scenario_data)
    # There's 1 node => "Foo/X-1" from group
    assert len(net.nodes) == 1
    node_obj = net.nodes["Foo/X-1"]
    # from the group creation => the node has "type": "node" but not "myattr"
    # and not disabled. We do not merge the direct node definition with it.
    assert node_obj.attrs["type"] == "node"
    assert "myattr" not in node_obj.attrs
    assert node_obj.disabled is False


def test_expand_network_dsl_empty():
    """Tests calling expand_network_dsl with an empty dictionary => empty Network."""
    net = expand_network_dsl({})
    assert len(net.nodes) == 0
    assert len(net.links) == 0
    assert not net.attrs


def test_network_version_attribute():
    """Tests that 'version' in the network data is recorded in net.attrs."""
    scenario_data = {"network": {"version": "1.2.3"}}
    net = expand_network_dsl(scenario_data)
    assert net.attrs["version"] == "1.2.3"


def test_expand_group_with_bracket_expansions():
    """Tests bracket expansions in group names => multiple expansions => replicate group_def."""
    ctx_net = Network()
    ctx = DSLExpansionContext({}, ctx_net)

    group_def = {"node_count": 1}
    _expand_group(
        ctx, parent_path="", group_name="fa[1-2]_plane[3-4]", group_def=group_def
    )

    expected = {
        "fa1_plane3/fa1_plane3-1",
        "fa1_plane4/fa1_plane4-1",
        "fa2_plane3/fa2_plane3-1",
        "fa2_plane4/fa2_plane4-1",
    }
    assert set(ctx_net.nodes.keys()) == expected


def test_apply_parameters_nested_fields():
    """
    Tests parameter overrides for nested fields beyond just 'attrs'.
    Here we keep 'some_field' under 'attrs' so it is recognized as user-defined.
    """
    bp = Blueprint(
        name="bp1",
        groups={
            "leaf": {
                "node_count": 1,
                "attrs": {
                    "some_field": {"nested_key": 111},
                },
            },
        },
        adjacency=[],
    )
    ctx_net = Network()
    ctx = DSLExpansionContext(blueprints={"bp1": bp}, network=ctx_net)

    group_def = {
        "use_blueprint": "bp1",
        "parameters": {
            # Note we override the nested field by referencing 'leaf.attrs.some_field.nested_key'
            "leaf.attrs.some_field.nested_key": 999,
        },
    }
    _expand_group(
        ctx,
        parent_path="Region",
        group_name="Main",
        group_def=group_def,
    )

    # 1 node => "Region/Main/leaf/leaf-1"
    assert len(ctx_net.nodes) == 1
    node_obj = ctx_net.nodes["Region/Main/leaf/leaf-1"]
    # 'some_field' is stored under node_obj.attrs
    assert node_obj.attrs["some_field"]["nested_key"] == 999


def test_link_overrides_repeated():
    """Tests applying multiple link_overrides in sequence => last override wins on conflict."""
    net = Network()
    net.add_node(Node("S1"))
    net.add_node(Node("T1"))
    link = Link("S1", "T1", capacity=5, cost=5, attrs={})
    net.add_link(link)

    network_data = {
        "link_overrides": [
            {
                "source": "S1",
                "target": "T1",
                "link_params": {
                    "capacity": 100,
                    "attrs": {"color": "red"},
                },
            },
            {
                "source": "S1",
                "target": "T1",
                "link_params": {
                    "cost": 999,
                    "attrs": {"color": "blue"},  # overwrites 'red'
                    "risk_groups": ["RGfinal"],
                },
            },
        ]
    }
    _process_link_overrides(net, network_data)
    assert link.capacity == 100
    assert link.cost == 999
    assert link.attrs["color"] == "blue"
    # The second override sets risk_groups => replaces any existing
    assert link.risk_groups == {"RGfinal"}


def test_node_overrides_repeated():
    """Tests multiple node_overrides => last one overwrites shared attrs, merges distinct ones, replaces risk_groups if set."""
    net = Network()
    net.add_node(Node("X", attrs={"existing": "keep"}, risk_groups={"RGold"}))

    network_data = {
        "node_overrides": [
            {
                "path": "X",
                "attrs": {
                    "role": "old_role",
                    "color": "red",
                },
                "risk_groups": ["RGfirst"],
            },
            {
                "path": "X",
                "attrs": {
                    "role": "updated_role",
                    "speed": "fast",
                },
                "risk_groups": ["RGsecond"],
            },
        ]
    }
    _process_node_overrides(net, network_data)
    node_attrs = net.nodes["X"].attrs
    # existing => remains
    assert node_attrs["existing"] == "keep"
    # role => updated_role
    assert node_attrs["role"] == "updated_role"
    # color => from first override, not overwritten by second => still "red"
    assert node_attrs["color"] == "red"
    # speed => from second
    assert node_attrs["speed"] == "fast"

    # risk_groups => replaced by second => RGsecond
    assert net.nodes["X"].risk_groups == {"RGsecond"}


def test_adjacency_no_matching_source_or_target():
    """Tests adjacency expansion where source/target path doesn't match any nodes => skip."""
    scenario_data = {
        "network": {
            "nodes": {"RealNode": {"attrs": {}}},
            "adjacency": [
                {
                    "source": "/MissingSource",
                    "target": "/RealNode",
                    "pattern": "mesh",
                },
                {
                    "source": "/RealNode",
                    "target": "/MissingTarget",
                    "pattern": "mesh",
                },
            ],
        }
    }
    net = expand_network_dsl(scenario_data)
    assert len(net.nodes) == 1
    assert len(net.links) == 0


def test_provide_network_version_and_name():
    """Tests that both 'name' and 'version' in DSL => net.attrs."""
    data = {
        "network": {
            "name": "NetGraphTest",
            "version": "2.0-beta",
        }
    }
    net = expand_network_dsl(data)
    assert net.attrs["name"] == "NetGraphTest"
    assert net.attrs["version"] == "2.0-beta"


def test_expand_adjacency_with_variables_zip():
    """Tests adjacency with expand_vars in 'zip' mode => expansions in lockstep."""
    scenario_data = {
        "network": {
            "groups": {
                "RackA": {"node_count": 1},
                "RackB": {"node_count": 1},
                "RackC": {"node_count": 1},
            },
            "adjacency": [
                {
                    "source": "/Rack{rack_id}",
                    "target": "/Rack{other_rack_id}",
                    "expand_vars": {
                        "rack_id": ["A", "B", "C"],
                        "other_rack_id": ["B", "C", "A"],
                    },
                    "expansion_mode": "zip",
                    "pattern": "mesh",
                    "link_params": {"capacity": 100},
                }
            ],
        }
    }
    net = expand_network_dsl(scenario_data)
    # (A->B), (B->C), (C->A)
    assert len(net.nodes) == 3
    assert len(net.links) == 3
    link_pairs = {(l.source, l.target) for l in net.links.values()}
    expected = {
        ("RackA/RackA-1", "RackB/RackB-1"),
        ("RackB/RackB-1", "RackC/RackC-1"),
        ("RackC/RackC-1", "RackA/RackA-1"),
    }
    assert link_pairs == expected
    for link in net.links.values():
        assert link.capacity == 100


def test_expand_adjacency_with_variables_zip_mismatch():
    """Tests 'zip' mode with mismatched list lengths => ValueError."""
    scenario_data = {
        "network": {
            "groups": {
                "RackA": {"node_count": 1},
                "RackB": {"node_count": 1},
                "RackC": {"node_count": 1},
            },
            "adjacency": [
                {
                    "source": "/Rack{rack_id}",
                    "target": "/Rack{other_rack_id}",
                    "expand_vars": {
                        "rack_id": ["A", "B"],
                        "other_rack_id": ["C", "A", "B"],  # mismatch
                    },
                    "expansion_mode": "zip",
                }
            ],
        }
    }

    with pytest.raises(ValueError) as exc:
        expand_network_dsl(scenario_data)
    assert "zip expansion requires all lists be the same length" in str(exc.value)
