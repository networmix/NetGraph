# NetGraph

- [Introduction](#introduction)
- [Use Case Examples](#use-case-examples)
  - [Calculate MaxFlow in a graph](#calculate-maxflow-in-a-graph)
  - [Place traffic demands on a graph](#place-traffic-demands-on-a-graph)
  - [Perform basic capacity analysis](#perform-basic-capacity-analysis)

---

## Introduction
This library is developed to help with network modeling and capacity analysis use-cases. The graph implementation in this library is largely compatible with [NetworkX](https://networkx.org/) while making edges first-class entities. Making edges explicitly addressable is important in traffic engineering applications.

The lib provides the following main primitives:
- [MultiDiGraph](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/graph.py#L14)
- [Demand](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L108)
- [FlowPolicy](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L37)

Besides, it provides a number of path finding and capacity calculation functions that can be used independently.

---
## Use Case Examples
### Calculate MaxFlow in a graph
- Calculate MaxFlow across all possible paths between the source and destination nodes
    ```python
    # Required imports
    from ngraph.graph import MultiDiGraph
    from ngraph.algorithms.calc_cap import calc_max_flow


    # Create a graph
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)

    # Calculate MaxFlow between the source and destination nodes
    max_flow = calc_max_flow(g, "A", "C")

    # We can verify that the result is as expected
    assert max_flow.max_total_flow == 3.0
    assert max_flow.max_single_flow == 2.0
    assert max_flow.max_balanced_flow == 2.0
    ```
- Calculate MaxFlow leveraging only the shortest paths between the source and destination nodes
    ```python
    # Required imports
    from ngraph.graph import MultiDiGraph
    from ngraph.algorithms.calc_cap import calc_max_flow


    # Create a graph
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "D", metric=2, capacity=2)
    g.add_edge("D", "C", metric=2, capacity=2)

    # Calculate MaxFlow between the source and destination nodes
    max_flow = calc_max_flow(g, "A", "C", shortest_path=True)

    # We can verify that the result is as expected
    assert max_flow.max_total_flow == 1.0
    assert max_flow.max_single_flow == 1.0
    assert max_flow.max_balanced_flow == 1.0
    ```
### Place traffic demands on a graph
- Place traffic demands leveraging all possible paths in a graph
    ```python
    from ngraph.graph import MultiDiGraph
    from ngraph.algorithms.common import init_flow_graph
    from ngraph.demand import FlowPolicyConfig, FLOW_POLICY_MAP, Demand


    # Create a graph
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=15, label="1")
    g.add_edge("B", "A", metric=1, capacity=15, label="1")
    g.add_edge("B", "C", metric=1, capacity=15, label="2")
    g.add_edge("C", "B", metric=1, capacity=15, label="2")
    g.add_edge("A", "C", metric=1, capacity=5, label="3")
    g.add_edge("C", "A", metric=1, capacity=5, label="3")

    # Initialize a flow graph
    r = init_flow_graph(g)

    # Create traffic demands
    demands = [
        Demand(
            "A",
            "B",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_1",
        ),
        Demand(
            "B",
            "A",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_1",
        ),
        Demand(
            "B",
            "C",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_2",
        ),
        Demand(
            "C",
            "B",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_2",
        ),
        Demand(
            "A",
            "C",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_3",
        ),
        Demand(
            "C",
            "A",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_3",
        ),
        ]

    # Place traffic demands onto the flow graph
    for demand in demands:
        demand.place(r)

    # We can verify that all demands were placed as expected 
    for demand in demands:
        assert demand.placed_flow == 10

    assert r.get_edges() == {
        0: (
            "A",
            "B",
            0,
            {
                "capacity": 15,
                "flow": 15.0,
                "flows": {
                    ("A", "B", "D_1"): 10.0,
                    ("A", "C", "D_3"): 5.0,
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
                    ("B", "A", "D_1"): 10.0,
                    ("C", "A", "D_3"): 5.0,
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
                    ("A", "C", "D_3"): 5.0,
                    ("B", "C", "D_2"): 10.0,
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
                    ("C", "A", "D_3"): 5.0,
                    ("C", "B", "D_2"): 10.0,
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
                "flows": {("A", "C", "D_3"): 5.0},
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
                "flows": {("C", "A", "D_3"): 5.0},
                "label": "3",
                "metric": 1,
            },
        ),
    }
    ```

### Perform basic capacity analysis
- Place traffic demands and analyze the results
    ```python
    from ngraph.graph import MultiDiGraph
    from ngraph.algorithms.common import init_flow_graph
    from ngraph.demand import FlowPolicyConfig, FLOW_POLICY_MAP, Demand
    from ngraph.analyser import Analyser


    # Create a graph
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=15, label="1")
    g.add_edge("B", "A", metric=1, capacity=15, label="1")
    g.add_edge("B", "C", metric=1, capacity=15, label="2")
    g.add_edge("C", "B", metric=1, capacity=15, label="2")
    g.add_edge("A", "C", metric=1, capacity=5, label="3")
    g.add_edge("C", "A", metric=1, capacity=5, label="3")

    # Initialize a flow graph
    r = init_flow_graph(g)

    # Create traffic demands
    demands = [
        Demand(
            "A",
            "B",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_1",
        ),
        Demand(
            "B",
            "A",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_1",
        ),
        Demand(
            "B",
            "C",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_2",
        ),
        Demand(
            "C",
            "B",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_2",
        ),
        Demand(
            "A",
            "C",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_3",
        ),
        Demand(
            "C",
            "A",
            10,
            FLOW_POLICY_MAP[FlowPolicyConfig.ALL_PATHS_PROPORTIONAL],
            label="D_3",
        ),
        ]

    # Place traffic demands onto the flow graph
    for demand in demands:
        demand.place(r)

    # Analayze graph and demands
    analyser = Analyser(r, demands)
    analyser.analyse()

    # We can check the analysis results
    assert analyser.demand_data[demands[0]].total_edge_cost_flow_product == 10.0
    assert analyser.demand_data[demands[0]].total_volume == 10.0
    assert analyser.demand_data[demands[0]].placed_demand == 10.0
    assert analyser.demand_data[demands[0]].unsatisfied_demand == 0

    assert analyser.graph_data.total_edge_cost_volume_product == 70.0
    assert analyser.graph_data.total_capacity == 70.0
    assert analyser.graph_data.total_flow == 70.0
    assert analyser.graph_data.avg_capacity_utilization == 1.0
    ```