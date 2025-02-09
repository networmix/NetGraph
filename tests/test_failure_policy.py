import pytest
from unittest.mock import patch

from ngraph.failure_policy import FailurePolicy


def test_default_attributes():
    """
    Ensure default constructor creates an empty failure_probabilities dict,
    and sets distribution to 'uniform'.
    """
    policy = FailurePolicy()
    assert policy.failure_probabilities == {}
    assert policy.distribution == "uniform"


@patch("ngraph.failure_policy.random")
def test_test_failure_returns_true(mock_random):
    """
    For a specific tag with nonzero probability, verify test_failure() returns True
    when random() is less than that probability.
    """
    policy = FailurePolicy(failure_probabilities={"node1": 0.7})

    # Mock random to return 0.5 which is < 0.7
    mock_random.return_value = 0.5
    assert (
        policy.test_failure("node1") is True
    ), "Should return True when random() < failure probability."


@patch("ngraph.failure_policy.random")
def test_test_failure_returns_false(mock_random):
    """
    For a specific tag with nonzero probability, verify test_failure() returns False
    when random() is not less than that probability.
    """
    policy = FailurePolicy(failure_probabilities={"node1": 0.3})

    # Mock random to return 0.4 which is > 0.3
    mock_random.return_value = 0.4
    assert (
        policy.test_failure("node1") is False
    ), "Should return False when random() >= failure probability."


@patch("ngraph.failure_policy.random")
def test_test_failure_zero_probability(mock_random):
    """
    A probability of zero means it should always return False, even if random() is also zero.
    """
    policy = FailurePolicy(failure_probabilities={"node1": 0.0})

    mock_random.return_value = 0.0
    assert (
        policy.test_failure("node1") is False
    ), "Should always return False with probability = 0.0"


@patch("ngraph.failure_policy.random")
def test_test_failure_no_entry_for_tag(mock_random):
    """
    If no entry for a given tag is found, probability defaults to 0.0 => always False.
    """
    policy = FailurePolicy()

    mock_random.return_value = 0.0
    assert (
        policy.test_failure("unknown_tag") is False
    ), "Unknown tag should default to 0.0 probability => always False."


def test_test_failure_non_uniform_distribution():
    """
    Verify that any distribution other than 'uniform' raises a ValueError.
    """
    policy = FailurePolicy(distribution="non_uniform")

    with pytest.raises(ValueError) as exc_info:
        policy.test_failure("node1")

    assert "Unsupported distribution" in str(exc_info.value)
