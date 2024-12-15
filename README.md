# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

- [Introduction](#introduction)
- [Installation and Usage](#installation-and-usage)
    - [Using the Docker Container with JupyterLab](#1-using-the-docker-container-with-jupyterlab)
    - [Using the Python Package](#2-using-the-python-package)
- [Use Case Examples](#use-case-examples)
    - [Calculate MaxFlow in a graph](#calculate-maxflow-in-a-graph)
    - [Place traffic demands on a graph](#place-traffic-demands-on-a-graph)
    - [Perform basic capacity analysis](#perform-basic-capacity-analysis)

---

## Introduction

This library is developed to help with network modeling and capacity analysis use-cases. The graph implementation in this library is a wrapper around MultiDiGraph of [NetworkX](https://networkx.org/). Our implementation makes edges explicitly addressable which is important in traffic engineering applications.

The lib provides the following main primitives:

- [MultiDiGraph](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/graph.py#L14)
- [Demand](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L108)
- [FlowPolicy](https://github.com/networmix/NetGraph/blob/07abd775c17490a9ffe102f9f54a871ea9772a96/ngraph/demand.py#L37)

Besides, it provides a number of path finding and capacity calculation functions that can be used independently.

---

## Installation and Usage

NetGraph can be used in two ways:

### 1. Using the Docker Container with JupyterLab Notebooks

**Prerequisites:**

- [Docker](https://docs.docker.com/get-docker/) installed on your machine.

**Steps:**

1. Clone the repository:

     ```bash
        git clone https://github.com/networmix/NetGraph
        ```

2. Build the Docker image:

     ```bash
        cd NetGraph
        ./run.sh build
        ```

3. Start the container with JupyterLab server:

     ```bash
        ./run.sh start
        ```

4. Open the JupyterLab URL in your browser:

     ```bash
        http://127.0.0.1:8788/
        ```

5. JupyterLab will show the content of `notebooks` directory and you can start using the provided notebooks or create your own.

Note: The Docker container will mount the `NetGraph` directory to the container, so any changes made to the code in the `NetGraph` directory will be reflected in the container and vice versa.

The ngraph package is installed in the container in editable mode, so you can make changes to the code and see the changes reflected immediately in the JupyterLab.

To exit the JupyterLab server, press `Ctrl+C` in the terminal where the server is running. To stop the remaining Docker container, run:

```bash
./run.sh stop
```

### 2. Using the Python Package

**Prerequisites:**

- Python 3.8 or higher installed on your machine.

Note: Don't forget to use a virtual environment (e.g., `venv`) to avoid conflicts with other Python packages. See [Python Virtual Environments](https://docs.python.org/3/library/venv.html) for more information.

**Steps:**

1. Install the package using pip:

     ```bash
        pip install ngraph
        ```

2. Use the package in your Python code:

        ```python
         from ngraph.lib.graph import MultiDiGraph
         from ngraph.lib.max_flow import calc_max_flow
        
         # Create a graph
         g = MultiDiGraph()
         g.add_edge("A", "B", metric=1, capacity=1)
         g.add_edge("B", "C", metric=1, capacity=1)
         g.add_edge("A", "B", metric=1, capacity=2)
         g.add_edge("B", "C", metric=1, capacity=2)
         g.add_edge("A", "D", metric=2, capacity=3)
         g.add_edge("D", "C", metric=2, capacity=3)
        
         # Calculate MaxFlow between the source and destination nodes
         max_flow = calc_max_flow(g, "A", "C")
        
         print(max_flow)

## Use Case Examples

### Calculate MaxFlow in a graph

- Calculate MaxFlow across all possible paths between the source and destination nodes

    ```python
    # Required imports
    from ngraph.lib.graph import MultiDiGraph
    from ngraph.lib.max_flow import calc_max_flow

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
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("A", "D", metric=2, capacity=3)
    g.add_edge("D", "C", metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    max_flow = calc_max_flow(g, "A", "C")

    # We can verify that the result is as expected
    assert max_flow == 6.0
    ```

- Calculate MaxFlow leveraging only the shortest paths between the source and destination nodes

    ```python
    # Required imports
    from ngraph.lib.graph import MultiDiGraph
    from ngraph.lib.max_flow import calc_max_flow

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
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("A", "D", metric=2, capacity=3)
    g.add_edge("D", "C", metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    # Flows will be placed only on the shortest paths
    max_flow = calc_max_flow(g, "A", "C", shortest_path=True)

    # We can verify that the result is as expected
    assert max_flow == 3.0
    ```

- Calculate MaxFlow balancing flows equally across the shortest paths between the source and destination nodes

    ```python
    # Required imports
    from ngraph.lib.graph import MultiDiGraph
    from ngraph.lib.max_flow import calc_max_flow
    from ngraph.lib.common import FlowPlacement

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
    g = MultiDiGraph()
    g.add_edge("A", "B", metric=1, capacity=1)
    g.add_edge("B", "C", metric=1, capacity=1)
    g.add_edge("A", "B", metric=1, capacity=2)
    g.add_edge("B", "C", metric=1, capacity=2)
    g.add_edge("A", "D", metric=2, capacity=3)
    g.add_edge("D", "C", metric=2, capacity=3)

    # Calculate MaxFlow between the source and destination nodes
    # Flows will be equally balanced across the shortest paths
    max_flow = calc_max_flow(
            g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
    )

    # We can verify that the result is as expected
    assert max_flow == 2.0
    ```

### Place traffic demands on a graph

- Place traffic demands leveraging all possible paths in a graph

    ```python
    # Required imports
    from ngraph.lib.graph import MultiDiGraph
    from ngraph.lib.common import init_flow_graph
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
                    "C",
                    20,
            ),
            Demand(
                    "C",
                    "A",
                    20,
            ),
    ]

    # Place traffic demands onto the flow graph
    for demand in demands:
            # Create a flow policy with required parameters or
            # use one of the predefined policies from FlowPolicyConfig
            flow_policy = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)

            # Place demand using the flow policy
            demand.place(r, flow_policy)

    # We can verify that all demands were placed as expected
    for demand in demands:
            assert demand.placed_demand == 20

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
    ```
