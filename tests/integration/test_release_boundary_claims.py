"""Release notes describe observable equal-source and nested-group behavior."""

import netgraph_core as core
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    Network,
    Node,
    PlacementQuery,
    RiskGroup,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    place,
    prepare,
)


@pytest.mark.parametrize("q", [1, 1 / 1024])
@pytest.mark.parametrize("caps,units", [((5, 0), 1), ((0, 5), 0), ((5, 5), None)])
def test_equal_sources_report_only_the_traffic_their_shares_carry(q, caps, units):
    n = Network(nodes={s: Node(s) for s in ("a", "b", "t")})
    for s, cap in zip(("a", "b"), caps, strict=True):
        n.add_link(Link(s, "t", cap))
    model = core.FlowPolicyConfig(routing=core.ShortestPaths())
    d = DemandSet("d", (DemandSpec(Selector("a|b"), Selector("t"), 10, model),))
    p = prepare(
        Scenario(n, demand_sets={"d": d}, units=UnitsSettings(q)), demand_sets=("d",)
    )
    row = (
        place(p, PlacementQuery(p.demand_sets["d"], workers=1))
        .cases[0]
        .states["converged"]
        .rows[0]
    )
    # Ordered RR: first sender gets ceil(I/2), second gets floor(I/2).
    assert row.result.delivered == (int(10 / q) if units is None else units)
    assert row.result.delivered * q <= sum(caps)


@pytest.mark.parametrize("scope", ["node", "link"])
@pytest.mark.parametrize("failed", ["child", "parent"])
def test_child_only_group_references_participate_in_ancestor_failures(scope, failed):
    n = Network(
        nodes={
            "a": Node("a", risk_groups={"child"} if scope == "node" else ()),
            "t": Node("t"),
        },
        risk_groups={"parent": RiskGroup("parent", children=(RiskGroup("child"),))},
    )
    n.add_link(Link("a", "t", 10, risk_groups={"child"} if scope == "link" else ()))
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    failures = FailureRequest(
        FailurePolicy(
            modes=(FailureMode(1, (FailureRule("risk_group", path=f"^{failed}$"),)),)
        ),
        1,
        1,
    )
    answer = capacity(
        p, CapacityQuery(Selector("a"), Selector("t"), failures=failures, workers=1)
    )
    assert [c.states["converged"].rows[0].result.delivered for c in answer.cases] == [
        10,
        0,
    ]


def test_documented_numeric_string_ordering_and_equality_examples():
    import re

    from ngraph import Condition
    from ngraph.model.selectors.conditions import evaluate_condition
    from tests.docs.pages import stated

    for op in (">", "=="):
        left, right, expected = stated(
            "docs/reference/dsl.md",
            rf'`"(\d+)" {re.escape(op)} (\d+)`\s+\w+\s+(true|false)',
        )
        assert evaluate_condition({"x": left}, Condition("x", op, int(right))) is (
            expected == "true"
        )
