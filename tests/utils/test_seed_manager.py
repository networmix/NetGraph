"""Tests for seed management functionality."""

from ngraph.utils.seed_manager import SeedManager


class TestSeedManager:
    """Test SeedManager functionality."""

    def test_init_with_master_seed(self):
        """Test SeedManager initialization with master seed."""
        seed_mgr = SeedManager(42)
        assert seed_mgr.master_seed == 42

    def test_init_without_master_seed(self):
        """Test SeedManager initialization without master seed."""
        seed_mgr = SeedManager()
        assert seed_mgr.master_seed is None

    def test_derive_seed_with_master_seed(self):
        """Test deterministic seed derivation."""
        seed_mgr = SeedManager(42)

        # Same components should produce same seed
        seed1 = seed_mgr.derive_seed("test", "component")
        seed2 = seed_mgr.derive_seed("test", "component")
        assert seed1 == seed2
        assert seed1 is not None
        assert isinstance(seed1, int)
        assert 0 <= seed1 <= 0x7FFFFFFF  # Positive 32-bit integer

        # Different components should produce different seeds
        seed3 = seed_mgr.derive_seed("test", "other")
        assert seed1 != seed3

        # Order matters
        seed4 = seed_mgr.derive_seed("component", "test")
        assert seed1 != seed4

    def test_derive_seed_without_master_seed(self):
        """Test seed derivation returns None when no master seed."""
        seed_mgr = SeedManager()

        seed = seed_mgr.derive_seed("test", "component")
        assert seed is None

    def test_derive_seed_different_master_seeds(self):
        """Test different master seeds produce different derived seeds."""
        seed_mgr1 = SeedManager(42)
        seed_mgr2 = SeedManager(123)

        seed1 = seed_mgr1.derive_seed("test", "component")
        seed2 = seed_mgr2.derive_seed("test", "component")
        assert seed1 != seed2

    def test_derive_seed_various_component_types(self):
        """Test seed derivation with various component types."""
        seed_mgr = SeedManager(42)

        # Test with strings
        seed1 = seed_mgr.derive_seed("failure_policy", "default")
        assert seed1 is not None

        # Test with integers
        seed2 = seed_mgr.derive_seed("worker", 5)
        assert seed2 is not None

        # Test with mixed types
        seed3 = seed_mgr.derive_seed("step", "analysis", 0)
        assert seed3 is not None

        # All should be different
        assert len({seed1, seed2, seed3}) == 3

    def test_seed_derivation_consistency(self):
        """Test that seed derivation is consistent across instances."""
        seed_mgr1 = SeedManager(42)
        seed_mgr2 = SeedManager(42)

        # Same master seed should produce same derived seeds
        seed1 = seed_mgr1.derive_seed("failure_policy", "default")
        seed2 = seed_mgr2.derive_seed("failure_policy", "default")
        assert seed1 == seed2

    def test_seed_distribution(self):
        """Test that derived seeds have good distribution."""
        seed_mgr = SeedManager(42)

        # Generate many seeds
        seeds = []
        for i in range(1000):
            seed = seed_mgr.derive_seed("test", i)
            seeds.append(seed)

        # Check that seeds are unique (very high probability)
        assert len(set(seeds)) > 990  # Allow for some collisions

    def test_empty_components(self):
        """Test seed derivation with no components."""
        seed_mgr = SeedManager(42)

        seed1 = seed_mgr.derive_seed()
        seed2 = seed_mgr.derive_seed()
        assert seed1 == seed2
        assert seed1 is not None
