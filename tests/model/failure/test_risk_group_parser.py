"""Tests for risk group parsing in ngraph.model.failure.parser.

Focuses on rejection of keys that are silently inert on nested children:
only top-level groups are registered in network.risk_groups, so 'membership',
'disabled', and 'generate' blocks on children must fail fast.
"""

import jsonschema
import pytest

from ngraph.model.failure.parser import build_risk_groups
from ngraph.scenario import Scenario


class TestBuildRiskGroupsChildRejection:
    """Inert keys on child entries are rejected with ValueError."""

    def test_child_membership_rejected(self):
        """A 'membership' block on a child raises instead of being ignored."""
        rg_data = [
            {
                "name": "Parent",
                "children": [
                    {
                        "name": "Child",
                        "membership": {
                            "scope": "node",
                            "match": {
                                "conditions": [
                                    {"attr": "role", "op": "==", "value": "leaf"}
                                ]
                            },
                        },
                    }
                ],
            }
        ]

        with pytest.raises(
            ValueError, match="'membership' rules not allowed in children"
        ):
            build_risk_groups(rg_data)

    def test_child_disabled_rejected(self):
        """A 'disabled' flag on a child raises instead of being ignored."""
        rg_data = [
            {
                "name": "Parent",
                "children": [{"name": "Child", "disabled": True}],
            }
        ]

        with pytest.raises(ValueError, match="'disabled' not allowed in children"):
            build_risk_groups(rg_data)

    def test_child_disabled_false_rejected(self):
        """Even 'disabled: false' on a child is rejected (the key is inert)."""
        rg_data = [
            {
                "name": "Parent",
                "children": [{"name": "Child", "disabled": False}],
            }
        ]

        with pytest.raises(ValueError, match="'disabled' not allowed in children"):
            build_risk_groups(rg_data)

    def test_grandchild_membership_rejected(self):
        """Rejection applies recursively to nested grandchildren."""
        rg_data = [
            {
                "name": "Parent",
                "children": [
                    {
                        "name": "Child",
                        "children": [
                            {
                                "name": "Grandchild",
                                "membership": {
                                    "scope": "link",
                                    "match": {
                                        "conditions": [
                                            {
                                                "attr": "fiber.conduit_id",
                                                "op": "==",
                                                "value": "C1",
                                            }
                                        ]
                                    },
                                },
                            }
                        ],
                    }
                ],
            }
        ]

        with pytest.raises(
            ValueError, match="'membership' rules not allowed in children"
        ):
            build_risk_groups(rg_data)

    def test_child_generate_rejected(self):
        """A 'generate' block on a child raises (existing behavior)."""
        rg_data = [
            {
                "name": "Parent",
                "children": [{"generate": {"scope": "node", "group_by": "site"}}],
            }
        ]

        with pytest.raises(ValueError, match="'generate' blocks not allowed"):
            build_risk_groups(rg_data)

    def test_top_level_membership_and_disabled_still_accepted(self):
        """Top-level entries keep full support for membership and disabled."""
        rg_data = [
            {
                "name": "Parent",
                "disabled": True,
                "membership": {
                    "scope": "node",
                    "match": {
                        "conditions": [{"attr": "role", "op": "==", "value": "leaf"}]
                    },
                },
                "children": [{"name": "Child"}],
            }
        ]

        groups, generate_specs = build_risk_groups(rg_data)

        assert generate_specs == []
        assert len(groups) == 1
        parent = groups[0]
        assert parent.name == "Parent"
        assert parent.disabled is True
        assert parent._membership_raw is not None
        assert [c.name for c in parent.children] == ["Child"]

    def test_plain_children_still_accepted(self):
        """Children without inert keys parse unchanged."""
        rg_data = [
            {
                "name": "Parent",
                "children": [
                    {"name": "Child[1-2]", "attrs": {"tier": "conduit"}},
                    "ChildShorthand",
                ],
            }
        ]

        groups, _ = build_risk_groups(rg_data)
        child_names = [c.name for c in groups[0].children]
        assert child_names == ["Child1", "Child2", "ChildShorthand"]


class TestScenarioChildMembershipRejection:
    """Scenario.from_yaml surfaces the child-key rejection to users.

    The JSON schema rejects these keys before the parser runs, so the
    scenario-level error is a jsonschema.ValidationError; the parser's
    ValueError remains the guard for direct build_risk_groups callers.
    """

    def test_from_yaml_child_membership_raises(self):
        """A scenario with a membership block on a child fails to load."""
        yaml_content = """
network:
  nodes:
    A:
      attrs:
        role: leaf

risk_groups:
  - name: Parent
    children:
      - name: Child
        membership:
          scope: node
          match:
            conditions:
              - attr: role
                op: "=="
                value: leaf
"""
        with pytest.raises(
            jsonschema.ValidationError,
            match="Additional properties are not allowed",
        ):
            Scenario.from_yaml(yaml_content)

    def test_from_yaml_child_disabled_raises(self):
        """A scenario with a disabled flag on a child fails to load."""
        yaml_content = """
network:
  nodes:
    A: {}

risk_groups:
  - name: Parent
    children:
      - name: Child
        disabled: true
"""
        with pytest.raises(
            jsonschema.ValidationError,
            match="Additional properties are not allowed",
        ):
            Scenario.from_yaml(yaml_content)
