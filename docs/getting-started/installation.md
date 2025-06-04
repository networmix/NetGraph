# Installation

NetGraph can be used in two ways:
- **Using the Docker Container with JupyterLab**: This is the easiest way to get started with NetGraph, as it provides a pre-configured environment with JupyterLab and all dependencies installed.
- **Using the Python Package**: If you prefer to use NetGraph in your own Python environment, you can install the package using pip and use it in your Python code.

## Using the Docker Container with JupyterLab

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

## Using the Python Package

**Prerequisites:**

- Python 3.9 or higher installed on your machine.

!!! note
    Don't forget to use a virtual environment (e.g., `venv`) to avoid conflicts with other Python packages. See [Python Virtual Environments](https://docs.python.org/3/library/venv.html) for more information.

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
    network:
      groups:
        servers:
          node_count: 2
          name_template: "server-{node_num}"
    """
    
    scenario = Scenario.from_yaml(scenario_yaml)
    network = scenario.network
    explorer = NetworkExplorer.explore_network(network)
    explorer.print_tree(skip_leaves=True, detailed=False)
    ```

## Next Steps

- **[Quick Tutorial](tutorial.md)** - Build your first network scenario
- **[DSL Reference](../reference/dsl.md)** - Learn the YAML syntax
