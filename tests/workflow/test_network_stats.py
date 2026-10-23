import pytest

from ngraph.model.network import Link, Network, Node
from ngraph.scenario import Scenario, prepare, run
from ngraph.workflow.network_stats import NetworkStats


@pytest.fixture
def mock_scenario():
    scenario = Scenario(Network())

    scenario.network.add_node(Node("A"))
    scenario.network.add_node(Node("B"))
    scenario.network.add_node(Node("C"))

    scenario.network.add_link(Link("A", "B", capacity=10, cost=2.0))
    scenario.network.add_link(Link("A", "C", capacity=5, cost=4.0))
    scenario.network.add_link(Link("C", "A", capacity=7, cost=3.0))
    return scenario


@pytest.fixture
def mock_scenario_with_disabled():
    """Scenario with disabled nodes and links for testing include_disabled parameter."""
    scenario = Scenario(Network())

    # Add nodes - some enabled, some disabled
    scenario.network.add_node(Node("A"))  # enabled
    scenario.network.add_node(Node("B"))  # enabled
    scenario.network.add_node(Node("C", disabled=True))  # disabled
    scenario.network.add_node(Node("D"))  # enabled

    # Add links - some enabled, some disabled
    scenario.network.add_link(Link("A", "B", capacity=10, cost=2.0))  # enabled
    scenario.network.add_link(
        Link("A", "C", capacity=5, cost=4.0)
    )  # enabled (to disabled node)
    scenario.network.add_link(
        Link("C", "A", capacity=7, cost=3.0)
    )  # enabled (from disabled node)
    scenario.network.add_link(
        Link("B", "D", capacity=15, cost=6.0, disabled=True)
    )  # disabled
    scenario.network.add_link(Link("D", "B", capacity=20, cost=1.0))  # enabled
    return scenario


def test_network_stats_collects_statistics(mock_scenario):
    step = NetworkStats(name="stats")

    data = run(prepare(Scenario(mock_scenario.network, (step,)))).steps[0].result

    # Node statistics
    assert data.node_count == 3

    # Link statistics
    assert data.link_count == 3
    assert data.total_capacity == 22.0  # 10 + 5 + 7
    assert data.mean_capacity == pytest.approx(22.0 / 3)
    assert data.min_capacity == 5.0
    assert data.max_capacity == 10.0

    # Positive integer cost fixture:2,4,3.
    assert data.mean_cost == pytest.approx((2.0 + 4.0 + 3.0) / 3)
    assert data.min_cost == 2.0
    assert data.max_cost == 4.0

    # Degree statistics should be present
    assert isinstance(data.mean_degree, float)
    assert isinstance(data.min_degree, float)
    assert isinstance(data.max_degree, float)


def test_network_stats_excludes_disabled_by_default(mock_scenario_with_disabled):
    """Test that disabled nodes and links are excluded by default."""
    step = NetworkStats(name="stats")

    data = (
        run(prepare(Scenario(mock_scenario_with_disabled.network, (step,))))
        .steps[0]
        .result
    )

    # Should exclude disabled node C and disabled link B->D
    assert data.node_count == 3  # A, B, D (excluding C)
    assert data.link_count == 2  # A->B and D->B are enabled and between enabled nodes

    # Link statistics (A->B with capacity 10, D->B with capacity 20)
    assert data.total_capacity == 30.0  # 10 + 20
    assert data.mean_capacity == 15.0  # (10 + 20) / 2
    assert data.min_capacity == 10.0
    assert data.max_capacity == 20.0

    # Cost statistics: enabled A->B cost2 and D->B cost1.
    assert data.mean_cost == 1.5  # (2 + 1) / 2
    assert data.min_cost == 1.0
    assert data.max_cost == 2.0


def test_network_stats_includes_disabled_when_enabled(mock_scenario_with_disabled):
    """Test that disabled nodes and links are included when include_disabled=True."""
    step = NetworkStats(name="stats", include_disabled=True)

    data = (
        run(prepare(Scenario(mock_scenario_with_disabled.network, (step,))))
        .steps[0]
        .result
    )

    # Should include all nodes and links
    assert data.node_count == 4  # A, B, C, D
    assert data.link_count == 5  # All 5 links

    # Link statistics (all links: 10, 5, 7, 15, 20)
    assert data.total_capacity == 57.0  # 10 + 5 + 7 + 15 + 20
    assert data.mean_capacity == pytest.approx(57.0 / 5)
    assert data.min_capacity == 5.0
    assert data.max_capacity == 20.0

    # Cost statistics: costs2,4,3,6,1.
    assert data.mean_cost == pytest.approx((2.0 + 4.0 + 3.0 + 6.0 + 1.0) / 5)
    assert data.min_cost == 1.0
    assert data.max_cost == 6.0


def test_network_stats_with_exclusions(mock_scenario):
    """Test NetworkStats with excluded nodes and links."""
    step = NetworkStats(name="stats", excluded_nodes=["A"], excluded_links=[])

    data = run(prepare(Scenario(mock_scenario.network, (step,)))).steps[0].result

    # Should exclude node A and its links
    assert data.node_count == 2  # B, C (excluding A)
    assert data.link_count == 0  # All links connect to A, so none remain
