# NetGraph

🚧 Work in progress! 🚧

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

- [Introduction](#introduction)
- [Installation and Usage](#installation-and-usage)
    - [Using the Docker Container with JupyterLab](#1-using-the-docker-container-with-jupyterlab)
    - [Using the Python Package](#2-using-the-python-package)
- [Use Case Examples](#use-case-examples)
    - [Calculate MaxFlow between two 3-tier Clos networks](#calculate-maxflow-between-two-3-tier-clos-networks)
---

## Introduction

NetGraph is a scenario-based network modeling and analysis framework written in Python. It allows you to design, simulate, and evaluate complex network topologies - ranging from small test cases to massive Data Center fabrics and WAN networks.

You can load an entire scenario from a single YAML file (including topology, failure policies, traffic demands, multi-step workflows) and run it in just a few lines of Python. The results can then be explored, visualized, and refined — making NetGraph well-suited for iterative network design, traffic engineering experiments, and what-if scenario analysis in large-scale topologies.

### Core Concepts

- **Topology Language and Hierarchical Blueprints**:
NetGraph includes a domain-specific language for describing topologies via “blueprints.” These blueprints can be nested and reused, letting you define node groups and their interconnects in a hierarchical manner. Connectivity patterns (e.g., "mesh", "one_to_one") and complex expansions (e.g., dc[1-3, 5-6]) let you scale out large topologies with minimal repetition.

- **Scenario-Based Workflows**:
A Scenario is the main entry point for building and running network analyses: it encapsulates the topology, failure policies, traffic demands, and workflow steps. A Scenario can be loaded from a YAML file or created programmatically, and it can be run in a single step or iteratively to explore different configurations.

- **Low-Level Library**:
Under the hood, NetGraph provides robust primitives for building and analyzing network graphs, calculating flows, placing traffic demands, and enforcing traffic engineering policies. This library is used by the scenario-based workflows, but it can also be used independently.

---

## Installation and Usage

NetGraph can be used in two ways:
- **Using the Docker Container with JupyterLab**: This is the easiest way to get started with NetGraph, as it provides a pre-configured environment with JupyterLab and all dependencies installed.
- **Using the Python Package**: If you prefer to use NetGraph in your own Python environment, you can install the package using pip and use it in your Python code.

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
    ./run.sh run
    ```

4. Open the JupyterLab URL in your browser:

    ```bash
    http://127.0.0.1:8788/
    ```

5. Jupyter will show the content of `notebooks` directory and you can start using the provided notebooks (e.g., open scenario_dc.ipynb) or create your own.

**Note**: Docker is instructed to mount the content of `NetGraph` directory into the `/root/env` directory inside container, so any changes made to any files in the `NetGraph` directory will be reflected in the container and vice versa. The `ngraph` package is installed in the container in editable mode, so you can make changes to the code and leverage them immediately in JupyterLab. But don't forget to restart the JupyterLab kernel to see the changes.

To exit the JupyterLab server, press `Ctrl+C` in the terminal where the server is running. To stop the remaining Docker container, run:

```bash
./run.sh stop
```

### 2. Using the Python Package

**Prerequisites:**

- Python 3.10 or higher installed on your machine.

Note: Don't forget to use a virtual environment (e.g., `venv`) to avoid conflicts with other Python packages. See [Python Virtual Environments](https://docs.python.org/3/library/venv.html) for more information.

**Steps:**

1. Install the package using pip:

    ```bash
    pip install ngraph
    ```

2. Use the package in your Python code:

    ```python
    from ngraph.scenario import Scenario
    from ngraph.explorer import NetworkExplorer
    scenario_yaml = """
    <describe your scenario here>
    """
    scenario = Scenario.from_yaml(scenario_yaml)
    scenario.run()
    network = scenario.network
    explorer = NetworkExplorer.explore_network(network)
    explorer.print_tree(skip_leaves=True, detailed=False)
    ```

## Use Case Examples

### Calculate MaxFlow between two 3-tier Clos networks

```python
from ngraph.scenario import Scenario
from ngraph.lib.flow_policy import FlowPlacement
scenario_yaml = """
blueprints:
  brick_2tier:
    groups:
      t1:
        node_count: 8
        name_template: t1-{node_num}
      t2:
        node_count: 8
        name_template: t2-{node_num}

    adjacency:
      - source: /t1
        target: /t2
        pattern: mesh
        link_params:
          capacity: 2
          cost: 1

  3tier_clos:
    groups:
      b1:
        use_blueprint: brick_2tier
      b2:
        use_blueprint: brick_2tier
      spine:
        node_count: 64
        name_template: t3-{node_num}

    adjacency:
      - source: b1/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1
      - source: b2/t2
        target: spine
        pattern: one_to_one
        link_params:
          capacity: 2
          cost: 1

network:
  name: "3tier_clos_network"
  version: 1.0

  groups:
    my_clos1:
      use_blueprint: 3tier_clos

    my_clos2:
      use_blueprint: 3tier_clos

  adjacency:
    - source: my_clos1/spine
      target: my_clos2/spine
      pattern: one_to_one
      link_count: 4
      link_params:
        capacity: 1
        cost: 1
"""
scenario = Scenario.from_yaml(scenario_yaml)
network = scenario.network
network.max_flow(
    source_path=r"my_clos1.*(b[0-9]*)/t1",
    sink_path=r"my_clos2.*(b[0-9]*)/t1",
    mode="combine",
    shortest_path=True,
    flow_placement=FlowPlacement.EQUAL_BALANCED,
)
```
Result is `{('b1|b2', 'b1|b2'): 256.0}`. It means that the maximum flow between all t1 nodes in `my_clos1` and all t1 nodes in `my_clos2` is 256.0.

Note that flow_placement parameter is set to FlowPlacement.EQUAL_BALANCED, which emulates ECMP. This means that the flow is distributed equally between all possible paths. If we were to disable three out of four links between any pair of spine routers (bringing the overal spine - spine capacity to 253.0), the overall flow in such ECMP scenario would be limited by this bottleneck and the maximum flow would be 64.0 (not 253). While setting flow_placement to FlowPlacement.PROPORTIONAL would result in the flow being distributed proportionally to the link capacities (emulation of UCMP). Resulting in the maximum flow of 253.0.