"""Tests for lib.algorithms.types module."""

from ngraph.lib.algorithms.types import Edge, FlowSummary


class TestEdgeType:
    """Test Edge type alias."""

    def test_edge_creation(self) -> None:
        """Test Edge tuple creation."""
        edge = ("node_a", "node_b", "edge_key")

        # Should be a valid Edge tuple
        assert len(edge) == 3
        assert edge[0] == "node_a"
        assert edge[1] == "node_b"
        assert edge[2] == "edge_key"

    def test_edge_unpacking(self) -> None:
        """Test Edge tuple unpacking."""
        edge: Edge = ("source", "destination", "key")
        src, dst, key = edge

        assert src == "source"
        assert dst == "destination"
        assert key == "key"


class TestFlowSummary:
    """Test FlowSummary dataclass."""

    def test_flow_summary_creation(self) -> None:
        """Test basic FlowSummary creation."""
        edge_flow = {("A", "B", "e1"): 10.0, ("B", "C", "e2"): 5.0}
        residual_cap = {("A", "B", "e1"): 90.0, ("B", "C", "e2"): 95.0}
        reachable = {"A", "B"}
        min_cut = [("B", "C", "e2")]

        summary = FlowSummary(
            total_flow=15.0,
            edge_flow=edge_flow,
            residual_cap=residual_cap,
            reachable=reachable,
            min_cut=min_cut,
        )

        assert summary.total_flow == 15.0
        assert summary.edge_flow == edge_flow
        assert summary.residual_cap == residual_cap
        assert summary.reachable == reachable
        assert summary.min_cut == min_cut

    def test_flow_summary_structure(self) -> None:
        """Test that FlowSummary has the expected dataclass structure."""
        summary = FlowSummary(
            total_flow=10.0,
            edge_flow={},
            residual_cap={},
            reachable=set(),
            min_cut=[],
        )

        # Verify it's a dataclass with expected fields
        assert hasattr(summary, "__dataclass_fields__")
        fields = summary.__dataclass_fields__
        expected_fields = {
            "total_flow",
            "edge_flow",
            "residual_cap",
            "reachable",
            "min_cut",
        }
        assert set(fields.keys()) == expected_fields

    def test_flow_summary_with_complex_data(self) -> None:
        """Test FlowSummary with more complex data structures."""
        edge_flow = {
            ("datacenter_1", "edge_1", "link_1"): 100.0,
            ("datacenter_1", "edge_2", "link_2"): 75.0,
            ("edge_1", "customer_1", "access_1"): 50.0,
            ("edge_2", "customer_2", "access_2"): 25.0,
        }

        residual_cap = {
            ("datacenter_1", "edge_1", "link_1"): 0.0,  # Saturated
            ("datacenter_1", "edge_2", "link_2"): 25.0,
            ("edge_1", "customer_1", "access_1"): 50.0,
            ("edge_2", "customer_2", "access_2"): 75.0,
        }

        reachable = {"datacenter_1", "edge_1", "edge_2"}
        min_cut = [("datacenter_1", "edge_1", "link_1")]

        summary = FlowSummary(
            total_flow=175.0,
            edge_flow=edge_flow,
            residual_cap=residual_cap,
            reachable=reachable,
            min_cut=min_cut,
        )

        # Verify all data is accessible
        assert summary.total_flow == 175.0
        assert len(summary.edge_flow) == 4
        assert len(summary.residual_cap) == 4
        assert len(summary.reachable) == 3
        assert len(summary.min_cut) == 1

        # Check specific values
        assert summary.edge_flow[("datacenter_1", "edge_1", "link_1")] == 100.0
        assert summary.residual_cap[("datacenter_1", "edge_1", "link_1")] == 0.0
        assert "datacenter_1" in summary.reachable
        assert ("datacenter_1", "edge_1", "link_1") in summary.min_cut

    def test_flow_summary_empty_collections(self) -> None:
        """Test FlowSummary with empty collections."""
        summary = FlowSummary(
            total_flow=0.0,
            edge_flow={},
            residual_cap={},
            reachable=set(),
            min_cut=[],
        )

        assert summary.total_flow == 0.0
        assert len(summary.edge_flow) == 0
        assert len(summary.residual_cap) == 0
        assert len(summary.reachable) == 0
        assert len(summary.min_cut) == 0
