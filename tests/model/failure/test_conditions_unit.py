from typing import Any

import pytest

from ngraph.dsl.selectors import Condition, evaluate_condition, evaluate_conditions


class TestEvaluateCondition:
    def test_equality_and_inequality(self) -> None:
        attrs = {"x": 5, "y": "abc"}
        assert evaluate_condition(attrs, Condition("x", "==", 5)) is True
        assert evaluate_condition(attrs, Condition("x", "!=", 6)) is True
        assert evaluate_condition(attrs, Condition("y", "==", "abc")) is True

    def test_ordering_with_none_guard(self) -> None:
        attrs = {"a": 3, "b": None}
        assert evaluate_condition(attrs, Condition("a", ">", 2)) is True
        assert evaluate_condition(attrs, Condition("a", ">=", 3)) is True
        assert evaluate_condition(attrs, Condition("a", "<", 10)) is True
        assert evaluate_condition(attrs, Condition("a", "<=", 3)) is True
        # None comparisons must return False rather than raising
        assert evaluate_condition(attrs, Condition("b", ">", 0)) is False
        assert evaluate_condition(attrs, Condition("missing", "<", 0)) is False

    def test_contains_and_not_contains(self) -> None:
        attrs = {"s": "hello", "l": [1, 2, 3], "n": None, "i": 123}
        assert evaluate_condition(attrs, Condition("s", "contains", "ell")) is True
        assert evaluate_condition(attrs, Condition("l", "contains", 2)) is True
        assert evaluate_condition(attrs, Condition("s", "not_contains", "xyz")) is True
        # None yields False for both contains and not_contains (can't evaluate on None)
        assert evaluate_condition(attrs, Condition("n", "contains", 1)) is False
        assert evaluate_condition(attrs, Condition("n", "not_contains", 1)) is False
        # Non-iterable: contains returns False, not_contains returns True
        assert evaluate_condition(attrs, Condition("i", "contains", 1)) is False
        assert evaluate_condition(attrs, Condition("i", "not_contains", 1)) is True

    def test_exists_and_not_exists(self) -> None:
        attrs: dict[str, Any] = {"p": 0, "q": None}
        assert evaluate_condition(attrs, Condition("p", "exists")) is True
        # exists with None returns False (attr must have non-None value)
        assert evaluate_condition(attrs, Condition("q", "exists")) is False
        assert evaluate_condition(attrs, Condition("missing", "exists")) is False
        assert evaluate_condition(attrs, Condition("missing", "not_exists")) is True
        assert evaluate_condition(attrs, Condition("q", "not_exists")) is True
        assert evaluate_condition(attrs, Condition("p", "not_exists")) is False

    def test_unsupported_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid operator"):
            Condition("x", "bad")  # type: ignore


class TestEvaluateConditions:
    def test_and_or_logic(self) -> None:
        attrs = {"x": 10, "y": "abc"}
        conds = [Condition("x", ">", 5), Condition("y", "==", "abc")]
        assert evaluate_conditions(attrs, conds, "and") is True
        assert evaluate_conditions(attrs, conds, "or") is True

        conds2 = [Condition("x", "<", 5), Condition("y", "!=", "abc")]
        assert evaluate_conditions(attrs, conds2, "and") is False
        assert evaluate_conditions(attrs, conds2, "or") is False

    def test_unsupported_logic(self) -> None:
        # Need non-empty conditions to trigger logic check
        conds = [Condition("x", "==", 1)]
        with pytest.raises(ValueError, match="Unsupported logic"):
            evaluate_conditions({}, conds, "xor")
