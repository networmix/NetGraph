"""Tests for dot-notation attribute access in conditions."""

from ngraph.dsl.selectors import Condition, evaluate_condition, resolve_attr_path


class TestResolveAttrPath:
    """Tests for resolve_attr_path() function."""

    def test_simple_attribute(self):
        """Single-segment path resolves to top-level attribute."""
        attrs = {"role": "spine", "tier": 2}
        found, value = resolve_attr_path(attrs, "role")
        assert found is True
        assert value == "spine"

    def test_nested_attribute(self):
        """Dot-notation resolves nested dicts."""
        attrs = {"hardware": {"vendor": "Acme", "model": "X100"}}
        found, value = resolve_attr_path(attrs, "hardware.vendor")
        assert found is True
        assert value == "Acme"

    def test_deeply_nested(self):
        """Multiple levels of nesting work."""
        attrs = {"level1": {"level2": {"level3": "deep_value"}}}
        found, value = resolve_attr_path(attrs, "level1.level2.level3")
        assert found is True
        assert value == "deep_value"

    def test_missing_attribute(self):
        """Missing top-level attribute returns (False, None)."""
        attrs = {"role": "spine"}
        found, value = resolve_attr_path(attrs, "missing")
        assert found is False
        assert value is None

    def test_missing_nested_attribute(self):
        """Missing nested attribute returns (False, None)."""
        attrs = {"hardware": {"vendor": "Acme"}}
        found, value = resolve_attr_path(attrs, "hardware.missing")
        assert found is False
        assert value is None

    def test_path_through_non_dict(self):
        """Path through non-dict value returns (False, None)."""
        attrs = {"hardware": "simple_string"}
        found, value = resolve_attr_path(attrs, "hardware.vendor")
        assert found is False
        assert value is None

    def test_empty_attrs(self):
        """Empty attrs dict handles any path."""
        found, value = resolve_attr_path({}, "any.path")
        assert found is False
        assert value is None

    def test_none_value(self):
        """None value is found (different from missing)."""
        attrs = {"value": None}
        found, value = resolve_attr_path(attrs, "value")
        assert found is True
        assert value is None


class TestEvaluateConditionWithDotNotation:
    """Tests for evaluate_condition() with dot-notation paths."""

    def test_equality_nested(self):
        """Equality operator works with nested attributes."""
        attrs = {"hardware": {"vendor": "Acme"}}
        cond = Condition(attr="hardware.vendor", operator="==", value="Acme")
        assert evaluate_condition(attrs, cond) is True

    def test_inequality_nested(self):
        """Inequality operator works with nested attributes."""
        attrs = {"hardware": {"vendor": "Acme"}}
        cond = Condition(attr="hardware.vendor", operator="!=", value="Other")
        assert evaluate_condition(attrs, cond) is True

    def test_numeric_comparison_nested(self):
        """Numeric comparison works with nested attributes."""
        attrs = {"metrics": {"latency": 50}}
        cond = Condition(attr="metrics.latency", operator="<", value=100)
        assert evaluate_condition(attrs, cond) is True

    def test_contains_nested(self):
        """Contains operator works with nested attributes."""
        attrs = {"config": {"tags": ["prod", "web"]}}
        cond = Condition(attr="config.tags", operator="contains", value="prod")
        assert evaluate_condition(attrs, cond) is True

    def test_any_value_nested_present(self):
        """any_value operator with present nested attribute."""
        attrs = {"hardware": {"vendor": "Acme"}}
        cond = Condition(attr="hardware.vendor", operator="any_value")
        assert evaluate_condition(attrs, cond) is True

    def test_any_value_nested_missing(self):
        """any_value operator with missing nested attribute."""
        attrs = {"hardware": {}}
        cond = Condition(attr="hardware.vendor", operator="any_value")
        assert evaluate_condition(attrs, cond) is False

    def test_no_value_nested_missing(self):
        """no_value operator with missing nested attribute."""
        attrs = {"hardware": {}}
        cond = Condition(attr="hardware.vendor", operator="no_value")
        assert evaluate_condition(attrs, cond) is True

    def test_no_value_nested_none(self):
        """no_value operator with None nested attribute."""
        attrs = {"hardware": {"vendor": None}}
        cond = Condition(attr="hardware.vendor", operator="no_value")
        assert evaluate_condition(attrs, cond) is True

    def test_backward_compatibility_simple(self):
        """Simple (non-dotted) paths still work."""
        attrs = {"role": "spine", "tier": 2}
        cond = Condition(attr="role", operator="==", value="spine")
        assert evaluate_condition(attrs, cond) is True

    def test_in_operator_nested(self):
        """in operator works with nested attributes."""
        attrs = {"location": {"region": "us-west"}}
        cond = Condition(
            attr="location.region", operator="in", value=["us-west", "us-east"]
        )
        assert evaluate_condition(attrs, cond) is True


class TestDeeplyNestedDotNotation:
    """Tests for deeply nested attribute paths (4+ levels)."""

    def test_four_level_nesting(self):
        """Four levels of nesting work correctly."""
        attrs = {"infrastructure": {"facility": {"building": {"floor": "3"}}}}
        found, value = resolve_attr_path(
            attrs, "infrastructure.facility.building.floor"
        )
        assert found is True
        assert value == "3"

    def test_five_level_nesting(self):
        """Five levels of nesting work correctly."""
        attrs = {"topology": {"fiber": {"path": {"segment": {"conduit_id": "C-001"}}}}}
        found, value = resolve_attr_path(
            attrs, "topology.fiber.path.segment.conduit_id"
        )
        assert found is True
        assert value == "C-001"

    def test_deep_nesting_condition_evaluation(self):
        """Condition evaluation works with deeply nested paths."""
        attrs = {"facility": {"datacenter": {"room": {"rack": {"pdu_zone": "A"}}}}}
        cond = Condition(
            attr="facility.datacenter.room.rack.pdu_zone", operator="==", value="A"
        )
        assert evaluate_condition(attrs, cond) is True

    def test_deep_nesting_missing_intermediate(self):
        """Missing intermediate level returns (False, None)."""
        attrs = {
            "facility": {
                "datacenter": {
                    # "room" is missing
                }
            }
        }
        found, value = resolve_attr_path(
            attrs, "facility.datacenter.room.rack.pdu_zone"
        )
        assert found is False
        assert value is None

    def test_deep_nesting_with_list_at_leaf(self):
        """Deeply nested path ending in a list works with contains operator."""
        attrs = {"network": {"fabric": {"tier": {"roles": ["spine", "border"]}}}}
        cond = Condition(
            attr="network.fabric.tier.roles", operator="contains", value="spine"
        )
        assert evaluate_condition(attrs, cond) is True

        cond_miss = Condition(
            attr="network.fabric.tier.roles", operator="contains", value="leaf"
        )
        assert evaluate_condition(attrs, cond_miss) is False
