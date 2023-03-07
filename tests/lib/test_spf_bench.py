# pylint: disable=protected-access,invalid-name
import pytest
from ngraph.lib.graph import MultiDiGraph
from ngraph.lib.spf import spf
import networkx as nx


@pytest.fixture
def graph3():
    # Metric:
    #  ┌────────►E─────────┐
    #  │ [1]        [1]    │
    #  │                   │
    #  │                   ▼   [1]
    #  A────────►B────────►C──────┐
    #  │ [1,1,1]   [1,1,1] │      │
    #  │                   │      ▼
    #  │                   │[2]   F
    #  │                   │      │
    #  │                   │      │
    #  │   [4]             ▼      │[1]
    #  └──────────────────►D◄─────┘
    #
    # Capacity:
    #  ┌────────►E─────────┐
    #  │ [5]        [4]    │
    #  │                   │
    #  │                   ▼   [1]
    #  A────────►B────────►C──────┐
    #  │ [2,4,6]   [1,2,3] │      │
    #  │                   │      ▼
    #  │                   │[3]   F
    #  │                   │      │
    #  │                   │      │
    #  │   [2]             ▼      │[2]
    #  └──────────────────►D◄─────┘

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("A", "B", metric=1, capacity=4)
    g.add_edge("A", "B", metric=1, capacity=6)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "D", metric=2, capacity=3)
    g.add_edge("A", "E", metric=1, capacity=5)
    g.add_edge("E", "C", metric=1, capacity=4)
    g.add_edge("A", "D", metric=4, capacity=2)
    g.add_edge("C", "F", metric=1, capacity=1)
    g.add_edge("F", "D", metric=1, capacity=2)
    return g


@pytest.fixture
def graph3_nx():
    # Metric:
    #  ┌────────►E─────────┐
    #  │ [1]        [1]    │
    #  │                   │
    #  │                   ▼   [1]
    #  A────────►B────────►C──────┐
    #  │ [1,1,1]   [1,1,1] │      │
    #  │                   │      ▼
    #  │                   │[2]   F
    #  │                   │      │
    #  │                   │      │
    #  │   [4]             ▼      │[1]
    #  └──────────────────►D◄─────┘
    #
    # Capacity:
    #  ┌────────►E─────────┐
    #  │ [5]        [4]    │
    #  │                   │
    #  │                   ▼   [1]
    #  A────────►B────────►C──────┐
    #  │ [2,4,6]   [1,2,3] │      │
    #  │                   │      ▼
    #  │                   │[3]   F
    #  │                   │      │
    #  │                   │      │
    #  │   [2]             ▼      │[2]
    #  └──────────────────►D◄─────┘

    g = nx.MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("A", "B", metric=1, capacity=4)
    g.add_edge("A", "B", metric=1, capacity=6)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "D", metric=2, capacity=3)
    g.add_edge("A", "E", metric=1, capacity=5)
    g.add_edge("E", "C", metric=1, capacity=4)
    g.add_edge("A", "D", metric=4, capacity=2)
    g.add_edge("C", "F", metric=1, capacity=1)
    g.add_edge("F", "D", metric=1, capacity=2)
    return g


def test_spf_bench_1(benchmark, graph3):
    benchmark(spf, graph3, "A")


def test_spf_bench_2(benchmark, graph3_nx):
    benchmark(nx.dijkstra_predecessor_and_distance, graph3_nx, "A", weight="metric")
