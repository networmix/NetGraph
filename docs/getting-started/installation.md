# Installation

The `ngraph` package depends on `netgraph-core`, the C++ engine; `pip install ngraph` installs both.

## Requirements

- Python 3.11 or higher
- A C++ compiler, only when no pre-built `netgraph-core` wheel exists for the platform
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
3. Dependencies (networkx, numpy, pyyaml, jsonschema)

Verify installation:

```bash
ngraph --help
```

## From Source

For development, or to install from the repository:

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

# Or, with development tooling (tests, linters, docs):
pip install -e '.[dev]'
```

## Platform Notes

**Pre-built wheels**: Available for Linux (x86_64, aarch64), macOS (x86_64, arm64), and Windows (x86_64).

**Building from source**: Requires CMake 3.23+ and a C++20 compiler (per netgraph-core's build configuration). Builds automatically during `pip install` if no compatible wheel is available.

**Next**: See [Tutorial](tutorial.md) for running scenarios and programmatic usage examples.
