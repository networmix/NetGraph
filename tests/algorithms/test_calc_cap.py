# pylint: disable=protected-access,invalid-name
import pytest

from ngraph.graph import MultiDiGraph
from ngraph.algorithms.common import init_flow_graph
from ngraph.algorithms.spf import spf
from ngraph.algorithms.calc_cap import (
    MaxFlow,
    NodeCapacity,
    calc_graph_cap,
)


@pytest.fixture
def line_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=5)
    g.add_edge("B", "A", metric=1, capacity=5)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=3)
    g.add_edge("C", "B", metric=1, capacity=3)
    g.add_edge("B", "C", metric=2, capacity=7)
    g.add_edge("C", "B", metric=2, capacity=7)
    return g


@pytest.fixture
def graph_1():
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
def graph_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("A", "B", metric=1, capacity=0)
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
def graph_square_1():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
    g.add_edge("A", "C", metric=3, capacity=3)
    return g


@pytest.fixture
def graph_square_2():
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=1)
    g.add_edge("D", "C", metric=1, capacity=2)
    g.add_edge("B", "D", metric=1, capacity=2)
    g.add_edge("D", "B", metric=1, capacity=2)
    return g


class TestGraphCapacity:
    def test_calc_graph_capacity_1(self, line_1):
        _, pred = spf(line_1, "A")
        r = init_flow_graph(line_1)

        max_flow, _ = calc_graph_cap(r, "A", "C", pred)
        assert max_flow == MaxFlow(
            max_total_flow=4, max_single_flow=3, max_balanced_flow=2.0
        )

    def test_calc_graph_capacity_2(self, graph_1):
        _, pred = spf(graph_1, "A")
        r = init_flow_graph(graph_1)

        max_flow, node_cap = calc_graph_cap(r, "A", "D", pred)
        assert max_flow == MaxFlow(
            max_total_flow=10, max_single_flow=3, max_balanced_flow=2.5
        )
        assert node_cap == {
            "A": NodeCapacity(
                node_id="A",
                edges={0, 1, 2, 7, 9},
                edges_max_flow={
                    (0, 1, 2): MaxFlow(
                        max_total_flow=4, max_single_flow=3, max_balanced_flow=2.0
                    ),
                    (7,): MaxFlow(
                        max_total_flow=4, max_single_flow=3, max_balanced_flow=2.0
                    ),
                    (9,): MaxFlow(
                        max_total_flow=2, max_single_flow=2, max_balanced_flow=2
                    ),
                },
                max_balanced_flow=3.333333333333333,
                max_single_flow=3,
                max_total_flow=10,
                downstream_nodes={
                    (0, 1, 2): {"C", "F", "B", "D"},
                    (7,): {"C", "F", "E", "D"},
                    (9,): {"D"},
                },
                flow_fraction_balanced=1,
                flow_fraction_total=1,
            ),
            "B": NodeCapacity(
                node_id="B",
                edges={3, 4, 5},
                edges_max_flow={
                    (3, 4, 5): MaxFlow(
                        max_total_flow=4, max_single_flow=3, max_balanced_flow=2.0
                    )
                },
                max_balanced_flow=2.0,
                max_single_flow=3,
                max_total_flow=4,
                downstream_nodes={(3, 4, 5): {"C", "F", "D"}},
                flow_fraction_balanced=0.6000000000000001,
                flow_fraction_total=0.4,
            ),
            "C": NodeCapacity(
                node_id="C",
                edges={10, 6},
                edges_max_flow={
                    (6,): MaxFlow(
                        max_total_flow=3, max_single_flow=3, max_balanced_flow=3
                    ),
                    (10,): MaxFlow(
                        max_total_flow=1, max_single_flow=1, max_balanced_flow=1
                    ),
                },
                max_balanced_flow=2.0,
                max_single_flow=3,
                max_total_flow=4,
                downstream_nodes={(6,): {"D"}, (10,): {"F", "D"}},
                flow_fraction_balanced=0.8,
                flow_fraction_total=0.8,
            ),
            "E": NodeCapacity(
                node_id="E",
                edges={8},
                edges_max_flow={
                    (8,): MaxFlow(
                        max_total_flow=4, max_single_flow=3, max_balanced_flow=2.0
                    )
                },
                max_balanced_flow=2.0,
                max_single_flow=3,
                max_total_flow=4,
                downstream_nodes={(8,): {"C", "F", "D"}},
                flow_fraction_balanced=0.2,
                flow_fraction_total=0.4,
            ),
            "F": NodeCapacity(
                node_id="F",
                edges={11},
                edges_max_flow={
                    (11,): MaxFlow(
                        max_total_flow=2, max_single_flow=2, max_balanced_flow=2
                    )
                },
                max_balanced_flow=2.0,
                max_single_flow=2,
                max_total_flow=2,
                downstream_nodes={(11,): {"D"}},
                flow_fraction_balanced=0.4,
                flow_fraction_total=0.2,
            ),
        }

    def test_calc_graph_capacity_3(self, graph_2):
        _, pred = spf(graph_2, "A")
        r = init_flow_graph(graph_2)

        max_flow, node_cap = calc_graph_cap(r, "A", "D", pred)
        assert max_flow == MaxFlow(
            max_total_flow=10, max_single_flow=3, max_balanced_flow=0
        )

    def test_calc_graph_capacity_4(self, graph_square_2):
        _, pred = spf(graph_square_2, "A")
        r = init_flow_graph(graph_square_2)

        max_flow, node_cap = calc_graph_cap(r, "A", "C", pred)
        assert max_flow == MaxFlow(
            max_total_flow=2, max_single_flow=1, max_balanced_flow=2
        )
