"""Tests for FailurePolicy expansion by shared risk groups."""

from __future__ import annotations

from ngraph.model.failure.policy import FailurePolicy, FailureRule
from ngraph.model.selectors import Condition


def test_expand_by_shared_risk_groups() -> None:
    """Entities sharing a risk group with a failed one should also fail when enabled."""
    # One node and one link share the same risk group label "rg1"
    nodes = {
        "N1": {"risk_groups": {"rg1"}},
        "N2": {"risk_groups": set()},
    }
    links = {
        "L1": {"risk_groups": {"rg1"}},
        "L2": {"risk_groups": set()},
    }

    # Rule fails N1 explicitly
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="risk_groups", op="contains", value="rg1")],
        logic="and",
        mode="all",
    )

    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[rule])], expand_groups=True
    )
    failed = set(policy.apply_failures(nodes, links))

    # Both N1 and L1 should be included due to shared risk group; N2/L2 unaffected
    assert {"N1", "L1"}.issubset(failed)
    assert "N2" not in failed and "L2" not in failed


def test_failed_risk_group_returns_group_name_only() -> None:
    """A risk_group-scoped rule returns the failed group names.

    Cascading a failed parent group to its children is inherent to the
    risk-group hierarchy and happens downstream (in FailureManager), not in
    the policy itself.
    """
    rule = FailureRule(
        scope="risk_group",
        conditions=[Condition(attr="name", op="==", value="parent")],
        logic="and",
        mode="all",
    )
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])])

    risk_groups = {
        "parent": {"name": "parent", "children": ["child1"]},
        "child1": {"name": "child1", "children": []},
    }

    failed = policy.apply_failures({}, {}, network_risk_groups=risk_groups)
    assert failed == ["parent"]


def test_expand_risk_groups_with_prepared_index() -> None:
    """A precomputed risk-group index must yield the same expansion result."""
    nodes = {
        "N1": {"risk_groups": {"rg1"}},
        "N2": {"risk_groups": {"rg2"}},
    }
    links = {
        "L1": {"risk_groups": {"rg1"}},
        "L2": {"risk_groups": set()},
    }
    rule = FailureRule(
        scope="node",
        conditions=[Condition(attr="risk_groups", op="contains", value="rg1")],
        logic="and",
        mode="all",
    )
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[rule])], expand_groups=True
    )

    index = FailurePolicy.build_risk_group_index(nodes, links)
    assert index == {"rg1": {"N1", "L1"}, "rg2": {"N2"}}

    baseline = policy.apply_failures(nodes, links, seed=7)
    with_index = policy.apply_failures(nodes, links, seed=7, prepared_rg_index=index)
    assert with_index == baseline
    assert set(with_index) == {"N1", "L1"}
