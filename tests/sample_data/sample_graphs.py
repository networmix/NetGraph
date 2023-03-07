import pytest

from ngraph.lib.graph import MultiDiGraph


@pytest.fixture
def line1():
    # Metric:
    #      [1]      [1,1,2]
    #  A◄───────►B◄───────►C
    #
    # Capacity:
    #     [5]      [1,3,7]
    #  A◄───────►B◄───────►C

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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=15, label="1")
    g.add_edge("B", "A", metric=1, capacity=15, label="1")
    g.add_edge("B", "C", metric=1, capacity=15, label="2")
    g.add_edge("C", "B", metric=1, capacity=15, label="2")
    g.add_edge("A", "C", metric=1, capacity=5, label="3")
    g.add_edge("C", "A", metric=1, capacity=5, label="3")
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
    # Capacity:
    #       [1]        [1]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [2]        [2]  │
    #   └────────►D─────────┘

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)
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
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=2)
    g.add_edge("D", "C", metric=1, capacity=2)
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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=100)
    g.add_edge("B", "C", metric=1, capacity=125)
    g.add_edge("A", "D", metric=1, capacity=75)
    g.add_edge("D", "C", metric=1, capacity=50)
    g.add_edge("B", "D", metric=1, capacity=50)
    g.add_edge("D", "B", metric=1, capacity=50)
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
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=100)
    g.add_edge("B", "C", metric=1, capacity=125)
    g.add_edge("A", "D", metric=1, capacity=75)
    g.add_edge("D", "C", metric=1, capacity=50)
    g.add_edge("B", "D", metric=1, capacity=50)
    g.add_edge("D", "B", metric=1, capacity=50)
    g.add_edge("A", "B", metric=2, capacity=200)
    g.add_edge("B", "D", metric=2, capacity=200)
    g.add_edge("D", "C", metric=2, capacity=200)
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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("D", "E", metric=1, capacity=1)
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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("D", "C", metric=1, capacity=1)
    g.add_edge("C", "E", metric=1, capacity=1)
    g.add_edge("D", "E", metric=1, capacity=1)
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

    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "B1", metric=2, capacity=2)
    g.add_edge("B1", "C", metric=2, capacity=2)
    g.add_edge("A", "B2", metric=3, capacity=3)
    g.add_edge("B2", "C", metric=3, capacity=3)
    return g


@pytest.fixture
def graph5():
    """Fully connected graph with 5 nodes"""
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("A", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=1, capacity=1)
    g.add_edge("A", "E", metric=1, capacity=1)
    g.add_edge("B", "A", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("B", "D", metric=1, capacity=1)
    g.add_edge("B", "E", metric=1, capacity=1)
    g.add_edge("C", "A", metric=1, capacity=1)
    g.add_edge("C", "B", metric=1, capacity=1)
    g.add_edge("C", "D", metric=1, capacity=1)
    g.add_edge("C", "E", metric=1, capacity=1)
    g.add_edge("D", "A", metric=1, capacity=1)
    g.add_edge("D", "B", metric=1, capacity=1)
    g.add_edge("D", "C", metric=1, capacity=1)
    g.add_edge("D", "E", metric=1, capacity=1)
    g.add_edge("E", "A", metric=1, capacity=1)
    g.add_edge("E", "B", metric=1, capacity=1)
    g.add_edge("E", "C", metric=1, capacity=1)
    g.add_edge("E", "D", metric=1, capacity=1)
    return g
