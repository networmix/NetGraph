# pylint: disable=protected-access,invalid-name
import random

import pytest
from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.spf import spf
import networkx as nx


random.seed(0)


def create_complex_graph(num_nodes, num_edges):
    node_labels = [str(i) for i in range(num_nodes)]
    edges = []

    # Add edges until the desired number of edges is reached
    edges_added = 0
    while edges_added < num_edges / 4:
        # Randomly select source and target nodes from the list of labels
        src = random.choice(node_labels)
        tgt = random.choice(node_labels)

        # Add an edge with random metric and capacity
        edges.append((src, tgt, random.randint(1, 10), random.randint(1, 5)))
        edges.append((src, tgt, random.randint(1, 10), random.randint(1, 5)))
        edges.append((src, tgt, random.randint(1, 10), random.randint(1, 5)))
        edges.append((src, tgt, random.randint(1, 10), random.randint(1, 5)))
        edges_added += 1

    return node_labels, edges


@pytest.fixture
def graph1():
    g = MultiDiGraph()
    gnx = nx.MultiDiGraph()
    node_labels, edges = create_complex_graph(100, 10000)
    for node in node_labels:
        g.add_node(node)
        gnx.add_node(node)

    for edge in edges:
        g.add_edge(edge[0], edge[1], metric=edge[2], capacity=edge[3])
        gnx.add_edge(edge[0], edge[1], metric=edge[2], capacity=edge[3])

    return g, gnx


def test_bench_ngraph_spf_1(benchmark, graph1):
    benchmark(spf, graph1[0], "0")


def test_bench_networkx_spf_1(benchmark, graph1):
    benchmark(
        nx.dijkstra_predecessor_and_distance,
        graph1[1],
        "0",
        weight="metric",
    )
