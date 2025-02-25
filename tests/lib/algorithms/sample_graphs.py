import pytest

from ngraph.lib.graph import StrictMultiDiGraph


@pytest.fixture
def line1():
    # Metric:
    #      [1]      [1,1,2]
    #  A◄───────►B◄───────►C
    #
    # Capacity:
    #     [5]      [1,3,7]
    #  A◄───────►B◄───────►C
    #

    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")

    g.add_edge("A", "B", key=0, cost=1, capacity=5)
    g.add_edge("B", "A", key=1, cost=1, capacity=5)
    g.add_edge("B", "C", key=2, cost=1, capacity=1)
    g.add_edge("C", "B", key=3, cost=1, capacity=1)
    g.add_edge("B", "C", key=4, cost=1, capacity=3)
    g.add_edge("C", "B", key=5, cost=1, capacity=3)
    g.add_edge("B", "C", key=6, cost=2, capacity=7)
    g.add_edge("C", "B", key=7, cost=2, capacity=7)
    return g


@pytest.fixture
def triangle1():
    # Metric:
    #     [1]        [1]
    #   ┌──────►B◄──────┐
    #   │               │
    #   │               │
    #   │               │
    #   ▼      [1]      ▼
    #   A◄─────────────►C
    #
    # Capacity:
    #     [15]      [15]
    #   ┌──────►B◄──────┐
    #   │               │
    #   │               │
    #   │               │
    #   ▼      [5]      ▼
    #   A◄─────────────►C
    #

    g = StrictMultiDiGraph()
    g.add_node("A")
    g.add_node("B")
    g.add_node("C")

    g.add_edge("A", "B", key=0, cost=1, capacity=15, label="1")
    g.add_edge("B", "A", key=1, cost=1, capacity=15, label="1")
    g.add_edge("B", "C", key=2, cost=1, capacity=15, label="2")
    g.add_edge("C", "B", key=3, cost=1, capacity=15, label="2")
    g.add_edge("A", "C", key=4, cost=1, capacity=5, label="3")
    g.add_edge("C", "A", key=5, cost=1, capacity=5, label="3")
    return g


@pytest.fixture
def square1():
    # Metric:
    #       [1]        [1]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [2]        [2]  │
    #   └────────►D─────────┘
    #
    # Capacity is similar (1,1,2,2).

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("B", "C", key=1, cost=1, capacity=1)
    g.add_edge("A", "D", key=2, cost=2, capacity=2)
    g.add_edge("D", "C", key=3, cost=2, capacity=2)
    return g


@pytest.fixture
def square2():
    # Metric:
    #       [1]        [1]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [1]        [1]  │
    #   └────────►D─────────┘
    #
    # Capacity:
    #       [1]        [1]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [2]        [2]  │
    #   └────────►D─────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("B", "C", key=1, cost=1, capacity=1)
    g.add_edge("A", "D", key=2, cost=1, capacity=2)
    g.add_edge("D", "C", key=3, cost=1, capacity=2)
    return g


@pytest.fixture
def square3():
    # Metric:
    #       [1]        [1]
    #   ┌────────►B─────────┐
    #   │         ▲         │
    #   │         │         ▼
    #   A         │[1]      C
    #   │         │         ▲
    #   │   [1]   ▼    [1]  │
    #   └────────►D─────────┘
    #
    # Capacity:
    #     [100]       [125]
    #   ┌────────►B─────────┐
    #   │         ▲         │
    #   │         │         ▼
    #   A         │[50]     C
    #   │         │         ▲
    #   │  [75]   ▼   [50]  │
    #   └────────►D─────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=100)
    g.add_edge("B", "C", key=1, cost=1, capacity=125)
    g.add_edge("A", "D", key=2, cost=1, capacity=75)
    g.add_edge("D", "C", key=3, cost=1, capacity=50)
    g.add_edge("B", "D", key=4, cost=1, capacity=50)
    g.add_edge("D", "B", key=5, cost=1, capacity=50)
    return g


@pytest.fixture
def square4():
    # Metric:
    #      [1,2]      [1]
    #   ┌────────►B──────────┐
    #   │         │▲         │
    #   │         ││         ▼
    #   A      [2]││[1]      C
    #   │         ││         ▲
    #   │   [1]   ▼▼  [1,2]  │
    #   └────────►D──────────┘
    #
    # Capacity:
    #    [100,200]    [125]
    #   ┌────────►B──────────┐
    #   │         │▲         │
    #   │         ││         ▼
    #   A         ││[50,200] C
    #   │         ││         ▲
    #   │  [75]   ▼▼ [50,200]│
    #   └────────►D──────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=100)
    g.add_edge("B", "C", key=1, cost=1, capacity=125)
    g.add_edge("A", "D", key=2, cost=1, capacity=75)
    g.add_edge("D", "C", key=3, cost=1, capacity=50)
    g.add_edge("B", "D", key=4, cost=1, capacity=50)
    g.add_edge("D", "B", key=5, cost=1, capacity=50)
    g.add_edge("A", "B", key=6, cost=2, capacity=200)
    g.add_edge("B", "D", key=7, cost=2, capacity=200)
    g.add_edge("D", "C", key=8, cost=2, capacity=200)
    return g


@pytest.fixture
def square5():
    # Metric:
    #      [1]        [1]
    #  ┌────────►B─────────┐
    #  │         ▲         │
    #  │         │         ▼
    #  A         │[1]      D
    #  │         │         ▲
    #  │   [1]   ▼    [1]  │
    #  └────────►C─────────┘
    #
    # Capacity:
    #      [1]        [1]
    #  ┌────────►B─────────┐
    #  │         ▲         │
    #  │         │         ▼
    #  A         │[1]      D
    #  │         │         ▲
    #  │   [1]   ▼    [1]  │
    #  └────────►C─────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("A", "C", key=1, cost=1, capacity=1)
    g.add_edge("B", "D", key=2, cost=1, capacity=1)
    g.add_edge("C", "D", key=3, cost=1, capacity=1)
    g.add_edge("B", "C", key=4, cost=1, capacity=1)
    g.add_edge("C", "B", key=5, cost=1, capacity=1)
    return g


@pytest.fixture
def graph1():
    # Metric:
    #      [1]        [1]
    #  ┌────────►B─────────┐
    #  │         ▲         │
    #  │         │         ▼   [1]
    #  A         │[1]      D────────►E
    #  │         │         ▲
    #  │   [1]   ▼    [1]  │
    #  └────────►C─────────┘
    #
    # Capacity:
    #      [1]        [1]
    #  ┌────────►B─────────┐
    #  │         ▲         │
    #  │         │         ▼   [1]
    #  A         │[1]      D────────►E
    #  │         │         ▲
    #  │   [1]   ▼    [1]  │
    #  └────────►C─────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D", "E"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("A", "C", key=1, cost=1, capacity=1)
    g.add_edge("B", "D", key=2, cost=1, capacity=1)
    g.add_edge("C", "D", key=3, cost=1, capacity=1)
    g.add_edge("B", "C", key=4, cost=1, capacity=1)
    g.add_edge("C", "B", key=5, cost=1, capacity=1)
    g.add_edge("D", "E", key=6, cost=1, capacity=1)
    return g


@pytest.fixture
def graph2():
    # Metric:
    #            [1]        [1]
    #        ┌────────►C─────────┐
    #        │         ▲         │
    #   [1]  │         │         ▼
    # A─────►B         │[1]      E
    #        │         │         ▲
    #        │   [1]   ▼    [1]  │
    #        └────────►D─────────┘
    #
    # Capacity:
    #            [1]        [1]
    #        ┌────────►C─────────┐
    #        │         ▲         │
    #   [1]  │         │         ▼
    # A─────►B         │[1]      E
    #        │         │         ▲
    #        │   [1]   ▼    [1]  │
    #        └────────►D─────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D", "E"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("B", "C", key=1, cost=1, capacity=1)
    g.add_edge("B", "D", key=2, cost=1, capacity=1)
    g.add_edge("C", "D", key=3, cost=1, capacity=1)
    g.add_edge("D", "C", key=4, cost=1, capacity=1)
    g.add_edge("C", "E", key=5, cost=1, capacity=1)
    g.add_edge("D", "E", key=6, cost=1, capacity=1)
    return g


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
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D", "E", "F"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=2)
    g.add_edge("A", "B", key=1, cost=1, capacity=4)
    g.add_edge("A", "B", key=2, cost=1, capacity=6)
    g.add_edge("B", "C", key=3, cost=1, capacity=1)
    g.add_edge("B", "C", key=4, cost=1, capacity=2)
    g.add_edge("B", "C", key=5, cost=1, capacity=3)
    g.add_edge("C", "D", key=6, cost=2, capacity=3)
    g.add_edge("A", "E", key=7, cost=1, capacity=5)
    g.add_edge("E", "C", key=8, cost=1, capacity=4)
    g.add_edge("A", "D", key=9, cost=4, capacity=2)
    g.add_edge("C", "F", key=10, cost=1, capacity=1)
    g.add_edge("F", "D", key=11, cost=1, capacity=2)
    return g


@pytest.fixture
def graph4():
    # Metric:
    #     [1]        [1]
    #  ┌────────►B─────────┐
    #  │                   │
    #  │   [2]        [2]  ▼
    #  A────────►B1───────►C
    #  │                   ▲
    #  │   [3]        [3]  │
    #  └────────►B2────────┘
    #
    # Capacity:
    #     [1]        [1]
    #  ┌────────►B─────────┐
    #  │                   │
    #  │   [2]        [2]  ▼
    #  A────────►B1───────►C
    #  │                   ▲
    #  │   [3]        [3]  │
    #  └────────►B2────────┘
    #

    g = StrictMultiDiGraph()
    for node in ("A", "B", "B1", "B2", "C"):
        g.add_node(node)

    g.add_edge("A", "B", key=0, cost=1, capacity=1)
    g.add_edge("B", "C", key=1, cost=1, capacity=1)
    g.add_edge("A", "B1", key=2, cost=2, capacity=2)
    g.add_edge("B1", "C", key=3, cost=2, capacity=2)
    g.add_edge("A", "B2", key=4, cost=3, capacity=3)
    g.add_edge("B2", "C", key=5, cost=3, capacity=3)
    return g


@pytest.fixture
def graph5():
    """Fully connected graph with 5 nodes, each edge has cost=1, capacity=1."""
    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D", "E"):
        g.add_node(node)

    edge_id = 0
    nodes = ["A", "B", "C", "D", "E"]
    for src in nodes:
        for dst in nodes:
            if src != dst:
                g.add_edge(src, dst, key=edge_id, cost=1, capacity=1)
                edge_id += 1

    return g
