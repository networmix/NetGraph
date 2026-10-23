"""Independent hierarchy, editing and typed-namespace witnesses."""

import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import MembershipIndex, RiskGroup


def hierarchy():
    leaf = RiskGroup("leaf")
    child = RiskGroup("child", children=[leaf])
    root = RiskGroup("root", children=[child])
    network = Network(risk_groups={"root": root, "other": RiskGroup("other")})
    network.add_node(Node("direct", risk_groups={"root"}))
    network.add_node(Node("nested", risk_groups={"leaf", "other"}))
    network.add_node(Node("end"))
    link = Link("direct", "end", risk_groups={"child"})
    network.add_link(link)
    return network, link


def test_unregistered_descendants_and_direct_membership():
    network, link = hierarchy()
    index = MembershipIndex.build(network)
    assert index.members("root", False).nodes == {"direct"}
    assert index.members("root", False).links == set()
    assert index.members("root").nodes == {"direct", "nested"}
    assert index.members("root").links == {link.id}
    assert index.members("child").nodes == {"nested"}
    assert index.members("leaf").links == set()
    with pytest.raises(ValueError, match="unknown risk group absent"):
        index.members("absent")
    with pytest.raises(TypeError):
        index.direct["root"] = index.direct["leaf"]


def test_mutations_resolve_current_membership_and_preserve_direct_enable():
    network, link = hierarchy()
    network.disable_risk_group("root", recursive=False)
    assert network.nodes["direct"].disabled
    assert not network.nodes["nested"].disabled
    assert not network.links[link.id].disabled
    network.disable_risk_group("root")
    assert network.nodes["nested"].disabled
    assert network.links[link.id].disabled
    network.disable_risk_group("other")
    network.enable_risk_group("root")
    assert not any(node.disabled for node in network.nodes.values())
    assert not network.links[link.id].disabled
    # Editable data has no cache generation: a later call sees this change.
    network.replace_node("end", risk_groups={"leaf"})
    network.disable_risk_group("root")
    assert network.nodes["end"].disabled
    before = [node.disabled for node in network.nodes.values()]
    network.enable_risk_group("unknown")
    assert [node.disabled for node in network.nodes.values()] == before


def test_snapshot_does_not_borrow_editable_member_sets():
    network, _ = hierarchy()
    index = MembershipIndex.build(network)
    network.replace_node("nested", risk_groups=())
    assert index.members("root").nodes == {"direct", "nested"}
    assert MembershipIndex.build(network).members("root").nodes == {"direct"}


def test_cycles_reach_unregistered_descendants():
    network, _ = hierarchy()
    # A descendant named like a registered group refers to that declaration.
    back = RiskGroup(
        "child", children=[RiskGroup("leaf", children=[RiskGroup("root")])]
    )
    network.risk_groups["root"] = RiskGroup("root", children=[back])
    with pytest.raises(ValueError, match="root -> child -> leaf -> root"):
        MembershipIndex.build(network)
    network.risk_groups["root"] = RiskGroup(
        "root", children=[RiskGroup("child", children=[RiskGroup("leaf")])]
    )
    assert "nested" in MembershipIndex.build(network).members("root").nodes


def test_unknown_reference_is_labelled_with_legal_control():
    network, _ = hierarchy()
    network.replace_node("end", risk_groups={"typo"})
    with pytest.raises(ValueError, match="Node 'end': unknown risk groups.*typo"):
        MembershipIndex.build(network)
    network.replace_node("end", risk_groups=())
    assert MembershipIndex.build(network).members("root").nodes == {"direct", "nested"}


def test_node_and_link_identifiers_do_not_alias_in_shared_expansion():
    network, link = hierarchy()
    network.add_node(Node(link.id, risk_groups={"other"}))
    index = MembershipIndex.build(network)
    # The node named like a link fails the other group's node, not that link.
    members = index.expand({link.id}, set(), set(), shared=True)
    assert members.nodes == {link.id, "nested"}
    assert members.links == set()
    # An explicitly failed root always cascades through its descendants.
    members = index.expand(set(), set(), {"root"}, shared=False)
    assert members.nodes == {"direct", "nested"}
    assert members.links == {link.id}


def test_identical_inline_declarations_resolve_once():
    first = RiskGroup("room", children=[RiskGroup("leaf")], attrs={"labels": ["same"]})
    second = RiskGroup("room", children=[RiskGroup("leaf")], attrs={"labels": ["same"]})
    network = Network(
        risk_groups={
            "a": RiskGroup("a", children=[first]),
            "b": RiskGroup("b", children=[second]),
        }
    )
    network.add_node(Node("member", risk_groups={"leaf"}))
    index = MembershipIndex.build(network)
    assert tuple(index.groups) == ("a", "room", "leaf", "b")
    assert index.groups["room"] is first
    assert index.members("a").nodes == index.members("b").nodes == {"member"}


@pytest.mark.parametrize("difference", ["attrs", "disabled", "children", "membership"])
def test_conflicting_inline_declarations_name_both_parent_paths(difference):
    first = RiskGroup("room")
    second = RiskGroup(
        "room",
        **{
            "attrs": {"attrs": {"label": ["different"]}},
            "disabled": {"disabled": True},
            "children": {"children": [RiskGroup("nested")]},
            "membership": {"_membership_raw": {"scope": "node", "path": "^member$"}},
        }[difference],
    )
    network = Network(
        risk_groups={
            "a": RiskGroup("a", children=[first]),
            "b": RiskGroup("b", children=[second]),
        }
    )
    with pytest.raises(
        ValueError,
        match="room: conflicting inline declarations at a -> room and b -> room",
    ):
        MembershipIndex.build(network)
    network.risk_groups["b"] = RiskGroup("b", children=[RiskGroup("room")])
    assert MembershipIndex.build(network).members("a") == MembershipIndex.build(
        network
    ).members("b")


def test_registered_declaration_overrides_conflicting_inline_definitions():
    registered = RiskGroup(
        "room", children=[RiskGroup("leaf")], attrs={"authoritative": True}
    )
    network = Network(
        risk_groups={
            "a": RiskGroup(
                "a", children=[RiskGroup("room", disabled=True, attrs={"inline": 1})]
            ),
            "b": RiskGroup(
                "b", children=[RiskGroup("room", children=[RiskGroup("ignored")])]
            ),
            "room": registered,
        }
    )
    network.add_node(Node("member", risk_groups={"leaf"}))
    index = MembershipIndex.build(network)
    assert index.groups["room"] is registered
    assert index.groups["room"].attrs == {"authoritative": True}
    assert not index.groups["room"].disabled and "ignored" not in index.groups
    assert index.members("a").nodes == index.members("b").nodes == {"member"}
