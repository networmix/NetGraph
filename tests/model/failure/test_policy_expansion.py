"""Shared membership and explicit group causes use one resolver."""

from dataclasses import replace

from ngraph.model.failure import FailureMode, FailurePolicy, FailureRule
from ngraph.model.network import Link, Network, Node
from ngraph.model.risk import RiskGroup
from ngraph.model.selectors import Condition
from ngraph.scenario import Scenario, prepare
from tests.failure_fixture import draw


def test_expand_by_shared_risk_groups():
    network = Network(risk_groups={"rg1": RiskGroup("rg1")})
    network.add_node(Node("N1", risk_groups={"rg1"}))
    network.add_node(Node("N2"))
    network.add_link(Link("N1", "N2", 10, 3, risk_groups={"rg1"}))
    network.add_link(Link("N1", "N2", 10, 5))
    prepared = prepare(Scenario(network))
    rule = FailureRule("node", [Condition("risk_groups", "contains", "rg1")])
    policy = FailurePolicy(modes=[FailureMode(1, [rule])], expand_groups=True)
    case = draw(prepared, policy, trace=True)
    assert case.pattern.excluded_nodes == ("N1",)
    assert case.pattern.excluded_links == ("N1|N2|0",)
    assert case.trace.expanded_nodes == ()
    assert case.trace.expanded_links == ("N1|N2|0",)
    policy = replace(policy, expand_groups=False)
    assert draw(prepared, policy).pattern.excluded_links == ()


def test_failed_group_cascades_to_members_and_keeps_group_cause_in_trace():
    child = RiskGroup("child")
    network = Network(risk_groups={"parent": RiskGroup("parent", children=[child])})
    network.add_node(Node("nested", risk_groups={"child"}))
    network.add_node(Node("other"))
    network.add_link(Link("nested", "other", 10, 3, risk_groups={"child"}))
    policy = FailurePolicy(
        modes=[
            FailureMode(
                1, [FailureRule("risk_group", [Condition("name", "==", "parent")])]
            )
        ]
    )
    case = draw(prepare(Scenario(network)), policy, trace=True)
    assert case.pattern.excluded_nodes == ("nested",)
    assert case.pattern.excluded_links == ("nested|other|0",)
    assert case.trace.selections[0].scope == "risk_group"
    assert case.trace.selections[0].selected == ("parent",)
