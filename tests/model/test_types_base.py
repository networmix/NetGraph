"""Tests for ngraph.types public surface (enums and exports)."""

import pytest

from ngraph.types import FlowPlacement, Mode


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
    """FlowPlacement.from_string parses known names and rejects unknown ones."""
    assert FlowPlacement.from_string("proportional") is FlowPlacement.PROPORTIONAL
    with pytest.raises(ValueError, match="Invalid flow_placement"):
        FlowPlacement.from_string("bogus")
