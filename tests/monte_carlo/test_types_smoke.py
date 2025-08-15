from __future__ import annotations

from typing import get_type_hints

from ngraph.monte_carlo import types as mc_types


def test_monte_carlo_types_protocols_shape() -> None:
    # Ensure TypedDict definitions expose expected fields
    hints = get_type_hints(mc_types.FlowResult, include_extras=True)
    assert set(hints.keys()) >= {"src", "dst", "metric", "value"}
    hints_s = get_type_hints(mc_types.FlowStats, include_extras=True)
    assert set(hints_s.keys()) >= {"cost_distribution", "edges", "edges_kind"}
