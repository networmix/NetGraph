# NetGraph Development Guide

## Essential Commands

```bash
make setup         # Complete dev environment setup
make check         # Run all quality checks + tests
make test          # Run tests with coverage
make docs          # Generate API documentation
make docs-serve    # Serve docs locally
```

**For all available commands**: `make help`

## Documentation

### Generating API Documentation

The API documentation is auto-generated from source code docstrings:

```bash
# Generate API documentation
make docs
# or
python dev/generate_api_docs.py
```

**Important**: API documentation is **not** regenerated during pytest runs to avoid constant file changes. The doc generation test is skipped by default. To test doc generation:

```bash
GENERATE_DOCS=true pytest tests/test_api_docs.py::test_api_doc_generation_output
```

### Documentation Types

- `docs/reference/api.md` - Curated, example-driven API guide (manually maintained)
- `docs/reference/api-full.md` - Complete auto-generated reference (regenerated via `make docs`)
- `docs/reference/cli.md` - Command-line interface documentation
- `docs/reference/dsl.md` - YAML DSL syntax reference

## Publishing

**Manual**: `make clean && make build && make publish-test && make publish`

**Automated**: Create GitHub release → auto-publishes to PyPI

**Version**: Update `version = "x.y.z"` in `pyproject.toml` before publishing

## Key Development Files

```
pyproject.toml              # Package config, dependencies, tool settings
Makefile                    # Development commands
.pre-commit-config.yaml     # Code quality hooks
dev/setup-dev.sh           # Development environment setup script
dev/run-checks.sh           # Manual code quality checks
```

## Git Workflows

```
.github/workflows/
├── python-test.yml         # CI: tests, linting, type checking
├── docs.yml                # Auto-deploy documentation
└── publish.yml             # Auto-publish to PyPI on releases
```
