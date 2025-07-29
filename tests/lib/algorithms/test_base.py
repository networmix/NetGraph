"""Tests for lib.algorithms.base module."""

from ngraph.lib.algorithms.base import (
    MIN_CAP,
    MIN_FLOW,
    EdgeSelect,
    FlowPlacement,
    PathAlg,
)


class TestConstants:
    """Test constants defined in base module."""

    def test_min_cap_value(self) -> None:
        """Test MIN_CAP constant value."""
        assert MIN_CAP == 2**-12
        assert MIN_CAP > 0
        assert MIN_CAP < 0.001

    def test_min_flow_value(self) -> None:
        """Test MIN_FLOW constant value."""
        assert MIN_FLOW == 2**-12
        assert MIN_FLOW > 0
        assert MIN_FLOW < 0.001

    def test_min_values_equal(self) -> None:
        """Test that MIN_CAP and MIN_FLOW have the same value."""
        assert MIN_CAP == MIN_FLOW


class TestPathAlgEnum:
    """Test PathAlg enumeration."""

    def test_path_alg_values(self) -> None:
        """Test PathAlg enum values."""
        assert PathAlg.SPF == 1
        assert PathAlg.KSP_YENS == 2

    def test_path_alg_members(self) -> None:
        """Test PathAlg enum members."""
        assert len(PathAlg) == 2
        assert PathAlg.SPF in PathAlg
        assert PathAlg.KSP_YENS in PathAlg


class TestEdgeSelectEnum:
    """Test EdgeSelect enumeration."""

    def test_edge_select_values(self) -> None:
        """Test EdgeSelect enum values."""
        assert EdgeSelect.ALL_MIN_COST == 1
        assert EdgeSelect.ALL_MIN_COST_WITH_CAP_REMAINING == 2
        assert EdgeSelect.ALL_ANY_COST_WITH_CAP_REMAINING == 3
        assert EdgeSelect.SINGLE_MIN_COST == 4
        assert EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING == 5
        assert EdgeSelect.SINGLE_MIN_COST_WITH_CAP_REMAINING_LOAD_FACTORED == 6
        assert EdgeSelect.USER_DEFINED == 99

    def test_edge_select_members_count(self) -> None:
        """Test EdgeSelect enum members count."""
        assert len(EdgeSelect) == 7


class TestFlowPlacementEnum:
    """Test FlowPlacement enumeration."""

    def test_flow_placement_values(self) -> None:
        """Test FlowPlacement enum values."""
        assert FlowPlacement.PROPORTIONAL == 1
        assert FlowPlacement.EQUAL_BALANCED == 2

    def test_flow_placement_members(self) -> None:
        """Test FlowPlacement enum members."""
        assert len(FlowPlacement) == 2
        assert FlowPlacement.PROPORTIONAL in FlowPlacement
        assert FlowPlacement.EQUAL_BALANCED in FlowPlacement
