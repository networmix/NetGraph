import pytest
from ngraph.network import (
    Network,
    Node,
    Link,
    RiskGroup,
    new_base64_uuid,
)
from ngraph.lib.graph import StrictMultiDiGraph


def test_new_base64_uuid_length_and_uniqueness():
    """
    Generate two Base64-encoded UUIDs and confirm:
      - they are strings with no '=' padding
      - they are 22 chars long
      - they differ from each other
    """
    uuid1 = new_base64_uuid()
    uuid2 = new_base64_uuid()

    assert isinstance(uuid1, str)
    assert isinstance(uuid2, str)
    assert "=" not in uuid1
    assert "=" not in uuid2

    # 22 characters for a UUID in unpadded Base64
    assert len(uuid1) == 22
    assert len(uuid2) == 22

    # They should be unique
    assert uuid1 != uuid2


def test_node_creation_default_attrs():
    """
    A new Node with no attrs should have an empty dict for attrs.
    """
    node = Node("A")
    assert node.name == "A"
    assert node.attrs == {}
    assert node.risk_groups == set()
    assert node.disabled is False


def test_node_creation_custom_attrs():
    """
    A new Node can be created with custom attributes that are stored as-is.
    """
    custom_attrs = {"key": "value", "number": 42}
    node = Node("B", attrs=custom_attrs)
    assert node.name == "B"
    assert node.attrs == custom_attrs
    assert node.risk_groups == set()
    assert node.disabled is False


def test_link_defaults_and_id_generation():
    """
    A Link without custom parameters should default capacity/cost to 1.0,
    have an empty attrs dict, and generate a unique ID like 'A|B|<uuid>'.
    """
    link = Link("A", "B")

    assert link.capacity == 1.0
    assert link.cost == 1.0
    assert link.attrs == {}
    assert link.risk_groups == set()
    assert link.disabled is False

    # ID should start with 'A|B|' and have a random suffix
    assert link.id.startswith("A|B|")
    assert len(link.id) > len("A|B|")


def test_link_custom_values():
    """
    A Link can be created with custom capacity/cost/attrs,
    and the ID is generated automatically.
    """
    custom_attrs = {"color": "red"}
    link = Link("X", "Y", capacity=2.0, cost=4.0, attrs=custom_attrs)

    assert link.source == "X"
    assert link.target == "Y"
    assert link.capacity == 2.0
    assert link.cost == 4.0
    assert link.attrs == custom_attrs
    assert link.risk_groups == set()
    assert link.disabled is False
    assert link.id.startswith("X|Y|")


def test_link_id_uniqueness():
    """
    Even if two Links have the same source and target, the auto-generated IDs
    should differ because of the random UUID portion.
    """
    link1 = Link("A", "B")
    link2 = Link("A", "B")
    assert link1.id != link2.id


def test_network_add_node_and_link():
    """
    Adding nodes and links to a Network should store them in dictionaries
    keyed by node name and link ID, respectively.
    """
    network = Network()
    node_a = Node("A")
    node_b = Node("B")

    network.add_node(node_a)
    network.add_node(node_b)

    assert "A" in network.nodes
    assert "B" in network.nodes

    link = Link("A", "B")
    network.add_link(link)

    # Link is stored under link.id
    assert link.id in network.links
    assert network.links[link.id] is link


def test_network_add_link_missing_source():
    """
    Attempting to add a Link whose source node is not in the Network should raise an error.
    """
    network = Network()
    node_b = Node("B")
    network.add_node(node_b)

    link = Link("A", "B")  # 'A' doesn't exist

    with pytest.raises(ValueError, match="Source node 'A' not found in network."):
        network.add_link(link)


def test_network_add_link_missing_target():
    """
    Attempting to add a Link whose target node is not in the Network should raise an error.
    """
    network = Network()
    node_a = Node("A")
    network.add_node(node_a)

    link = Link("A", "B")  # 'B' doesn't exist
    with pytest.raises(ValueError, match="Target node 'B' not found in network."):
        network.add_link(link)


def test_network_attrs():
    """
    The Network's 'attrs' dictionary can store arbitrary metadata about the network.
    """
    network = Network(attrs={"network_type": "test"})
    assert network.attrs["network_type"] == "test"


def test_add_duplicate_node_raises_valueerror():
    """
    Adding a second Node with the same name should raise ValueError
    rather than overwriting the existing node.
    """
    network = Network()
    node1 = Node("A", attrs={"data": 1})
    node2 = Node("A", attrs={"data": 2})

    network.add_node(node1)
    with pytest.raises(ValueError, match="Node 'A' already exists in the network."):
        network.add_node(node2)


def test_select_node_groups_by_path():
    """
    Tests select_node_groups_by_path for exact matches, slash-based prefix matches,
    and * prefix pattern, plus capturing groups.
    """
    net = Network()
    # Add some nodes
    net.add_node(Node("SEA/spine/myspine-1"))
    net.add_node(Node("SEA/spine/myspine-2"))
    net.add_node(Node("SEA/leaf1/leaf-1"))
    net.add_node(Node("SEA/leaf1/leaf-2"))
    net.add_node(Node("SEA/leaf2/leaf-1"))
    net.add_node(Node("SEA/leaf2/leaf-2"))
    net.add_node(Node("SEA-other"))
    net.add_node(Node("SFO"))

    # 1) Exact match => "SFO"
    node_groups = net.select_node_groups_by_path("SFO")
    assert len(node_groups) == 1  # Only 1 group
    nodes = node_groups["SFO"]
    assert len(nodes) == 1  # Only 1 node
    assert nodes[0].name == "SFO"

    # 2) Startwith match => "SEA/spine"
    node_groups = net.select_node_groups_by_path("SEA/spine")
    assert len(node_groups) == 1  # Only 1 group
    nodes = node_groups["SEA/spine"]
    assert len(nodes) == 2  # 2 nodes
    found = {n.name for n in nodes}
    assert found == {"SEA/spine/myspine-1", "SEA/spine/myspine-2"}

    # 3) * match => "SEA/leaf*"
    node_groups = net.select_node_groups_by_path("SEA/leaf*")
    assert len(node_groups) == 1  # Only 1 group
    nodes = node_groups["SEA/leaf*"]
    assert len(nodes) == 4  # 4 nodes
    found = {n.name for n in nodes}
    assert found == {
        "SEA/leaf1/leaf-1",
        "SEA/leaf1/leaf-2",
        "SEA/leaf2/leaf-1",
        "SEA/leaf2/leaf-2",
    }

    # 4) match with capture => "(SEA/leaf\\d)"
    node_groups = net.select_node_groups_by_path("(SEA/leaf\\d)")
    assert len(node_groups) == 2  # 2 distinct captures
    nodes = node_groups["SEA/leaf1"]
    assert len(nodes) == 2  # 2 nodes
    found = {n.name for n in nodes}
    assert found == {"SEA/leaf1/leaf-1", "SEA/leaf1/leaf-2"}

    nodes = node_groups["SEA/leaf2"]
    assert len(nodes) == 2
    found = {n.name for n in nodes}
    assert found == {"SEA/leaf2/leaf-1", "SEA/leaf2/leaf-2"}


def test_to_strict_multidigraph_add_reverse_true():
    """
    Tests to_strict_multidigraph with add_reverse=True, ensuring
    that both forward and reverse edges are added.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))

    link_ab = Link("A", "B")
    link_bc = Link("B", "C")
    net.add_link(link_ab)
    net.add_link(link_bc)

    graph = net.to_strict_multidigraph(add_reverse=True)

    # Check nodes
    assert set(graph.nodes()) == {"A", "B", "C"}

    # Each link adds two edges (forward + reverse)
    edges = list(graph.edges(keys=True))
    forward_keys = {link_ab.id, link_bc.id}
    reverse_keys = {f"{link_ab.id}_rev", f"{link_bc.id}_rev"}
    all_keys = forward_keys.union(reverse_keys)
    found_keys = {e[2] for e in edges}

    assert found_keys == all_keys


def test_to_strict_multidigraph_add_reverse_false():
    """
    Tests to_strict_multidigraph with add_reverse=False, ensuring
    that only forward edges are added.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))

    link_ab = Link("A", "B")
    net.add_link(link_ab)

    graph = net.to_strict_multidigraph(add_reverse=False)

    # Check nodes
    assert set(graph.nodes()) == {"A", "B"}

    # Only one forward edge should exist
    edges = list(graph.edges(keys=True))
    assert len(edges) == 1
    assert edges[0][0] == "A"
    assert edges[0][1] == "B"
    assert edges[0][2] == link_ab.id


def test_max_flow_simple():
    """
    Tests a simple chain A -> B -> C to verify the max_flow calculation.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))

    # Add links with capacities
    net.add_link(Link("A", "B", capacity=5))
    net.add_link(Link("B", "C", capacity=3))

    # Max flow from A to C is limited by the smallest capacity (3)
    flow_value = net.max_flow("A", "C")
    assert flow_value == {("A", "C"): 3.0}


def test_max_flow_multi_parallel():
    """
    Tests a scenario where two parallel paths can carry flow.
    A -> B -> C and A -> D -> C, each with capacity=5.
    The total flow A->C should be 10.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("D"))

    net.add_link(Link("A", "B", capacity=5))
    net.add_link(Link("B", "C", capacity=5))
    net.add_link(Link("A", "D", capacity=5))
    net.add_link(Link("D", "C", capacity=5))

    flow_value = net.max_flow("A", "C")
    assert flow_value == {("A", "C"): 10.0}


def test_max_flow_no_source():
    """
    If no node in the network matches the source path, it should raise ValueError.
    """
    net = Network()
    # Add only "B" and "C" nodes, no "A".
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_link(Link("B", "C", capacity=10))

    with pytest.raises(ValueError, match="No source nodes found matching 'A'"):
        net.max_flow("A", "C")


def test_max_flow_no_sink():
    """
    If no node in the network matches the sink path, it should raise ValueError.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=10))

    with pytest.raises(ValueError, match="No sink nodes found matching 'C'"):
        net.max_flow("A", "C")


def test_max_flow_combine_empty():
    """
    Demonstrate that if the dictionary for sinks is not empty, but
    all matched sink nodes are disabled, the final combined_snk_nodes is empty
    => returns 0.0 (rather than raising ValueError).
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("Z", disabled=True))  # disabled => but recognized by ^(A|Z)$
    net.add_node(Node("C", disabled=True))
    net.add_node(Node("Y", disabled=True))

    flow_vals = net.max_flow("^(A|Z)$", "^(C|Y)$", mode="combine")
    assert flow_vals == {("A|Z", "C|Y"): 0.0}


def test_max_flow_pairwise_some_empty():
    """
    In 'pairwise' mode, we want distinct groups to appear in the result,
    even if one group is fully disabled.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))
    net.add_node(Node("Z", disabled=True))

    # A->B->C
    net.add_link(Link("A", "B", capacity=5))
    net.add_link(Link("B", "C", capacity=3))

    flow_vals = net.max_flow("^(A|B)$", "^(C|Z)$", mode="pairwise")
    assert flow_vals == {
        ("A", "C"): 3.0,
        ("A", "Z"): 0.0,
        ("B", "C"): 3.0,
        ("B", "Z"): 0.0,
    }


def test_max_flow_invalid_mode():
    """
    Passing an invalid mode should raise ValueError.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    with pytest.raises(ValueError, match="Invalid mode 'foobar'"):
        net.max_flow("A", "B", mode="foobar")


def test_compute_flow_single_group_empty_source_or_sink():
    """
    Directly tests _compute_flow_single_group returning 0.0 if sources or sinks is empty.
    """
    net = Network()
    # Minimal setup
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B", capacity=5))

    flow_val_empty_sources = net._compute_flow_single_group(
        [], [Node("B")], False, None
    )
    assert flow_val_empty_sources == 0.0

    flow_val_empty_sinks = net._compute_flow_single_group([Node("A")], [], False, None)
    assert flow_val_empty_sinks == 0.0


def test_disable_enable_node():
    """
    Tests disabling and enabling a single node.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_link(Link("A", "B"))

    # Initially, nothing is disabled
    assert net.nodes["A"].disabled is False
    assert net.nodes["B"].disabled is False

    net.disable_node("A")
    assert net.nodes["A"].disabled is True
    assert net.nodes["B"].disabled is False

    # Re-enable
    net.enable_node("A")
    assert net.nodes["A"].disabled is False


def test_disable_node_does_not_exist():
    """
    Tests that disabling/enabling a non-existent node raises ValueError.
    """
    net = Network()
    with pytest.raises(ValueError, match="Node 'A' does not exist."):
        net.disable_node("A")

    with pytest.raises(ValueError, match="Node 'B' does not exist."):
        net.enable_node("B")


def test_disable_enable_link():
    """
    Tests disabling and enabling a single link.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    link = Link("A", "B")
    net.add_link(link)

    assert net.links[link.id].disabled is False

    net.disable_link(link.id)
    assert net.links[link.id].disabled is True

    net.enable_link(link.id)
    assert net.links[link.id].disabled is False


def test_disable_link_does_not_exist():
    """
    Tests that disabling/enabling a non-existent link raises ValueError.
    """
    net = Network()
    with pytest.raises(ValueError, match="Link 'xyz' does not exist."):
        net.disable_link("xyz")
    with pytest.raises(ValueError, match="Link 'xyz' does not exist."):
        net.enable_link("xyz")


def test_enable_all_disable_all():
    """
    Ensures that enable_all and disable_all correctly toggle
    all nodes and links in the network.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    link = Link("A", "B")
    net.add_link(link)

    # Everything enabled by default
    assert net.nodes["A"].disabled is False
    assert net.nodes["B"].disabled is False
    assert net.links[link.id].disabled is False

    # Disable all
    net.disable_all()
    assert net.nodes["A"].disabled is True
    assert net.nodes["B"].disabled is True
    assert net.links[link.id].disabled is True

    # Enable all
    net.enable_all()
    assert net.nodes["A"].disabled is False
    assert net.nodes["B"].disabled is False
    assert net.links[link.id].disabled is False


def test_to_strict_multidigraph_excludes_disabled():
    """
    Disabled nodes or links should not appear in the final StrictMultiDiGraph.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    link_ab = Link("A", "B")
    net.add_link(link_ab)

    # Disable node A
    net.disable_node("A")
    graph = net.to_strict_multidigraph()
    # Node A and link A->B should not appear
    assert "A" not in graph.nodes
    # B is still there
    assert "B" in graph.nodes
    # No edges in the graph because A is disabled
    assert len(graph.edges()) == 0

    # Enable node A, disable link
    net.enable_all()
    net.disable_link(link_ab.id)
    graph = net.to_strict_multidigraph()
    # Nodes A and B appear now, but no edges because the link is disabled
    assert "A" in graph.nodes
    assert "B" in graph.nodes
    assert len(graph.edges()) == 0


def test_get_links_between():
    """
    Tests retrieving all links that connect a specific source to a target.
    """
    net = Network()
    net.add_node(Node("A"))
    net.add_node(Node("B"))
    net.add_node(Node("C"))

    link_ab1 = Link("A", "B")
    link_ab2 = Link("A", "B")
    link_bc = Link("B", "C")
    net.add_link(link_ab1)
    net.add_link(link_ab2)
    net.add_link(link_bc)

    # Two links from A->B
    ab_links = net.get_links_between("A", "B")
    assert len(ab_links) == 2
    assert set(ab_links) == {link_ab1.id, link_ab2.id}

    # One link from B->C
    bc_links = net.get_links_between("B", "C")
    assert len(bc_links) == 1
    assert bc_links[0] == link_bc.id

    # None from B->A
    ba_links = net.get_links_between("B", "A")
    assert ba_links == []


def test_find_links():
    """
    Tests finding links by optional source_regex, target_regex,
    and the any_direction parameter.
    """
    net = Network()
    net.add_node(Node("srcA"))
    net.add_node(Node("srcB"))
    net.add_node(Node("C"))
    link_a_c = Link("srcA", "C")
    link_b_c = Link("srcB", "C")
    net.add_link(link_a_c)
    net.add_link(link_b_c)

    # No filter => returns all
    all_links = net.find_links()
    assert len(all_links) == 2
    assert set(l.id for l in all_links) == {link_a_c.id, link_b_c.id}

    # Filter by source pattern "srcA"
    a_links = net.find_links(source_regex="^srcA$")
    assert len(a_links) == 1
    assert a_links[0].id == link_a_c.id

    # Filter by target pattern "C"
    c_links = net.find_links(target_regex="^C$")
    assert len(c_links) == 2

    # Combined filter that picks only link from "srcB" -> "C"
    b_links = net.find_links(source_regex="srcB", target_regex="^C$")
    assert len(b_links) == 1
    assert b_links[0].id == link_b_c.id


#
# New tests to improve coverage for RiskGroup-related methods.
#
def test_disable_risk_group_nonexistent():
    """
    If we call disable_risk_group on a name that is not in net.risk_groups,
    it should do nothing (not raise an error).
    """
    net = Network()
    # no risk groups at all
    net.disable_risk_group("nonexistent_group")  # Should not raise


def test_enable_risk_group_nonexistent():
    """
    If we call enable_risk_group on a name that is not in net.risk_groups,
    it should do nothing (not raise an error).
    """
    net = Network()
    # no risk groups at all
    net.enable_risk_group("nonexistent_group")  # Should not raise


def test_disable_risk_group_recursive():
    """
    Tests disabling a top-level group with recursive=True
    which should also disable child subgroups.
    """
    net = Network()

    # Set up nodes/links
    net.add_node(Node("A", risk_groups={"top"}))
    net.add_node(Node("B", risk_groups={"child1"}))
    net.add_node(Node("C", risk_groups={"child2"}))
    link = Link("A", "C", risk_groups={"child2"})
    net.add_link(link)

    # Add risk groups: "top" with children => child1, child2
    net.risk_groups["top"] = RiskGroup(
        "top", children=[RiskGroup("child1"), RiskGroup("child2")]
    )

    # By default, all are enabled
    assert net.nodes["A"].disabled is False
    assert net.nodes["B"].disabled is False
    assert net.nodes["C"].disabled is False
    assert net.links[link.id].disabled is False

    # Disable top group recursively
    net.disable_risk_group("top", recursive=True)

    # A is in "top", B in "child1", C/link in "child2" => all disabled
    assert net.nodes["A"].disabled is True
    assert net.nodes["B"].disabled is True
    assert net.nodes["C"].disabled is True
    assert net.links[link.id].disabled is True


def test_disable_risk_group_non_recursive():
    """
    Tests disabling a top-level group with recursive=False
    which should NOT disable child subgroups.
    """
    net = Network()
    net.add_node(Node("A", risk_groups={"top"}))
    net.add_node(Node("B", risk_groups={"child1"}))
    net.add_node(Node("C", risk_groups={"child2"}))

    net.risk_groups["top"] = RiskGroup(
        "top", children=[RiskGroup("child1"), RiskGroup("child2")]
    )

    # Disable top group, but do NOT recurse
    net.disable_risk_group("top", recursive=False)

    # A is in "top" => disabled
    # B is in "child1" => still enabled
    # C is in "child2" => still enabled
    assert net.nodes["A"].disabled is True
    assert net.nodes["B"].disabled is False
    assert net.nodes["C"].disabled is False


def test_enable_risk_group_multi_membership():
    """
    A node belongs to multiple risk groups. Disabling one group
    will disable that node, but enabling a different group that
    also includes that node should re-enable it.
    """
    net = Network()

    # Node X belongs to "group1" and "group2"
    net.add_node(Node("X", risk_groups={"group1", "group2"}))
    # Add risk groups
    net.risk_groups["group1"] = RiskGroup("group1")
    net.risk_groups["group2"] = RiskGroup("group2")

    # Initially enabled
    assert net.nodes["X"].disabled is False

    # Disable group1 => X disabled
    net.disable_risk_group("group1")
    assert net.nodes["X"].disabled is True

    # Enable group2 => X re-enabled because it's in "group2" also
    net.enable_risk_group("group2")
    assert net.nodes["X"].disabled is False
