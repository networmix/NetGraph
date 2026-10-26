"""Selection compares JSON numbers without losing wide integer information."""

import pytest

from ngraph import (
    CapacityQuery,
    Condition,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    Link,
    MatchSpec,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
    resolve_demands,
)
from ngraph.model.selectors import select_nodes
from ngraph.model.selectors.conditions import evaluate_condition


@pytest.mark.parametrize(
    "left,right,answers",
    [
        (10**309, 0, (False, False, True, True)),
        (-(10**309), 0, (True, True, False, False)),
        (10**309, 10**309, (False, True, False, True)),
        (2**53 + 1, float(2**53), (False, False, True, True)),
        (2**53, 2**53 + 1, (True, True, False, False)),
        (1.5, 2, (True, True, False, False)),
        ("10", 5, (False, False, True, True)),
        ("word", 5, (False, False, False, False)),
        (None, 5, (False, False, False, False)),
    ],
)
def test_ordering_keeps_integer_precision_and_numeric_string_coercion(
    left, right, answers
):
    for op, answer in zip(("<", "<=", ">", ">="), answers, strict=True):
        assert evaluate_condition({"x": left}, Condition("x", op, right)) is answer


@pytest.mark.parametrize(
    "value,selected", [(10**309, True), (3, True), (-(10**309), False), (0, False)]
)
def test_wide_numbers_follow_demand_membership_and_failure_paths(value, selected):
    condition = Condition("x", ">", 0)
    source = Selector(match=MatchSpec((condition,)))
    n = Network(nodes={"a": Node("a", attrs={"x": value}), "t": Node("t")})
    n.add_link(Link("a", "t", 10))
    assert select_nodes(n, source, True) == (
        {"_all_": [n.nodes["a"]]} if selected else {}
    )
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    demands = resolve_demands(
        p, DemandSet("d", (DemandSpec(source, Selector("t"), 1),))
    )
    assert bool(demands.demands) is selected
    failure = FailureRequest(
        FailurePolicy(
            modes=(FailureMode(1, (FailureRule("node", conditions=(condition,)),)),)
        ),
        1,
        1,
    )
    result = capacity(
        p, CapacityQuery(Selector("a"), Selector("t"), failures=failure, workers=1)
    )
    assert result.cases[-1].case.pattern.excluded_nodes == (("a",) if selected else ())
    assert result.cases[-1].states["converged"].rows[0].result.delivered == (
        0 if selected else 10
    )
    scenario = Scenario.from_yaml(f"""
network:
  nodes:
    a: {{attrs: {{x: {value}}}}}
    t: {{}}
risk_groups:
  - name: positive
    membership:
      scope: node
      path: '^a$'
      match:
        conditions: [{{attr: x, op: '>', value: 0}}]
""")
    assert ("positive" in scenario.network.nodes["a"].risk_groups) is selected


@pytest.mark.parametrize("weight", [10**309, "1e400", 3, 0])
def test_attribute_choice_weights_refuse_float_overflow_with_rule_and_entity(weight):
    n = Network(nodes={"a": Node("a", attrs={"weight": weight}), "t": Node("t")})
    n.add_link(Link("a", "t", 10))
    p = prepare(Scenario(n, units=UnitsSettings(1)))
    request = FailureRequest(
        FailurePolicy(
            modes=(
                FailureMode(
                    1,
                    (
                        FailureRule(
                            "node",
                            path="^a$",
                            mode="choice",
                            count=1,
                            weight_by="weight",
                        ),
                    ),
                ),
            )
        ),
        1,
        1,
    )
    query = CapacityQuery(Selector("a"), Selector("t"), failures=request, workers=1)
    if weight in (10**309, "1e400"):
        with pytest.raises(
            ValueError, match="failure mode 0 rule 0: nonfinite weight for a"
        ):
            capacity(p, query)
    else:
        answer = capacity(p, query)
        # A count-one choice fills from zero-weight candidates when no positive
        # candidate exists; the sole candidate is still chosen.
        assert answer.cases[-1].case.pattern.excluded_nodes == ("a",)
        assert answer.cases[-1].states["converged"].rows[0].result.delivered == 0
