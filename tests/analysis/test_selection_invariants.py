"""Router-only precision conflicts and direct shared-group membership."""

from ngraph import (
    Condition,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    RiskGroup,
    Scenario,
    Selector,
    UnitsSettings,
    failure_cases,
    prepare,
)


def test_finest_range_valid_q_when_only_router_split_conflicts():
    n = Network(
        nodes={k: Node(k) for k in ["A", "D", "X", "Y", *(f"M{i}" for i in range(8))]}
    )
    for i in range(8):
        n.add_link(Link("A", f"M{i}", 64))
        n.add_link(Link(f"M{i}", "D", 64))
    n.add_link(Link("X", "Y", float(2**59)))
    d = DemandSet("d", (DemandSpec(Selector("^A$"), Selector("^D$"), 4),))
    p = prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(precision=0.5)),
        demand_sets=("d",),
    )
    report = p.units_report
    # Eight equal branches: q<=0.5*4/(8-1)=2/7, so power-of-two q<=0.25; directed capacity
    # sum at q=0.25 exceeds2^62, while q=0.5 is range-valid.
    assert report.q == 0.5 and report.target_met is False
    assert any(c.kind == "router" for c in report.binding_constraints)
    assert any(c.kind == "capacity_sum" for c in report.binding_constraints)


def test_shared_group_expansion_uses_direct_not_child_members():
    n = Network(
        nodes={
            "x": Node("x", risk_groups={"P"}, attrs={"kill": True}),
            "y": Node("y", risk_groups={"C"}),
        },
        risk_groups={"P": RiskGroup("P", children=[RiskGroup("C")])},
    )
    policy = FailurePolicy(
        expand_groups=True,
        modes=[FailureMode(1, [FailureRule("node", [Condition("kill", "==", True)])])],
    )
    cases = failure_cases(prepare(Scenario(n)), FailureRequest(policy, 1, seed=1))
    assert cases[1].pattern.excluded_nodes == ("x",)
    assert "y" not in cases[1].pattern.excluded_nodes
