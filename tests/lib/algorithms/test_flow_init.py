"""Tests for lib.algorithms.flow_init module."""

from ngraph.lib.algorithms.flow_init import init_flow_graph
from ngraph.lib.graph import StrictMultiDiGraph


class TestInitFlowGraph:
    """Test init_flow_graph function."""

    def test_init_flow_graph_basic(self) -> None:
        """Test basic flow graph initialization."""
        # Create a simple graph
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", key="edge1", capacity=100)

        # Initialize flow graph
        result = init_flow_graph(graph)

        # Should return the same graph object
        assert result is graph

        # Check node attributes
        nodes = graph.get_nodes()
        assert "flow" in nodes["A"]
        assert "flows" in nodes["A"]
        assert nodes["A"]["flow"] == 0
        assert nodes["A"]["flows"] == {}

        assert "flow" in nodes["B"]
        assert "flows" in nodes["B"]
        assert nodes["B"]["flow"] == 0
        assert nodes["B"]["flows"] == {}

        # Check edge attributes - edges are keyed by string, value is tuple
        edges = graph.get_edges()
        edge_data = edges["edge1"]  # Key is just the string
        attrs = edge_data[3]  # Fourth element is the attribute dict
        assert "flow" in attrs
        assert "flows" in attrs
        assert attrs["flow"] == 0
        assert attrs["flows"] == {}

    def test_init_flow_graph_custom_attributes(self) -> None:
        """Test flow graph initialization with custom attribute names."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", key="edge1", capacity=100)

        # Use custom attribute names
        init_flow_graph(graph, flow_attr="total_flow", flows_attr="flow_dict")

        # Check custom attributes exist
        nodes = graph.get_nodes()
        assert "total_flow" in nodes["A"]
        assert "flow_dict" in nodes["A"]
        assert nodes["A"]["total_flow"] == 0
        assert nodes["A"]["flow_dict"] == {}

        edges = graph.get_edges()
        edge_data = edges["edge1"]
        attrs = edge_data[3]
        assert "total_flow" in attrs
        assert "flow_dict" in attrs
        assert attrs["total_flow"] == 0
        assert attrs["flow_dict"] == {}

    def test_init_flow_graph_reset_behavior(self) -> None:
        """Test flow graph initialization reset behavior."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", key="edge1")

        # First initialization
        init_flow_graph(graph)

        # Modify values manually
        nodes = graph.get_nodes()
        nodes["A"]["flow"] = 50
        nodes["A"]["flows"] = {"f1": 25}

        edges = graph.get_edges()
        edge_data = edges["edge1"]
        attrs = edge_data[3]
        attrs["flow"] = 30
        attrs["flows"] = {"f2": 15}

        # Re-initialize with reset (default)
        init_flow_graph(graph, reset_flow_graph=True)

        # Should reset to zero
        assert nodes["A"]["flow"] == 0
        assert nodes["A"]["flows"] == {}
        assert attrs["flow"] == 0
        assert attrs["flows"] == {}

    def test_init_flow_graph_no_reset(self) -> None:
        """Test flow graph initialization without reset."""
        graph = StrictMultiDiGraph()
        graph.add_node("A")
        graph.add_node("B")
        graph.add_edge("A", "B", key="edge1")

        # First initialization
        init_flow_graph(graph)

        # Modify values manually
        nodes = graph.get_nodes()
        nodes["A"]["flow"] = 50
        nodes["A"]["flows"] = {"f1": 25}

        edges = graph.get_edges()
        edge_data = edges["edge1"]
        attrs = edge_data[3]
        attrs["flow"] = 30
        attrs["flows"] = {"f2": 15}

        # Re-initialize without reset
        init_flow_graph(graph, reset_flow_graph=False)

        # Should preserve existing values
        assert nodes["A"]["flow"] == 50
        assert nodes["A"]["flows"] == {"f1": 25}
        assert attrs["flow"] == 30
        assert attrs["flows"] == {"f2": 15}

    def test_init_flow_graph_empty_graph(self) -> None:
        """Test flow graph initialization on empty graph."""
        graph = StrictMultiDiGraph()

        result = init_flow_graph(graph)

        # Should return the same empty graph
        assert result is graph
        assert len(graph.get_nodes()) == 0
        assert len(graph.get_edges()) == 0
