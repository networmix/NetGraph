# Installation

NetGraph is a hybrid Python+C++ framework. The Python package (`ngraph`) automatically installs
the C++ performance layer (`netgraph-core`) as a dependency.

## Requirements

- Python 3.11 or higher
- C++ compiler (for building netgraph-core from source if needed)
  - Linux: GCC 10+ or Clang 12+
  - macOS: Xcode Command Line Tools (Apple Clang)
  - Windows: Visual Studio 2019+ with C++ tools

## From PyPI

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Install NetGraph:

```bash
pip install ngraph
```

This installs:

1. The Python `ngraph` package
2. `netgraph-core` (pre-built wheels for common platforms, or builds from source)
3. Dependencies (networkx, pyyaml, pandas, jsonschema)

Verify installation:

```bash
ngraph --help
```

## From Source

For development or if you need the latest changes:

```bash
# Clone both repositories
git clone https://github.com/networmix/NetGraph-Core
git clone https://github.com/networmix/NetGraph

# Install NetGraph-Core first
cd NetGraph-Core
pip install -e .

# Install NetGraph
cd ../NetGraph
pip install -e .
```

## Platform Notes

**Pre-built wheels**: Available for Linux (x86_64, aarch64), macOS (x86_64, arm64), and Windows (x86_64).

**Building from source**: Requires CMake 3.15+. Builds automatically during `pip install` if no compatible wheel is available.

**Next**: See [Tutorial](tutorial.md) for running scenarios and programmatic usage examples.
