from typing import Any

import pytest

from ngraph.dsl.selectors import Condition, evaluate_condition, evaluate_conditions

# Use Condition directly (FailureCondition is just an alias)
FailureCondition = Condition


class TestEvaluateCondition:
    def test_equality_and_inequality(self) -> None:
        attrs = {"x": 5, "y": "abc"}
        assert evaluate_condition(attrs, FailureCondition("x", "==", 5)) is True
        assert evaluate_condition(attrs, FailureCondition("x", "!=", 6)) is True
        assert evaluate_condition(attrs, FailureCondition("y", "==", "abc")) is True

    def test_ordering_with_none_guard(self) -> None:
        attrs = {"a": 3, "b": None}
        assert evaluate_condition(attrs, FailureCondition("a", ">", 2)) is True
        assert evaluate_condition(attrs, FailureCondition("a", ">=", 3)) is True
        assert evaluate_condition(attrs, FailureCondition("a", "<", 10)) is True
        assert evaluate_condition(attrs, FailureCondition("a", "<=", 3)) is True
        # None comparisons must return False rather than raising
        assert evaluate_condition(attrs, FailureCondition("b", ">", 0)) is False
        assert evaluate_condition(attrs, FailureCondition("missing", "<", 0)) is False

    def test_contains_and_not_contains(self) -> None:
        attrs = {"s": "hello", "l": [1, 2, 3], "n": None, "i": 123}
        assert (
            evaluate_condition(attrs, FailureCondition("s", "contains", "ell")) is True
        )
        assert evaluate_condition(attrs, FailureCondition("l", "contains", 2)) is True
        assert (
            evaluate_condition(attrs, FailureCondition("s", "not_contains", "xyz"))
            is True
        )
        # None yields False for both contains and not_contains (can't evaluate on None)
        assert evaluate_condition(attrs, FailureCondition("n", "contains", 1)) is False
        assert (
            evaluate_condition(attrs, FailureCondition("n", "not_contains", 1)) is False
        )
        # Non-iterable: contains returns False, not_contains returns True
        assert evaluate_condition(attrs, FailureCondition("i", "contains", 1)) is False
        assert (
            evaluate_condition(attrs, FailureCondition("i", "not_contains", 1)) is True
        )

    def test_any_value_and_no_value(self) -> None:
        attrs: dict[str, Any] = {"p": 0, "q": None}
        assert evaluate_condition(attrs, FailureCondition("p", "any_value")) is True
        # any_value with None returns False (attr must have non-None value)
        assert evaluate_condition(attrs, FailureCondition("q", "any_value")) is False
        assert (
            evaluate_condition(attrs, FailureCondition("missing", "any_value")) is False
        )
        assert (
            evaluate_condition(attrs, FailureCondition("missing", "no_value")) is True
        )
        assert evaluate_condition(attrs, FailureCondition("q", "no_value")) is True
        assert evaluate_condition(attrs, FailureCondition("p", "no_value")) is False

    def test_unsupported_operator_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown operator"):
            evaluate_condition({"x": 1}, FailureCondition("x", "bad"))


class TestEvaluateConditions:
    def test_and_or_logic(self) -> None:
        attrs = {"x": 10, "y": "abc"}
        conds = [FailureCondition("x", ">", 5), FailureCondition("y", "==", "abc")]
        assert evaluate_conditions(attrs, conds, "and") is True
        assert evaluate_conditions(attrs, conds, "or") is True

        conds2 = [FailureCondition("x", "<", 5), FailureCondition("y", "!=", "abc")]
        assert evaluate_conditions(attrs, conds2, "and") is False
        assert evaluate_conditions(attrs, conds2, "or") is False

    def test_unsupported_logic(self) -> None:
        # Need non-empty conditions to trigger logic check
        conds = [FailureCondition("x", "==", 1)]
        with pytest.raises(ValueError, match="Unsupported logic"):
            evaluate_conditions({}, conds, "xor")
