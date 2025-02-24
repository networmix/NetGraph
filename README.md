# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

- [Introduction](#introduction)
- [Installation and Usage](#installation-and-usage)
    - [Using the Docker Container with JupyterLab](#1-using-the-docker-container-with-jupyterlab)
    - [Using the Python Package](#2-using-the-python-package)
- [Use Case Examples](#use-case-examples)
    - [Calculate MaxFlow in a graph](#calculate-maxflow-in-a-graph)
    - [Traffic demands placement on a graph](#traffic-demands-placement-on-a-graph)

---

## Introduction

NetGraph is a tool for network modeling and analysis. It consists of two main parts:
- A lower level library providing graph data structures and algorithms for network modeling and analysis.
- A set of higher level abstractions like network and workflow that can comprise a complete network analysis scenario.

The lower level lib provides the following main primitives:

- **StrictMultiDiGraph**  
  Specialized multi-digraph with addressable edges and strict checks on duplicate nodes/edges.

- **Path**  
  Represents a single path between two nodes in the graph.

- **PathBundle**  
  A collection of equal-cost paths between two nodes.

- **Demand**  
  Models a network demand from a source node to a destination node with a specified traffic volume.

- **Flow**  
  Represent placement of a Demand volume along one or more paths (via a PathBundle) in a graph.

- **FlowPolicy**  
  Governs how Demands are split into Flows, enforcing routing/TE constraints (e.g., shortest paths, multipath, capacity limits).

---

## Installation and Usage

NetGraph can be used in two ways:

### 1. Using the Docker Container with JupyterLab

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

5. Jupyter will show the content of `notebooks` directory and you can start using the provided notebooks or create your own.

Note: Docker will mount the content of `NetGraph` directory into the `/root/env` directory inside container, so any changes made to the code in the `NetGraph` directory will be reflected in the container and vice versa.

The `ngraph` package is installed in the container in editable mode, so you can make changes to the code and see the changes reflected immediately in JupyterLab.

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
      from ngraph.lib.graph import StrictMultiDiGraph
      from ngraph.lib.algorithms.max_flow import calc_max_flow

      # Create a graph
      g = StrictMultiDiGraph()
      g.add_node("A")
      g.add_node("B")
      g.add_node("C")
      g.add_edge("A", "B", metric=1, capacity=1)
      g.add_edge("A", "B", metric=1, capacity=1)
      g.add_edge("B", "C", metric=1, capacity=2)
      g.add_edge("A", "C", metric=2, capacity=3)

      # Calculate MaxFlow between the source and destination nodes
      max_flow = calc_max_flow(g, "A", "C")

      print(max_flow)
    ```

## Use Case Examples

### Calculate MaxFlow in a graph
```python
    """
    Tests max flow calculations on a graph with parallel edges.

    Graph topology (metrics/capacities):

                 [1,1] & [1,2]     [1,1] & [1,2]
          A ──────────────────► B ─────────────► C
          │                                      ▲
          │    [2,3]                             │ [2,3]
          └───────────────────► D ───────────────┘

    Edges:
      - A→B: two parallel edges with (metric=1, capacity=1) and (metric=1, capacity=2)
      - B→C: two parallel edges with (metric=1, capacity=1) and (metric=1, capacity=2)
      - A→D: (metric=2, capacity=3)
      - D→C: (metric=2, capacity=3)

    The test computes:
      - The true maximum flow (expected flow: 6.0)
      - The flow along the shortest paths (expected flow: 3.0)
      - Flow placement using an equal-balanced strategy on the shortest paths (expected flow: 2.0)
    """
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.max_flow import calc_max_flow
    from ngraph.lib.algorithms.base import FlowPlacement

    g = StrictMultiDiGraph()
    for node in ("A", "B", "C", "D"):
        g.add_node(node)

    # Create parallel edges between A→B and B→C
    g.add_edge("A", "B", key=0, metric=1, capacity=1)
    g.add_edge("A", "B", key=1, metric=1, capacity=2)
    g.add_edge("B", "C", key=2, metric=1, capacity=1)
    g.add_edge("B", "C", key=3, metric=1, capacity=2)
    # Create an alternative path A→D→C
    g.add_edge("A", "D", key=4, metric=2, capacity=3)
    g.add_edge("D", "C", key=5, metric=2, capacity=3)

    # 1. The true maximum flow
    max_flow_prop = calc_max_flow(g, "A", "C")
    assert max_flow_prop == 6.0, f"Expected 6.0, got {max_flow_prop}"

    # 2. The flow along the shortest paths
    max_flow_sp = calc_max_flow(g, "A", "C", shortest_path=True)
    assert max_flow_sp == 3.0, f"Expected 3.0, got {max_flow_sp}"

    # 3. Flow placement using an equal-balanced strategy on the shortest paths
    max_flow_eq = calc_max_flow(
        g, "A", "C", shortest_path=True, flow_placement=FlowPlacement.EQUAL_BALANCED
    )
    assert max_flow_eq == 2.0, f"Expected 2.0, got {max_flow_eq}"

```

### Traffic demands placement on a graph
```python
    """
    Demonstrates traffic engineering by placing two demands on a network.

    Graph topology (metrics/capacities):

              [15]
          A ─────── B
           \      /
        [5] \    / [15]
             \  /
              C

    - Each link is bidirectional:
         A↔B: capacity 15, B↔C: capacity 15, and A↔C: capacity 5.
    - We place a demand of volume 20 from A→C and a second demand of volume 20 from C→A.
    - Each demand uses its own FlowPolicy, so the policy's global flow accounting does not overlap.
    - The test verifies that each demand is fully placed at 20 units.
    """
    from ngraph.lib.graph import StrictMultiDiGraph
    from ngraph.lib.algorithms.flow_init import init_flow_graph
    from ngraph.lib.flow_policy import FlowPolicyConfig, get_flow_policy
    from ngraph.lib.demand import Demand

    # Build the graph.
    g = StrictMultiDiGraph()
    for node in ("A", "B", "C"):
        g.add_node(node)

    # Create bidirectional edges with distinct labels (for clarity).
    g.add_edge("A", "B", key=0, metric=1, capacity=15, label="1")
    g.add_edge("B", "A", key=1, metric=1, capacity=15, label="1")
    g.add_edge("B", "C", key=2, metric=1, capacity=15, label="2")
    g.add_edge("C", "B", key=3, metric=1, capacity=15, label="2")
    g.add_edge("A", "C", key=4, metric=1, capacity=5, label="3")
    g.add_edge("C", "A", key=5, metric=1, capacity=5, label="3")

    # Initialize flow-related structures (e.g., to track placed flows in the graph).
    flow_graph = init_flow_graph(g)

    # Demand from A→C (volume 20).
    demand_ac = Demand("A", "C", 20)
    flow_policy_ac = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
    demand_ac.place(flow_graph, flow_policy_ac)
    assert demand_ac.placed_demand == 20, (
        f"Demand from {demand_ac.src_node} to {demand_ac.dst_node} "
        f"expected to be fully placed."
    )

    # Demand from C→A (volume 20), using a separate FlowPolicy instance.
    demand_ca = Demand("C", "A", 20)
    flow_policy_ca = get_flow_policy(FlowPolicyConfig.TE_UCMP_UNLIM)
    demand_ca.place(flow_graph, flow_policy_ca)
    assert demand_ca.placed_demand == 20, (
        f"Demand from {demand_ca.src_node} to {demand_ca.dst_node} "
        f"expected to be fully placed."
    )

```