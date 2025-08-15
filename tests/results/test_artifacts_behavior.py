from __future__ import annotations

from ngraph.results.artifacts import CapacityEnvelope


def test_capacity_envelope_percentile_monotonicity_and_bounds() -> None:
    values = [1.0, 2.0, 2.0, 3.0, 10.0]
    env = CapacityEnvelope.from_values("S", "D", "combine", values)
    # Nondecreasing percentiles
    p10 = env.get_percentile(10)
    p50 = env.get_percentile(50)
    p90 = env.get_percentile(90)
    assert p10 <= p50 <= p90
    # Bounds: min <= pX <= max
    assert env.min_capacity <= p10 <= env.max_capacity
    assert env.min_capacity <= p50 <= env.max_capacity
    assert env.min_capacity <= p90 <= env.max_capacity
