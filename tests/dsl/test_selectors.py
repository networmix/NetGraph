"""Comprehensive tests for the unified selector system.

Tests for ngraph.dsl.selectors modules:
- normalize_selector: parsing and normalization
- select_nodes: node selection with all stages
- conditions: all condition operators
"""

import pytest

from ngraph.dsl.selectors import (
    Condition,
    MatchSpec,
    NodeSelector,
    evaluate_condition,
    evaluate_conditions,
    normalize_selector,
    select_nodes,
)
from ngraph.model.network import Network, Node

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def simple_network() -> Network:
    """A simple network with 4 nodes for basic testing."""
    network = Network()
    for name in ["A", "B", "C", "D"]:
        network.add_node(Node(name))
    return network


@pytest.fixture
def attributed_network() -> Network:
    """Network with nodes having various attributes for selector testing."""
    network = Network()

    # Datacenter 1: 2 leafs, 1 spine
    network.add_node(Node("dc1_leaf_1", attrs={"dc": "dc1", "role": "leaf", "tier": 1}))
    network.add_node(Node("dc1_leaf_2", attrs={"dc": "dc1", "role": "leaf", "tier": 1}))
    network.add_node(
        Node("dc1_spine_1", attrs={"dc": "dc1", "role": "spine", "tier": 2})
    )

    # Datacenter 2: 2 leafs, 1 spine (one disabled)
    network.add_node(Node("dc2_leaf_1", attrs={"dc": "dc2", "role": "leaf", "tier": 1}))
    network.add_node(
        Node(
            "dc2_leaf_2", attrs={"dc": "dc2", "role": "leaf", "tier": 1}, disabled=True
        )
    )
    network.add_node(
        Node("dc2_spine_1", attrs={"dc": "dc2", "role": "spine", "tier": 2})
    )

    return network


# ──────────────────────────────────────────────────────────────────────────────
# NodeSelector Schema Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestNodeSelectorSchema:
    """Tests for NodeSelector dataclass validation."""

    def test_path_only_valid(self) -> None:
        """NodeSelector with only path is valid."""
        sel = NodeSelector(path="^dc1/.*")
        assert sel.path == "^dc1/.*"
        assert sel.group_by is None
        assert sel.match is None

    def test_group_by_only_valid(self) -> None:
        """NodeSelector with only group_by is valid."""
        sel = NodeSelector(group_by="role")
        assert sel.group_by == "role"
        assert sel.path is None

    def test_match_only_valid(self) -> None:
        """NodeSelector with only match is valid."""
        cond = Condition(attr="role", op="==", value="leaf")
        match = MatchSpec(conditions=[cond])
        sel = NodeSelector(match=match)
        assert sel.match is not None
        assert sel.path is None
        assert sel.group_by is None

    def test_all_fields_valid(self) -> None:
        """NodeSelector with all fields is valid."""
        cond = Condition(attr="role", op="==", value="leaf")
        match = MatchSpec(conditions=[cond])
        sel = NodeSelector(path="^dc1/.*", group_by="role", match=match)
        assert sel.path == "^dc1/.*"
        assert sel.group_by == "role"
        assert sel.match is not None

    def test_no_fields_raises(self) -> None:
        """NodeSelector with no fields raises ValueError."""
        with pytest.raises(ValueError, match="at least one of"):
            NodeSelector()


# ──────────────────────────────────────────────────────────────────────────────
# normalize_selector Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestNormalizeSelector:
    """Tests for normalize_selector function."""

    def test_string_input_creates_path_selector(self) -> None:
        """String input creates NodeSelector with path."""
        sel = normalize_selector("^dc1/.*", "demand")
        assert sel.path == "^dc1/.*"
        assert sel.group_by is None
        assert sel.match is None

    def test_dict_with_path(self) -> None:
        """Dict with path key creates selector."""
        sel = normalize_selector({"path": "^dc1/.*"}, "demand")
        assert sel.path == "^dc1/.*"

    def test_dict_with_group_by(self) -> None:
        """Dict with group_by key creates selector."""
        sel = normalize_selector({"group_by": "role"}, "demand")
        assert sel.group_by == "role"
        assert sel.path is None

    def test_dict_with_match(self) -> None:
        """Dict with match key creates selector."""
        sel = normalize_selector(
            {
                "match": {
                    "conditions": [{"attr": "role", "op": "==", "value": "leaf"}],
                    "logic": "and",
                }
            },
            "demand",
        )
        assert sel.match is not None
        assert len(sel.match.conditions) == 1
        assert sel.match.logic == "and"

    def test_dict_combined_fields(self) -> None:
        """Dict with multiple fields creates combined selector."""
        sel = normalize_selector(
            {
                "path": "^dc1/.*",
                "group_by": "role",
                "match": {"conditions": [{"attr": "tier", "op": "==", "value": 1}]},
            },
            "demand",
        )
        assert sel.path == "^dc1/.*"
        assert sel.group_by == "role"
        assert sel.match is not None

    def test_existing_node_selector_with_active_only_set(self) -> None:
        """NodeSelector with active_only already set is returned as-is."""
        original = NodeSelector(path="^A$", active_only=False)
        result = normalize_selector(original, "demand")
        assert result is original
        assert result.active_only is False  # Preserved, not overwritten

    def test_existing_node_selector_active_only_none_gets_default(self) -> None:
        """NodeSelector with active_only=None gets context default (new object)."""
        original = NodeSelector(path="^A$")  # active_only defaults to None
        assert original.active_only is None

        result = normalize_selector(original, "demand")
        assert result is not original  # New object created
        assert result.active_only is True  # demand context default
        assert original.active_only is None  # Original unchanged

    def test_empty_dict_raises(self) -> None:
        """Empty dict raises ValueError."""
        with pytest.raises(ValueError, match="at least one of"):
            normalize_selector({}, "demand")

    def test_invalid_type_raises(self) -> None:
        """Invalid type raises ValueError."""
        with pytest.raises(ValueError, match="must be string or dict"):
            normalize_selector(123, "demand")  # type: ignore

    def test_unknown_context_raises(self) -> None:
        """Unknown context raises ValueError."""
        with pytest.raises(ValueError, match="Unknown context"):
            normalize_selector("^A$", "unknown_context")

    # Context-aware active_only defaults
    def test_demand_context_active_only_true(self) -> None:
        """Demand context defaults active_only to True."""
        sel = normalize_selector("^A$", "demand")
        assert sel.active_only is True

    def test_workflow_context_active_only_true(self) -> None:
        """Workflow context defaults active_only to True."""
        sel = normalize_selector("^A$", "workflow")
        assert sel.active_only is True

    def test_adjacency_context_active_only_false(self) -> None:
        """Adjacency context defaults active_only to False."""
        sel = normalize_selector("^A$", "adjacency")
        assert sel.active_only is False

    def test_override_context_active_only_false(self) -> None:
        """Override context defaults active_only to False."""
        sel = normalize_selector("^A$", "override")
        assert sel.active_only is False

    def test_explicit_active_only_overrides_default(self) -> None:
        """Explicit active_only in dict overrides context default."""
        sel = normalize_selector({"path": "^A$", "active_only": False}, "demand")
        assert sel.active_only is False


# ──────────────────────────────────────────────────────────────────────────────
# select_nodes Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestSelectNodesByPath:
    """Tests for path-based node selection."""

    def test_simple_regex_match(self, simple_network: Network) -> None:
        """Simple regex matches nodes."""
        sel = NodeSelector(path="^[AB]$")
        groups = select_nodes(simple_network, sel, default_active_only=False)

        # Pattern without capture groups uses pattern as label
        assert "^[AB]$" in groups
        node_names = [n.name for n in groups["^[AB]$"]]
        assert sorted(node_names) == ["A", "B"]

    def test_capture_groups_create_labels(self, attributed_network: Network) -> None:
        """Capture groups in regex create group labels."""
        sel = NodeSelector(path="^(dc[12])_.*")
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        # Captured groups become labels
        assert "dc1" in groups
        assert "dc2" in groups
        assert len(groups["dc1"]) == 3
        assert len(groups["dc2"]) == 3

    def test_no_match_returns_empty(self, simple_network: Network) -> None:
        """No matching nodes returns empty dict."""
        sel = NodeSelector(path="^nonexistent$")
        groups = select_nodes(simple_network, sel, default_active_only=False)
        assert groups == {}


class TestSelectNodesByMatch:
    """Tests for match-based filtering."""

    def test_match_filters_nodes(self, attributed_network: Network) -> None:
        """Match conditions filter nodes."""
        sel = NodeSelector(
            path=".*",
            match=MatchSpec(conditions=[Condition(attr="role", op="==", value="leaf")]),
        )
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        # Only leaf nodes should match
        all_nodes = [n for nodes in groups.values() for n in nodes]
        assert len(all_nodes) == 4  # 2 dc1 leafs + 2 dc2 leafs
        assert all(n.attrs["role"] == "leaf" for n in all_nodes)

    def test_match_with_and_logic(self, attributed_network: Network) -> None:
        """Match with AND logic requires all conditions."""
        sel = NodeSelector(
            path=".*",
            match=MatchSpec(
                conditions=[
                    Condition(attr="role", op="==", value="leaf"),
                    Condition(attr="dc", op="==", value="dc1"),
                ],
                logic="and",
            ),
        )
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        all_nodes = [n for nodes in groups.values() for n in nodes]
        assert len(all_nodes) == 2  # Only dc1 leafs
        assert all(n.attrs["dc"] == "dc1" for n in all_nodes)

    def test_match_with_or_logic(self, attributed_network: Network) -> None:
        """Match with OR logic requires any condition."""
        sel = NodeSelector(
            path=".*",
            match=MatchSpec(
                conditions=[
                    Condition(attr="role", op="==", value="leaf"),
                    Condition(attr="role", op="==", value="spine"),
                ],
                logic="or",
            ),
        )
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        all_nodes = [n for nodes in groups.values() for n in nodes]
        assert len(all_nodes) == 6  # All nodes match leaf or spine


class TestSelectNodesActiveOnly:
    """Tests for active_only filtering."""

    def test_active_only_excludes_disabled(self, attributed_network: Network) -> None:
        """active_only=True excludes disabled nodes."""
        sel = NodeSelector(path="^dc2_.*", active_only=True)
        groups = select_nodes(attributed_network, sel, default_active_only=True)

        all_nodes = [n for nodes in groups.values() for n in nodes]
        # dc2_leaf_2 is disabled, should be excluded
        assert len(all_nodes) == 2
        assert all(not n.disabled for n in all_nodes)

    def test_active_only_false_includes_disabled(
        self, attributed_network: Network
    ) -> None:
        """active_only=False includes disabled nodes."""
        sel = NodeSelector(path="^dc2_.*", active_only=False)
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        all_nodes = [n for nodes in groups.values() for n in nodes]
        assert len(all_nodes) == 3  # Includes disabled dc2_leaf_2

    def test_excluded_nodes_always_excluded(self, attributed_network: Network) -> None:
        """excluded_nodes parameter always excludes specified nodes."""
        sel = NodeSelector(path="^dc1_.*")
        groups = select_nodes(
            attributed_network,
            sel,
            default_active_only=False,
            excluded_nodes={"dc1_leaf_1"},
        )

        all_nodes = [n for nodes in groups.values() for n in nodes]
        node_names = [n.name for n in all_nodes]
        assert "dc1_leaf_1" not in node_names
        assert len(all_nodes) == 2


class TestSelectNodesByGroupBy:
    """Tests for group_by attribute grouping."""

    def test_group_by_attribute(self, attributed_network: Network) -> None:
        """group_by creates groups by attribute value."""
        sel = NodeSelector(path=".*", group_by="role")
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        assert "leaf" in groups
        assert "spine" in groups
        assert len(groups["leaf"]) == 4
        assert len(groups["spine"]) == 2

    def test_group_by_overrides_capture_groups(
        self, attributed_network: Network
    ) -> None:
        """group_by overrides regex capture group labels."""
        sel = NodeSelector(path="^(dc[12])_.*", group_by="role")
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        # group_by should override capture group labels
        assert "dc1" not in groups
        assert "dc2" not in groups
        assert "leaf" in groups
        assert "spine" in groups

    def test_group_by_missing_attribute_excludes_nodes(
        self, attributed_network: Network
    ) -> None:
        """Nodes missing group_by attribute are excluded."""
        # Add a node without the grouping attribute
        attributed_network.add_node(Node("orphan", attrs={"other": "value"}))

        sel = NodeSelector(path=".*", group_by="role")
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        all_nodes = [n for nodes in groups.values() for n in nodes]
        node_names = [n.name for n in all_nodes]
        assert "orphan" not in node_names


class TestSelectNodesMatchOnly:
    """Tests for match-only selectors (no path specified)."""

    def test_match_only_selects_all_then_filters(
        self, attributed_network: Network
    ) -> None:
        """Match-only selector starts with all nodes, then filters."""
        sel = NodeSelector(
            match=MatchSpec(conditions=[Condition(attr="tier", op="==", value=2)])
        )
        groups = select_nodes(attributed_network, sel, default_active_only=False)

        # Only spine nodes (tier=2) should match
        all_nodes = [n for nodes in groups.values() for n in nodes]
        assert len(all_nodes) == 2
        assert all(n.attrs["tier"] == 2 for n in all_nodes)


# ──────────────────────────────────────────────────────────────────────────────
# Condition Operators Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestConditionOperators:
    """Tests for all supported condition operators."""

    def test_equality_operator(self) -> None:
        """Test == operator."""
        attrs = {"x": 5, "y": "abc"}
        assert evaluate_condition(attrs, Condition("x", "==", 5)) is True
        assert evaluate_condition(attrs, Condition("x", "==", 6)) is False
        assert evaluate_condition(attrs, Condition("y", "==", "abc")) is True

    def test_inequality_operator(self) -> None:
        """Test != operator."""
        attrs = {"x": 5}
        assert evaluate_condition(attrs, Condition("x", "!=", 6)) is True
        assert evaluate_condition(attrs, Condition("x", "!=", 5)) is False

    def test_less_than_operator(self) -> None:
        """Test < operator."""
        attrs = {"x": 5}
        assert evaluate_condition(attrs, Condition("x", "<", 10)) is True
        assert evaluate_condition(attrs, Condition("x", "<", 5)) is False
        assert evaluate_condition(attrs, Condition("x", "<", 3)) is False

    def test_less_than_or_equal_operator(self) -> None:
        """Test <= operator."""
        attrs = {"x": 5}
        assert evaluate_condition(attrs, Condition("x", "<=", 5)) is True
        assert evaluate_condition(attrs, Condition("x", "<=", 10)) is True
        assert evaluate_condition(attrs, Condition("x", "<=", 3)) is False

    def test_greater_than_operator(self) -> None:
        """Test > operator."""
        attrs = {"x": 5}
        assert evaluate_condition(attrs, Condition("x", ">", 3)) is True
        assert evaluate_condition(attrs, Condition("x", ">", 5)) is False
        assert evaluate_condition(attrs, Condition("x", ">", 10)) is False

    def test_greater_than_or_equal_operator(self) -> None:
        """Test >= operator."""
        attrs = {"x": 5}
        assert evaluate_condition(attrs, Condition("x", ">=", 5)) is True
        assert evaluate_condition(attrs, Condition("x", ">=", 3)) is True
        assert evaluate_condition(attrs, Condition("x", ">=", 10)) is False

    def test_contains_operator_string(self) -> None:
        """Test contains operator with strings."""
        attrs = {"s": "hello world"}
        assert evaluate_condition(attrs, Condition("s", "contains", "world")) is True
        assert evaluate_condition(attrs, Condition("s", "contains", "xyz")) is False

    def test_contains_operator_list(self) -> None:
        """Test contains operator with lists."""
        attrs = {"l": [1, 2, 3]}
        assert evaluate_condition(attrs, Condition("l", "contains", 2)) is True
        assert evaluate_condition(attrs, Condition("l", "contains", 5)) is False

    def test_not_contains_operator(self) -> None:
        """Test not_contains operator."""
        attrs = {"s": "hello", "l": [1, 2]}
        assert evaluate_condition(attrs, Condition("s", "not_contains", "xyz")) is True
        assert evaluate_condition(attrs, Condition("s", "not_contains", "ell")) is False
        assert evaluate_condition(attrs, Condition("l", "not_contains", 5)) is True
        assert evaluate_condition(attrs, Condition("l", "not_contains", 1)) is False

    def test_in_operator(self) -> None:
        """Test in operator (value in list)."""
        attrs = {"x": "b"}
        assert evaluate_condition(attrs, Condition("x", "in", ["a", "b", "c"])) is True
        assert evaluate_condition(attrs, Condition("x", "in", ["x", "y"])) is False

    def test_not_in_operator(self) -> None:
        """Test not_in operator."""
        attrs = {"x": "d"}
        assert (
            evaluate_condition(attrs, Condition("x", "not_in", ["a", "b", "c"])) is True
        )
        assert evaluate_condition(attrs, Condition("x", "not_in", ["d", "e"])) is False

    def test_exists_operator(self) -> None:
        """Test exists operator (attribute exists and is not None)."""
        attrs = {"x": 0, "y": None, "z": ""}
        assert evaluate_condition(attrs, Condition("x", "exists")) is True
        assert evaluate_condition(attrs, Condition("y", "exists")) is False
        assert evaluate_condition(attrs, Condition("z", "exists")) is True
        assert evaluate_condition(attrs, Condition("missing", "exists")) is False

    def test_not_exists_operator(self) -> None:
        """Test not_exists operator (attribute missing or None)."""
        attrs = {"x": 0, "y": None}
        assert evaluate_condition(attrs, Condition("x", "not_exists")) is False
        assert evaluate_condition(attrs, Condition("y", "not_exists")) is True
        assert evaluate_condition(attrs, Condition("missing", "not_exists")) is True

    def test_missing_attribute_returns_false(self) -> None:
        """Missing attribute returns False for most operators."""
        attrs = {}
        assert evaluate_condition(attrs, Condition("x", "==", 5)) is False
        assert evaluate_condition(attrs, Condition("x", ">", 0)) is False
        assert evaluate_condition(attrs, Condition("x", "contains", "a")) is False

    def test_none_value_returns_false(self) -> None:
        """None value returns False for comparison operators."""
        attrs = {"x": None}
        assert evaluate_condition(attrs, Condition("x", "==", None)) is False
        assert evaluate_condition(attrs, Condition("x", ">", 0)) is False

    def test_invalid_operator_raises(self) -> None:
        """Invalid operator raises ValueError at construction time."""
        with pytest.raises(ValueError, match="Invalid operator"):
            Condition("x", "invalid_op", 5)  # type: ignore

    def test_in_operator_requires_list(self) -> None:
        """in operator requires list value."""
        with pytest.raises(ValueError, match="requires list"):
            evaluate_condition({"x": "a"}, Condition("x", "in", "abc"))


class TestEvaluateConditions:
    """Tests for evaluate_conditions with multiple conditions."""

    def test_and_logic_all_true(self) -> None:
        """AND logic returns True when all conditions pass."""
        attrs = {"x": 5, "y": "abc"}
        conds = [
            Condition("x", ">", 3),
            Condition("y", "==", "abc"),
        ]
        assert evaluate_conditions(attrs, conds, "and") is True

    def test_and_logic_one_false(self) -> None:
        """AND logic returns False when any condition fails."""
        attrs = {"x": 5, "y": "abc"}
        conds = [
            Condition("x", ">", 10),  # False
            Condition("y", "==", "abc"),  # True
        ]
        assert evaluate_conditions(attrs, conds, "and") is False

    def test_or_logic_one_true(self) -> None:
        """OR logic returns True when any condition passes."""
        attrs = {"x": 5}
        conds = [
            Condition("x", ">", 10),  # False
            Condition("x", "<", 10),  # True
        ]
        assert evaluate_conditions(attrs, conds, "or") is True

    def test_or_logic_all_false(self) -> None:
        """OR logic returns False when all conditions fail."""
        attrs = {"x": 5}
        conds = [
            Condition("x", ">", 10),
            Condition("x", "<", 3),
        ]
        assert evaluate_conditions(attrs, conds, "or") is False

    def test_empty_conditions_returns_true(self) -> None:
        """Empty conditions list returns True."""
        assert evaluate_conditions({}, [], "and") is True
        assert evaluate_conditions({}, [], "or") is True

    def test_invalid_logic_raises(self) -> None:
        """Invalid logic raises ValueError."""
        # Provide non-empty conditions so we don't return early
        conds = [Condition("x", "==", 1)]
        with pytest.raises(ValueError, match="Unsupported logic"):
            evaluate_conditions({}, conds, "xor")
