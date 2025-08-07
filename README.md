# NetGraph

[![Python-test](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml/badge.svg?branch=main)](https://github.com/networmix/NetGraph/actions/workflows/python-test.yml)

NetGraph is a scenario-based network modeling and analysis framework written in Python. Design, simulate, and evaluate complex network topologies from small test cases to large-scale Data Center fabrics and WAN networks.

## Features

- Scenario-based modeling (DSL for topology, failures, traffic, workflow)
- Hierarchical blueprints for reusable topologies
- Max-flow and demand placement analysis with configurable policies
- CLI: inspect, run, report
- Reporting to notebook and HTML

## Quick Start

### Local Installation

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -e '.[dev]'
```

### Docker with JupyterLab

```bash
git clone https://github.com/networmix/NetGraph
cd NetGraph
./run.sh build
./run.sh run  # Opens JupyterLab at http://127.0.0.1:8788/
```

## Documentation

Docs: [https://networmix.github.io/NetGraph/](https://networmix.github.io/NetGraph/)

- Installation: <https://networmix.github.io/NetGraph/getting-started/installation/>
- Tutorial: <https://networmix.github.io/NetGraph/getting-started/tutorial/>
- Examples: <https://networmix.github.io/NetGraph/examples/basic/>
- DSL: <https://networmix.github.io/NetGraph/reference/dsl/>
- API: <https://networmix.github.io/NetGraph/reference/api/>
- CLI: <https://networmix.github.io/NetGraph/reference/cli/>

## License

[MIT License](LICENSE)
