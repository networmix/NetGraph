# NetGraph Development Guide

## Essential Commands

```bash
make dev           # Create venv, install package with dev deps and hooks
make check         # Pre-commit with auto-fix, schema check, tests, then lint
make check-ci      # Non-mutating lint, schema check, and tests (CI)
make test          # Run tests with coverage
make docs          # Generate API documentation and diagram SVGs
make docs-serve    # Serve docs locally
```

`make docs` renders `docs/assets/diagrams/*.dot` with Graphviz; install it
with `brew install graphviz` (macOS) or `apt-get install graphviz` (Debian/Ubuntu).
Without it the diagram step is skipped and the committed SVGs stay as they are.

## Publishing

**Manual**: `make clean && make build && make publish-test && make publish`

**Automated**: Create GitHub release → auto-publishes to PyPI

**Version**: Update `version = "x.y.z"` in `pyproject.toml` before publishing

## Key Development Files

```text
pyproject.toml              # Package config, dependencies, tool settings
Makefile                    # Development commands
.pre-commit-config.yaml     # Code quality hooks
dev/run-checks.sh           # Script behind make check
```

## GitHub Workflows

```text
.github/workflows/
├── python-test.yml         # CI: tests, linting, type checking
├── docs.yml                # Build and deploy docs on push to main
└── publish.yml             # Publish to PyPI on release; Test PyPI on manual run
```
