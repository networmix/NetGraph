# NetGraph

This library is developed to help with network modeling and capacity analysis use-cases. The graph implementation in this library is largely compatible with [NetworkX](https://networkx.org/) while making edges first-class entities. Making edges explicitly addressable is important in traffic engineering applications.

The lib provides the following main primitives:
- [MultiDiGraph](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/graph.py#L14)
- [Demand](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L108)
- [FlowPolicy](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L37)

Besides, it provides a number of path finding and capacity calculation functions that can be used independently.

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