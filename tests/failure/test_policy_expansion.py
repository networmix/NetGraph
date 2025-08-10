"""Tests for FailurePolicy expansion by shared risk groups and children."""

from __future__ import annotations

from ngraph.failure.policy import FailureCondition, FailurePolicy, FailureRule


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
        entity_scope="node",
        conditions=[
            FailureCondition(attr="risk_groups", operator="contains", value="rg1")
        ],
        logic="and",
        rule_type="all",
    )

    from ngraph.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[rule])], fail_risk_groups=True
    )
    failed = set(policy.apply_failures(nodes, links))

    # Both N1 and L1 should be included due to shared risk group; N2/L2 unaffected
    assert {"N1", "L1"}.issubset(failed)
    assert "N2" not in failed and "L2" not in failed


def test_expand_failed_risk_group_children() -> None:
    """Failing a parent risk group should also fail its children when enabled."""
    # No nodes/links needed here; we validate risk_group expansion output itself
    nodes: dict[str, dict] = {}
    links: dict[str, dict] = {}

    # Rule selects top-level risk group name directly via risk_group scope
    rule = FailureRule(
        entity_scope="risk_group",
        conditions=[FailureCondition(attr="name", operator="==", value="parent")],
        logic="and",
        rule_type="all",
    )
    from ngraph.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[FailureMode(weight=1.0, rules=[rule])], fail_risk_group_children=True
    )

    # Risk group hierarchy as dicts (the policy supports dict objects for groups)
    risk_groups = {
        "parent": {"name": "parent", "children": [{"name": "child1", "children": []}]},
        "child1": {"name": "child1", "children": [{"name": "grand", "children": []}]},
        "grand": {"name": "grand", "children": []},
    }

    failed = policy.apply_failures(nodes, links, network_risk_groups=risk_groups)
    # Should include parent, child1, and grand due to recursive expansion
    assert set(failed) == {"parent", "child1", "grand"}
