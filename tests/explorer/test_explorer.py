import logging

import pytest

from ngraph.components import Component, ComponentsLibrary
from ngraph.explorer import (
    NetworkExplorer,
)
from ngraph.model.network import Link, Network, Node


def create_mock_components_library() -> ComponentsLibrary:
    """Create a mock ComponentsLibrary containing sample components."""
    lib = ComponentsLibrary()
    # Add a couple of known components for testing cost/power aggregation
    lib.components["known_hw"] = Component(
        name="known_hw",
        capex=10.0,
        power_watts=2.0,
    )
    lib.components["optic_hw"] = Component(
        name="optic_hw",
        capex=5.0,
        power_watts=1.0,
        capacity=100.0,
    )
    return lib


@pytest.fixture
def caplog_info_level():
    """
    Pytest fixture to set the logger level to INFO and capture logs.
    Ensures we can see warning messages in tests.
    """
    logger = logging.getLogger("explorer")
    old_level = logger.level
    logger.setLevel(logging.INFO)
    yield
    logger.setLevel(old_level)


def test_explore_empty_network():
    """Test exploring an empty network (no nodes, no links)."""
    network = Network()
    explorer = NetworkExplorer.explore_network(network)

    assert explorer.root_node is not None
    # Root node with no children, no stats
    assert explorer.root_node.name == "root"
    assert explorer.root_node.subtree_nodes == set()
    assert explorer.root_node.stats.node_count == 0
    assert explorer.root_node.stats.internal_link_count == 0
    assert explorer.root_node.stats.external_link_count == 0
    assert explorer.root_node.stats.total_capex == 0
    assert explorer.root_node.stats.total_power == 0


def test_explore_single_node_no_slash():
    """Test exploring a network with a single node that has no slashes in its name."""
    network = Network()
    network.nodes["nodeA"] = Node(name="nodeA")

    explorer = NetworkExplorer.explore_network(network)
    root = explorer.root_node

    assert root is not None
    assert len(root.children) == 1
    child_node = next(iter(root.children.values()))
    assert child_node.name == "nodeA"
    assert child_node.subtree_nodes == {"nodeA"}
    assert child_node.stats.node_count == 1


def test_explore_single_node_with_slashes():
    """
    Test a single node whose name includes multiple slash segments.
    Should build nested child TreeNodes under 'root'.
    """
    network = Network()
    network.nodes["dc1/plane1/ssw/ssw-1"] = Node(name="dc1/plane1/ssw/ssw-1")

    explorer = NetworkExplorer.explore_network(network)
    root = explorer.root_node

    assert root is not None
    # root -> dc1 -> plane1 -> ssw -> ssw-1
    assert len(root.children) == 1
    dc1_node = root.children["dc1"]
    assert len(dc1_node.children) == 1
    plane1_node = dc1_node.children["plane1"]
    assert len(plane1_node.children) == 1
    ssw_node = plane1_node.children["ssw"]
    assert len(ssw_node.children) == 1
    leaf = ssw_node.children["ssw-1"]

    # Check stats
    assert leaf.subtree_nodes == {"dc1/plane1/ssw/ssw-1"}
    assert leaf.stats.node_count == 1


def test_explore_network_with_links():
    """
    Test a network with multiple nodes and links (internal + external),
    verifying the stats are aggregated correctly.
    """
    # Setup network
    network = Network()

    # Create some nodes
    # "dc1/plane1/ssw-1" and "dc1/plane1/ssw-2" share a common prefix, so they are in the same subtree
    network.nodes["dc1/plane1/ssw-1"] = Node(
        name="dc1/plane1/ssw-1",
        attrs={"hardware": {"component": "known_hw", "count": 1}},
    )
    network.nodes["dc1/plane1/ssw-2"] = Node(name="dc1/plane1/ssw-2")  # no hw component
    # "dc2/plane2/ssw-3" is in a different subtree
    network.nodes["dc2/plane2/ssw-3"] = Node(
        name="dc2/plane2/ssw-3", attrs={"hardware": {"component": "unknown_hw"}}
    )

    # Add links: one internal link (within dc1 subtree), one crossing subtree boundary
    network.links["l1"] = Link(
        source="dc1/plane1/ssw-1",
        target="dc1/plane1/ssw-2",
        capacity=100.0,
        attrs={
            "hardware": {
                "source": {"component": "optic_hw", "count": 1},
                "target": {"component": "optic_hw", "count": 1},
            }
        },
    )
    network.links["l2"] = Link(
        source="dc1/plane1/ssw-1",
        target="dc2/plane2/ssw-3",
        capacity=200.0,
    )

    # Explore
    lib = create_mock_components_library()
    explorer = NetworkExplorer.explore_network(network, components_library=lib)
    root = explorer.root_node
    assert root is not None

    # Validate that the hierarchy is built
    dc1_node = root.children.get("dc1")
    assert dc1_node is not None
    plane1_node = dc1_node.children.get("plane1")
    assert plane1_node is not None
    ssw_1_node = plane1_node.children.get("ssw-1")
    ssw_2_node = plane1_node.children.get("ssw-2")
    assert ssw_1_node is not None
    assert ssw_2_node is not None

    dc2_node = root.children.get("dc2")
    assert dc2_node is not None
    plane2_node = dc2_node.children.get("plane2")
    assert plane2_node is not None
    ssw_3_node = plane2_node.children.get("ssw-3")
    assert ssw_3_node is not None

    # Check aggregated stats for the root
    # By default, from the root's perspective, both links connect nodes in its subtree => both internal
    assert root.stats.node_count == 3
    assert (
        root.stats.internal_link_count == 2
    )  # both links appear as internal at the root
    assert root.stats.internal_link_capacity == 300.0
    assert root.stats.external_link_count == 0
    assert root.stats.external_link_capacity == 0.0
    # Optics on an endpoint contribute only if that endpoint node has hardware.
    # Here only ssw-1 has hardware, so totals are: node (10) + one optic end (5) = 15.
    assert root.stats.total_capex == 15.0
    assert root.stats.total_power == 3.0

    # From dc1's perspective, the link to dc2 is external
    dc1_subtree_node = dc1_node
    assert dc1_subtree_node.stats.external_link_count == 1
    assert "dc2/plane2/ssw-3" in dc1_subtree_node.stats.external_link_details
    assert (
        dc1_subtree_node.stats.external_link_details["dc2/plane2/ssw-3"].link_count == 1
    )
    assert (
        dc1_subtree_node.stats.external_link_details["dc2/plane2/ssw-3"].link_capacity
        == 200.0
    )


def test_unknown_hw_warnings(caplog, caplog_info_level):
    """Test that unknown hw_component on nodes/links triggers a warning."""
    network = Network()
    network.nodes["n1"] = Node(
        name="n1", attrs={"hardware": {"component": "unknown_node_hw"}}
    )
    network.nodes["n2"] = Node(name="n2")
    network.links["l1"] = Link(
        source="n1",
        target="n2",
        attrs={"hardware": {"source": {"component": "unknown_link_hw"}}},
    )

    lib = create_mock_components_library()
    NetworkExplorer.explore_network(network, components_library=lib)

    # The aggregator can visit the same link/node multiple times at different levels,
    # but for our test we only require that at least one unknown-node warning
    # and one unknown-link warning appears in the logs:
    warnings = [r.message for r in caplog.records if r.levelname == "WARNING"]
    assert any("unknown_node_hw" in w for w in warnings)
    assert any("unknown_link_hw" in w for w in warnings)


def test_print_tree_basic(capsys):
    """
    Basic test of print_tree output with skip_leaves=False, detailed=False.
    """
    network = Network()
    network.nodes["n1"] = Node(name="n1")
    network.nodes["n2"] = Node(name="n2")
    explorer = NetworkExplorer.explore_network(network)

    explorer.print_tree()
    captured = capsys.readouterr().out

    # Expect lines for root, n1, n2
    assert "root" in captured
    assert "n1" in captured
    assert "n2" in captured


def test_print_tree_external_breakdown_rollup(capsys):
    """
    Verify external link breakdowns roll up leaf paths when skip_leaves=True and detailed=True.
    Also covers printing of aggregated internal capacity.
    """
    network = Network()
    # dc1 subtree with two leaves
    network.nodes["dc1/plane1/ssw/ssw-1"] = Node(name="dc1/plane1/ssw/ssw-1")
    network.nodes["dc1/plane1/ssw/ssw-2"] = Node(name="dc1/plane1/ssw/ssw-2")
    # dc2 subtree with one leaf
    network.nodes["dc2/plane2/ssw/ssw-3"] = Node(name="dc2/plane2/ssw/ssw-3")

    # Internal link within dc1 subtree and external link to dc2 subtree
    network.links["l_int"] = Link(
        source="dc1/plane1/ssw/ssw-1", target="dc1/plane1/ssw/ssw-2", capacity=123.0
    )
    network.links["l_ext"] = Link(
        source="dc1/plane1/ssw/ssw-1", target="dc2/plane2/ssw/ssw-3", capacity=200.0
    )

    explorer = NetworkExplorer.explore_network(network)
    explorer.print_tree(skip_leaves=True, detailed=True)
    captured = capsys.readouterr().out

    # Leaves should be skipped, their parent path should appear
    assert "ssw/ssw-1" not in captured
    assert "ssw/ssw-2" not in captured
    assert "plane1" in captured

    # Detailed output should include internal capacity aggregation
    assert "IntLinkCap=123.0" in captured

    # External breakdown should roll leaf path "dc2/plane2/ssw/ssw-3" up to "dc2/plane2/ssw"
    assert "External to [dc2/plane2/ssw]: 1 links, cap=200.0" in captured


def test_active_mode_excludes_disabled_nodes_and_links():
    """Validate active_stats omit disabled nodes and disabled links."""
    network = Network()
    # Nodes: a (enabled), b (disabled) in dc1; c (enabled) in dc2
    network.nodes["dc1/a"] = Node(name="dc1/a")
    network.nodes["dc1/b"] = Node(name="dc1/b", attrs={"disabled": True})
    network.nodes["dc2/c"] = Node(name="dc2/c")

    # Links:
    # - l1: internal within dc1 (a-b) -> excluded from active due to b disabled
    # - l2: a -> c external at dc1, included in active
    # - l3: a -> c disabled link, excluded from active
    network.links["l1"] = Link(source="dc1/a", target="dc1/b", capacity=100.0)
    network.links["l2"] = Link(source="dc1/a", target="dc2/c", capacity=200.0)
    network.links["l3"] = Link(
        source="dc1/a", target="dc2/c", capacity=50.0, attrs={"disabled": True}
    )

    explorer = NetworkExplorer.explore_network(network)
    root = explorer.root_node
    assert root is not None

    # Root perspective: all links are internal (entire graph is one subtree at root)
    assert root.stats.node_count == 3
    assert root.active_stats.node_count == 2  # excludes dc1/b

    assert root.stats.internal_link_count == 3  # l1, l2, l3
    assert root.stats.internal_link_capacity == 350.0
    assert root.active_stats.internal_link_count == 1  # only l2
    assert root.active_stats.internal_link_capacity == 200.0

    assert root.stats.external_link_count == 0
    assert root.active_stats.external_link_count == 0

    # dc1 subtree: external links to dc2; active excludes disabled dst/src and disabled link
    dc1 = root.children["dc1"]
    assert dc1.stats.node_count == 2
    assert dc1.active_stats.node_count == 1

    # From dc1 perspective: two external links in 'all', one in 'active'
    assert dc1.stats.external_link_count == 2
    assert dc1.stats.external_link_capacity == 250.0
    assert dc1.active_stats.external_link_count == 1
    assert dc1.active_stats.external_link_capacity == 200.0
