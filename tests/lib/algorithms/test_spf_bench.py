import random
import pytest
import networkx as nx

from ngraph.lib.graph import StrictMultiDiGraph
from ngraph.lib.algorithms.spf import spf

random.seed(0)


def create_complex_graph(num_nodes: int, num_edges: int):
    """
    Create a random directed graph with parallel edges.
    Args:
        num_nodes: Number of nodes.
        num_edges: Number of edges to add.
                   For each iteration, we add 4 edges, so we iterate num_edges/4 times.
    Returns:
        (node_labels, edges) where edges is a list of tuples:
            (src, dst, cost, capacity).
    """
    node_labels = [str(i) for i in range(num_nodes)]
    edges = []
    edges_added = 0
    while edges_added < num_edges // 4:
        src = random.choice(node_labels)
        tgt = random.choice(node_labels)
        if src == tgt:
            #  skip self-loops
            continue
        # Add four parallel edges from src->tgt with random cost/capacity
        for _ in range(4):
            cost = random.randint(1, 10)
            cap = random.randint(1, 5)
            edges.append((src, tgt, cost, cap))
        edges_added += 1
    return node_labels, edges


@pytest.fixture
def graph1():
    """
    Build both:
      - StrictMultiDiGraph 'g' (our custom graph)
      - NetworkX StrictMultiDiGraph 'gnx'
    Then return (g, gnx).
    """
    num_nodes = 100
    num_edges = 10000  # effectively 10k edges, but we add them in groups of 4
    node_labels, edges = create_complex_graph(num_nodes, num_edges)

    g = StrictMultiDiGraph()
    gnx = nx.MultiDiGraph()

    # Add nodes
    for node in node_labels:
        g.add_node(node)
        gnx.add_node(node)

    # Add edges to both graphs
    for src, dst, cost, cap in edges:
        # Our custom graph
        g.add_edge(src, dst, cost=cost, capacity=cap)
        # NetworkX
        gnx.add_edge(src, dst, cost=cost, capacity=cap)

    return g, gnx


def test_bench_ngraph_spf_1(benchmark, graph1):
    """
    Benchmark our custom SPF on 'graph1[0]', starting from node "0".
    """

    def run_spf():
        spf(graph1[0], "0")

    benchmark(run_spf)


def test_bench_networkx_spf_1(benchmark, graph1):
    """
    Benchmark NetworkX's built-in Dijkstra on 'graph1[1]', starting from node "0".
    """

    def run_nx_dijkstra():
        nx.dijkstra_predecessor_and_distance(graph1[1], "0", weight="cost")

    benchmark(run_nx_dijkstra)
