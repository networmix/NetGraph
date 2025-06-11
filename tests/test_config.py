"""Test the configuration module functionality."""

from ngraph.config import TRAFFIC_CONFIG, TrafficManagerConfig


def test_traffic_manager_config_defaults():
    """Test that the default configuration values are correct."""
    config = TrafficManagerConfig()

    assert config.default_rounds == 5
    assert config.min_rounds == 5
    assert config.max_rounds == 100
    assert config.ratio_base == 5
    assert config.ratio_multiplier == 5


def test_traffic_manager_config_estimate_rounds():
    """Test the estimate_rounds method with various ratios."""
    config = TrafficManagerConfig()

    # Test with ratio 0 (should return base value, clamped to min)
    assert config.estimate_rounds(0.0) == 5

    # Test with ratio 1 (should return base + multiplier = 10)
    assert config.estimate_rounds(1.0) == 10

    # Test with ratio 2 (should return base + 2*multiplier = 15)
    assert config.estimate_rounds(2.0) == 15

    # Test with very high ratio (should clamp to max)
    assert config.estimate_rounds(100.0) == 100


def test_traffic_manager_config_bounds():
    """Test that bounds are properly enforced."""
    config = TrafficManagerConfig()

    # Test minimum bound
    assert config.estimate_rounds(-1.0) == config.min_rounds

    # Test maximum bound - use a ratio that would exceed max_rounds
    high_ratio = (config.max_rounds + 10) / config.ratio_multiplier
    assert config.estimate_rounds(high_ratio) == config.max_rounds


def test_global_config_instance():
    """Test that the global TRAFFIC_CONFIG instance works."""
    assert TRAFFIC_CONFIG.default_rounds == 5
    assert TRAFFIC_CONFIG.estimate_rounds(1.0) == 10


def test_custom_config():
    """Test creating a custom configuration."""
    custom_config = TrafficManagerConfig(
        default_rounds=10, min_rounds=8, max_rounds=50, ratio_base=3, ratio_multiplier=2
    )

    assert custom_config.default_rounds == 10
    assert custom_config.min_rounds == 8
    assert custom_config.max_rounds == 50
    assert custom_config.ratio_base == 3
    assert custom_config.ratio_multiplier == 2

    # Test estimation with custom values: 3 + 2*1.5 = 6
    assert custom_config.estimate_rounds(1.5) == 8  # Clamped to min_rounds

    # Test estimation: 3 + 2*10 = 23
    assert custom_config.estimate_rounds(10.0) == 23
