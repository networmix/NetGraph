from ngraph.model.failure.policy import FailurePolicy, FailureRule


def test_weighted_choice_uses_weight_by_and_excludes_zero_weight_items() -> None:
    """When weight_by is set and count equals number of positive weights,
    selection should return only positive-weight items regardless of RNG.
    """
    rule = FailureRule(
        scope="link",
        mode="choice",
        count=2,
        weight_by="cost",
    )
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])], seed=123)

    nodes: dict[str, dict] = {}
    links = {
        "L1": {"cost": 10.0},  # positive weight
        "L2": {"cost": 0.0},  # zero weight
        "L3": {"cost": 5.0},  # positive weight
    }

    failed = set(policy.apply_failures(nodes, links))
    assert failed == {"L1", "L3"}


def test_weighted_choice_fills_from_zero_when_insufficient_positive() -> None:
    """If fewer positive-weight items exist than count, fill the remainder
    uniformly from zero-weight items.
    """
    rule = FailureRule(
        scope="link",
        mode="choice",
        count=2,
        weight_by="cost",
    )
    # Seed ensures deterministic fill choice among zeros
    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(modes=[FailureMode(weight=1.0, rules=[rule])], seed=42)

    nodes: dict[str, dict] = {}
    links = {
        "L1": {"cost": 7.0},  # positive weight
        "L2": {"cost": 0.0},  # zero weight
        "L3": {"cost": 0.0},  # zero weight
    }

    failed = set(policy.apply_failures(nodes, links))
    assert "L1" in failed  # must include the only positive
    assert len(failed) == 2
    # The second pick must be one of the zero-weight items
    assert len(failed - {"L1"}) == 1
    assert (failed - {"L1"}).issubset({"L2", "L3"})


def test_weighted_modes_selects_positive_weight_mode_only() -> None:
    """With one zero-weight and one positive-weight mode, selection must use the positive-weight mode."""
    # Mode 0 (weight 0): link rule
    link_rule = FailureRule(scope="link", mode="choice", count=1)
    # Mode 1 (weight 1): node rule
    node_rule = FailureRule(scope="node", mode="all")

    from ngraph.model.failure.policy import FailureMode

    policy = FailurePolicy(
        modes=[
            # Zero-weight mode should never be selected
            FailureMode(weight=0.0, rules=[link_rule]),
            FailureMode(weight=1.0, rules=[node_rule]),
        ],
        seed=7,
    )

    nodes = {"N1": {}, "N2": {}}
    links = {"L1": {}, "L2": {}}

    failed = set(policy.apply_failures(nodes, links))
    # Only nodes should be present since the positive-weight mode applies a node rule
    assert failed.issubset(set(nodes))
    assert failed == {"N1", "N2"}
