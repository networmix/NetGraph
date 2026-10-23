"""Integration tests combining network features with flow analysis."""

import copy

import pytest

from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    RiskGroup,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
)


class TestNetworkIntegration:
    """Network features combined with flow analysis."""

    @pytest.fixture
    def diamond_network(self):
        """Fixture providing a diamond-shaped network A->B,C->D."""
        net = Network()
        for node_name in ["A", "B", "C", "D"]:
            net.add_node(Node(node_name))

        net.add_link(Link("A", "B"))
        net.add_link(Link("A", "C"))
        net.add_link(Link("B", "D"))
        net.add_link(Link("C", "D"))
        return net

    def test_risk_group_with_flow_analysis(self):
        """Disabling an all-node risk group blocks max flow; re-enabling restores it."""
        net = Network()
        nodes = ["A", "B", "C", "D"]
        for node in nodes:
            net.add_node(Node(node, risk_groups={"critical"}))

        net.add_link(Link("A", "B"))
        net.add_link(Link("B", "C"))
        net.add_link(Link("C", "D"))

        net.risk_groups["critical"] = RiskGroup("critical")

        # Risk group enabled: the unit-capacity chain carries 1.0
        source, target = Selector("^A$"), Selector("^D$")
        flow = capacity(
            prepare(Scenario(net, units=UnitsSettings(1))),
            CapacityQuery(source, target, workers=1),
        )
        assert flow.cases[0].states["converged"].rows[0].result.delivered == 1

        # No flow possible when all nodes are disabled - raises error
        net = copy.deepcopy(net)
        net.disable_risk_group("critical")
        with pytest.raises(ValueError, match="capacity.source: empty selection"):
            capacity(
                prepare(Scenario(net, units=UnitsSettings(1))),
                CapacityQuery(source, target, workers=1),
            )

        # Flow should resume when risk group is re-enabled
        net = copy.deepcopy(net)
        net.enable_risk_group("critical")
        flow = capacity(
            prepare(Scenario(net, units=UnitsSettings(1))),
            CapacityQuery(source, target, workers=1),
        )
        assert flow.cases[0].states["converged"].rows[0].result.delivered == 1
