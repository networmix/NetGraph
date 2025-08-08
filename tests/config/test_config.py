"""Tests for `ngraph.config` focusing on behavior and correctness."""

from ngraph.config import TrafficManagerConfig


def test_estimate_rounds_bounds_default_config() -> None:
    """Default config clamps results within [min_rounds, max_rounds]."""
    config = TrafficManagerConfig()

    # Below lower bound clamps to min_rounds
    assert config.estimate_rounds(-1.0) == config.min_rounds

    # Far above upper bound clamps to max_rounds
    very_high_ratio = (config.max_rounds + 100) / config.ratio_multiplier
    assert config.estimate_rounds(very_high_ratio) == config.max_rounds

    # Return type is int and always within bounds
    result = config.estimate_rounds(0.5)
    assert isinstance(result, int)
    assert config.min_rounds <= result <= config.max_rounds


def test_estimate_rounds_monotonic_default_config() -> None:
    """Estimated rounds are non-decreasing with increasing ratio."""
    config = TrafficManagerConfig()
    ratios = [0.0, 0.5, 1.0, 2.0, 5.0]
    values = [config.estimate_rounds(r) for r in ratios]
    assert values == sorted(values)


def test_estimate_rounds_formula_and_clamping_custom_config() -> None:
    """Formula matches base + multiplier * ratio when not clamped; clamps otherwise.

    Uses a custom configuration to test exact arithmetic independent of defaults.
    """
    # Wide bounds: exact formula applies
    cfg_linear = TrafficManagerConfig(
        default_rounds=0,
        min_rounds=0,
        max_rounds=1_000_000,
        ratio_base=3,
        ratio_multiplier=2,
    )
    assert cfg_linear.estimate_rounds(0.0) == 3  # 3 + 2*0 = 3
    assert cfg_linear.estimate_rounds(1.5) == 6  # 3 + 2*1.5 = 6
    assert cfg_linear.estimate_rounds(10.0) == 23  # 3 + 2*10 = 23

    # Tight bounds: verify both min and max clamping
    cfg_clamped = TrafficManagerConfig(
        default_rounds=10,
        min_rounds=8,
        max_rounds=20,
        ratio_base=3,
        ratio_multiplier=2,
    )
    assert cfg_clamped.estimate_rounds(-5.0) == 8  # below min
    assert cfg_clamped.estimate_rounds(1.5) == 8  # 3 + 2*1.5 = 6 -> clamp to 8
    assert cfg_clamped.estimate_rounds(100.0) == 20  # above max
