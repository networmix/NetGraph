"""Range/input conflicts and direct shared-group membership."""

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


def test_static_input_bound_and_range_can_both_be_satisfied():
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
    # v_min=4 gives B_in=4; L=12+34=46, Gamma=13.5 and c_min=64
    # give B_split=64/27>2. q=2 fits range as well as both numeric bounds.
    assert report.q == 2 and report.target_met is True
    assert report.limited_by == "split_count" and report.range_limit is None
    assert report.split_bound.count == 27 / 2


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
