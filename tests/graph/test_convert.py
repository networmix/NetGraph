import networkx as nx

from ngraph.graph.convert import from_digraph, from_graph, to_digraph, to_graph
from ngraph.graph.strict_multidigraph import StrictMultiDiGraph


def build_sample_graph() -> StrictMultiDiGraph:
    graph = StrictMultiDiGraph()
    graph.add_node("A")
    graph.add_node("B")
    e1 = graph.add_edge("A", "B", weight=1)
    e2 = graph.add_edge("A", "B", weight=3)
    assert e1 != e2
    return graph


def test_to_digraph_basic_and_revertible():
    g = build_sample_graph()
    nxg = to_digraph(g)

    assert isinstance(nxg, nx.DiGraph)
    assert nxg.has_edge("A", "B")

    # Revertible data preserved
    uv_edges = nxg.edges["A", "B"].get("_uv_edges")
    assert isinstance(uv_edges, list) and len(uv_edges) == 1
    (u, v, edges_dict) = uv_edges[0]
    assert (u, v) == ("A", "B")
    assert isinstance(edges_dict, dict) and len(edges_dict) == 2


def test_from_digraph_roundtrip():
    g = build_sample_graph()
    nxg = to_digraph(g)
    roundtrip = from_digraph(nxg)

    # Expect two edges restored
    edges = roundtrip.get_edges()
    assert len(edges) == 2
    # Validate endpoints are correct
    for _, (src, dst, _, _) in edges.items():
        assert (src, dst) == ("A", "B")


def test_to_graph_undirected_and_revertible():
    g = build_sample_graph()
    nxg = to_graph(g)

    assert isinstance(nxg, nx.Graph)
    assert nxg.has_edge("A", "B")
    uv_edges = nxg.edges["A", "B"].get("_uv_edges")
    assert isinstance(uv_edges, list) and len(uv_edges) == 1
    (u, v, edges_dict) = uv_edges[0]
    # For undirected graphs, order may vary; compare as set
    assert {u, v} == {"A", "B"}
    assert isinstance(edges_dict, dict) and len(edges_dict) == 2


def test_edge_func_applied_in_conversion():
    g = build_sample_graph()

    def edge_func(graph: StrictMultiDiGraph, u, v, edges: dict) -> dict:
        # Sum the weights of all parallel edges
        weight_sum = 0
        for _edge_id, attr in edges.items():
            weight_sum += int(attr.get("weight", 0))
        return {"weight_sum": weight_sum}

    nxg = to_digraph(g, edge_func=edge_func)
    assert nxg.edges["A", "B"]["weight_sum"] == 4


def test_from_graph_roundtrip():
    g = build_sample_graph()
    nxg = to_graph(g)
    roundtrip = from_graph(nxg)

    edges = roundtrip.get_edges()
    assert len(edges) == 2
    for _, (src, dst, _, _) in edges.items():
        assert (src, dst) == ("A", "B")
