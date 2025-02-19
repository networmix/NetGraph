def test_example_1():
    # Required imports
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.max_flow import calc_max_flow

    # Create a graph with parallel edges
    # Metric:
    #      [1,1]      [1,1]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [2]        [2]  │
    #   └────────►D─────────┘
    #
    # Capacity:
    #      [1,2]      [1,2]
    #   ┌────────►B─────────┐
    #   │                   │
    #   │                   ▼
    #   A                   C
    #   │                   ▲
    #   │   [3]        [3]  │
    #   └────────►D─────────┘

    g = StrictMultiDiGraph()
    # Explicitly add nodes
    for node in ["A", "B", "C", "D"]:
        g.add_node(node)
    # Add edges with explicit keys (0, 1, 2, ...)
    g.add_edge("A", "B", key=0, metric=1, capacity=1)
    g.add_edge("B", "C", key=1, metric=1, capacity=1)
    g.add_edge("A", "B", key=2, metric=1, capacity=2)
    g.add_edge("B", "C", key=3, metric=1, capacity=2)
    g.add_edge("A", "D", key=4, metric=2, capacity=3)
    g.add_edge("D", "C", key=5, metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    max_flow = calc_max_flow(g, "A", "C")

    # We can verify that the result is as expected
    assert max_flow == 6.0


def test_example_2():
    # Required imports
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.max_flow import calc_max_flow

    # Create a graph with parallel edges
    # Metric and Capacity same as in Example 1
    g = StrictMultiDiGraph()
    # Explicitly add nodes
    for node in ["A", "B", "C", "D"]:
        g.add_node(node)
    # Add edges with explicit keys
    g.add_edge("A", "B", key=0, metric=1, capacity=1)
    g.add_edge("B", "C", key=1, metric=1, capacity=1)
    g.add_edge("A", "B", key=2, metric=1, capacity=2)
    g.add_edge("B", "C", key=3, metric=1, capacity=2)
    g.add_edge("A", "D", key=4, metric=2, capacity=3)
    g.add_edge("D", "C", key=5, metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    # Flows will be placed only on the shortest paths
    max_flow = calc_max_flow(g, "A", "C", shortest_path=True)

    # We can verify that the result is as expected
    assert max_flow == 3.0


def test_example_3():
    # Required imports
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.max_flow import calc_max_flow
    from ngraph.lib.algorithms.base import FlowPlacement

    # Create a graph with parallel edges
    # Metric and Capacity same as in Example 1
    g = StrictMultiDiGraph()
    # Explicitly add nodes
    for node in ["A", "B", "C", "D"]:
        g.add_node(node)
    # Add edges with explicit keys
    g.add_edge("A", "B", key=0, metric=1, capacity=1)
    g.add_edge("B", "C", key=1, metric=1, capacity=1)
    g.add_edge("A", "B", key=2, metric=1, capacity=2)
    g.add_edge("B", "C", key=3, metric=1, capacity=2)
    g.add_edge("A", "D", key=4, metric=2, capacity=3)
    g.add_edge("D", "C", key=5, metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    # Flows will be equally balanced across the shortest paths
    max_flow = calc_max_flow(
        g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
    )

    # We can verify that the result is as expected
    assert max_flow == 2.0


def test_example_4():
    # Required imports
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.flow_init import init_flow_graph
    from ngraph.lib.demand import FlowPolicyConfig, Demand, get_flow_policy
    from ngraph.lib.flow import FlowIndex

    # Create a graph
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

    g = StrictMultiDiGraph()
    # Explicitly add nodes
    for node in ["A", "B", "C"]:
        g.add_node(node)
    # Add edges with explicit keys
    g.add_edge("A", "B", key=0, metric=1, capacity=15, label="1")
    g.add_edge("B", "A", key=1, metric=1, capacity=15, label="1")
    g.add_edge("B", "C", key=2, metric=1, capacity=15, label="2")
    g.add_edge("C", "B", key=3, metric=1, capacity=15, label="2")
    g.add_edge("A", "C", key=4, metric=1, capacity=5, label="3")
    g.add_edge("C", "A", key=5, metric=1, capacity=5, label="3")

    # Initialize a flow graph
    r = init_flow_graph(g)

    # Create traffic demands
    demands = [
        Demand("A", "C", 20),
        Demand("C", "A", 20),
    ]

    # Place traffic demands onto the flow graph
    for demand in demands:
        # Create a flow policy or use a predefined one from FlowPolicyConfig
        flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
        demand.place(r, flow_policy)

    # We can verify that all demands were placed as expected
    for demand in demands:
        assert demand.placed_demand == 20

    # Verify the final state of edges in the flow graph
    assert r.get_edges() == {
        0: (
            "A",
            "B",
            0,
            {
                "capacity": 15,
                "flow": 15.0,
                "flows": {
                    FlowIndex(src_node="A", dst_node="C", flow_class=0, flow_id=1): 15.0
                },
                "label": "1",
                "metric": 1,
            },
        ),
        1: (
            "B",
            "A",
            1,
            {
                "capacity": 15,
                "flow": 15.0,
                "flows": {
                    FlowIndex(src_node="C", dst_node="A", flow_class=0, flow_id=1): 15.0
                },
                "label": "1",
                "metric": 1,
            },
        ),
        2: (
            "B",
            "C",
            2,
            {
                "capacity": 15,
                "flow": 15.0,
                "flows": {
                    FlowIndex(src_node="A", dst_node="C", flow_class=0, flow_id=1): 15.0
                },
                "label": "2",
                "metric": 1,
            },
        ),
        3: (
            "C",
            "B",
            3,
            {
                "capacity": 15,
                "flow": 15.0,
                "flows": {
                    FlowIndex(src_node="C", dst_node="A", flow_class=0, flow_id=1): 15.0
                },
                "label": "2",
                "metric": 1,
            },
        ),
        4: (
            "A",
            "C",
            4,
            {
                "capacity": 5,
                "flow": 5.0,
                "flows": {
                    FlowIndex(src_node="A", dst_node="C", flow_class=0, flow_id=0): 5.0
                },
                "label": "3",
                "metric": 1,
            },
        ),
        5: (
            "C",
            "A",
            5,
            {
                "capacity": 5,
                "flow": 5.0,
                "flows": {
                    FlowIndex(src_node="C", dst_node="A", flow_class=0, flow_id=0): 5.0
                },
                "label": "3",
                "metric": 1,
            },
        ),
    }
