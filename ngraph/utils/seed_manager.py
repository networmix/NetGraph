"""Deterministic seed derivation to avoid global random.seed() order dependencies."""

from __future__ import annotations

import hashlib
from typing import Any, Optional


class SeedManager:
    """Derives per-component seeds from one master seed.

    A global random.seed() makes each component's random draws depend on what
    ran before it. SeedManager hashes the master seed with component
    identifiers (SHA-256), so a component's seed does not depend on execution
    order or parallelism.

    Usage:
        seed_mgr = SeedManager(42)
        failure_seed = seed_mgr.derive_seed("failure_policy", "default")
    """

    def __init__(self, master_seed: Optional[int] = None) -> None:
        """Initialize the seed manager.

        Args:
            master_seed: Master seed for deterministic operations. If None,
                        derive_seed() returns None (non-deterministic).
        """
        self.master_seed = master_seed

    def derive_seed(self, *components: Any) -> Optional[int]:
        """Derive a deterministic seed from master seed and component identifiers.

        The master seed and the component identifiers are joined and hashed
        with SHA-256, so distinct components get unrelated seeds.

        Args:
            *components: Component identifiers (strings, integers, etc.) that
                        uniquely identify the component needing a seed.

        Returns:
            Derived seed in [0, 2**31 - 1], or None if no master seed is set.

        Example:
            seed_mgr = SeedManager(42)
            policy_seed = seed_mgr.derive_seed("failure_policy", "default")
            worker_seed = seed_mgr.derive_seed("capacity_analysis", "worker", 3)
        """
        if self.master_seed is None:
            return None

        seed_input = f"{self.master_seed}:" + ":".join(str(c) for c in components)
        hash_digest = hashlib.sha256(seed_input.encode()).digest()

        seed_value = int.from_bytes(hash_digest[:4], byteorder="big")
        return seed_value & 0x7FFFFFFF  # Clear the sign bit: non-negative 31-bit value
