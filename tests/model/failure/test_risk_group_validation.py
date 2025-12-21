"""Tests for risk group reference validation."""

import pytest

from ngraph.model.failure.validation import validate_risk_group_references
from ngraph.model.network import Link, Network, Node, RiskGroup


class TestValidateRiskGroupReferences:
    """Tests for validate_risk_group_references() function."""

    def test_valid_references(self):
        """No error when all references are valid."""
        net = Network()
        net.add_node(Node("A", risk_groups={"RG1", "RG2"}))
        net.add_node(Node("B", risk_groups={"RG1"}))
        link = Link("A", "B", risk_groups={"RG2"})
        net.add_link(link)

        net.risk_groups["RG1"] = RiskGroup("RG1")
        net.risk_groups["RG2"] = RiskGroup("RG2")

        # Should not raise
        validate_risk_group_references(net)

    def test_undefined_node_reference(self):
        """Error when node references undefined risk group."""
        net = Network()
        net.add_node(Node("A", risk_groups={"Undefined_RG"}))

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        assert "undefined risk group reference" in str(exc_info.value).lower()
        assert "Node 'A'" in str(exc_info.value)
        assert "Undefined_RG" in str(exc_info.value)

    def test_undefined_link_reference(self):
        """Error when link references undefined risk group."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B", risk_groups={"Missing_RG"})
        net.add_link(link)

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        assert "undefined risk group reference" in str(exc_info.value).lower()
        assert "Link 'A->B'" in str(exc_info.value)
        assert "Missing_RG" in str(exc_info.value)

    def test_multiple_undefined_references(self):
        """Error message lists multiple violations."""
        net = Network()
        net.add_node(Node("A", risk_groups={"Bad1"}))
        net.add_node(Node("B", risk_groups={"Bad2"}))
        link = Link("A", "B", risk_groups={"Bad3"})
        net.add_link(link)

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        error_msg = str(exc_info.value)
        assert "3 undefined risk group reference" in error_msg.lower()
        assert "Bad1" in error_msg
        assert "Bad2" in error_msg
        assert "Bad3" in error_msg

    def test_partial_undefined(self):
        """Error when some references are valid but others are not."""
        net = Network()
        net.add_node(Node("A", risk_groups={"Valid_RG", "Invalid_RG"}))

        net.risk_groups["Valid_RG"] = RiskGroup("Valid_RG")

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        error_msg = str(exc_info.value)
        assert "Invalid_RG" in error_msg
        assert "Valid_RG" not in error_msg  # Valid one should not be in error

    def test_empty_network(self):
        """No error for empty network."""
        net = Network()
        validate_risk_group_references(net)  # Should not raise

    def test_no_risk_group_references(self):
        """No error when entities don't reference any risk groups."""
        net = Network()
        net.add_node(Node("A"))
        net.add_node(Node("B"))
        link = Link("A", "B")
        net.add_link(link)

        validate_risk_group_references(net)  # Should not raise

    def test_error_message_has_helpful_hint(self):
        """Error message includes hint about how to fix."""
        net = Network()
        net.add_node(Node("A", risk_groups={"Typo_RG"}))

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        error_msg = str(exc_info.value)
        assert "risk_groups" in error_msg.lower()
        assert "define" in error_msg.lower() or "remove" in error_msg.lower()

    def test_truncation_for_many_errors(self):
        """Error message truncates when there are many violations."""
        net = Network()
        # Create 15 nodes with undefined references
        for i in range(15):
            net.add_node(Node(f"Node_{i}", risk_groups={f"Bad_{i}"}))

        with pytest.raises(ValueError) as exc_info:
            validate_risk_group_references(net)

        error_msg = str(exc_info.value)
        assert "15 undefined" in error_msg.lower()
        assert "..." in error_msg  # Truncation indicator
