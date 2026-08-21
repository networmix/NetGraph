"""Tests for ngraph.types public surface (enums and exports)."""

import pytest

import ngraph.types
from ngraph.types import FlowPlacement, Mode


def test_min_cap_min_flow_removed() -> None:
    """Dead MIN_CAP/MIN_FLOW constants are no longer exported."""
    assert not hasattr(ngraph.types, "MIN_CAP")
    assert not hasattr(ngraph.types, "MIN_FLOW")
    assert "MIN_CAP" not in ngraph.types.__all__
    assert "MIN_FLOW" not in ngraph.types.__all__


def test_mode_from_string_valid() -> None:
    """Mode.from_string parses names case-insensitively."""
    assert Mode.from_string("combine") is Mode.COMBINE
    assert Mode.from_string("PAIRWISE") is Mode.PAIRWISE
    assert Mode.from_string("Combine") is Mode.COMBINE


def test_mode_from_string_invalid() -> None:
    """Mode.from_string raises ValueError for unknown values."""
    with pytest.raises(ValueError, match="Invalid mode 'aggregate'"):
        Mode.from_string("aggregate")


def test_flow_placement_from_string_still_works() -> None:
    """FlowPlacement.from_string remains the parsing counterpart."""
    assert FlowPlacement.from_string("proportional") is FlowPlacement.PROPORTIONAL
    with pytest.raises(ValueError, match="Invalid flow_placement"):
        FlowPlacement.from_string("bogus")
