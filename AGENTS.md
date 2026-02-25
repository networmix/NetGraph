# AGENTS.md

## Cursor Cloud specific instructions

### Overview

NetGraph is a Python library + CLI tool for network modeling and analysis. It combines a Python front-end with C++ graph algorithms via `netgraph-core`. There are no web servers, databases, or Docker services.

### Development commands

All dev commands use the venv at `./venv`. See `Makefile` for the full list (`make help`).

| Task | Command |
|---|---|
| Lint (ruff + pyright) | `make lint` |
| Auto-format | `make format` |
| Quick tests (no slow/benchmark) | `make qt` |
| Full tests with coverage | `make test` |
| Run a scenario | `ngraph run scenarios/square_mesh.yaml --output results/` |
| Schema validation | `make validate` |

### Gotchas

- The system package `python3.12-venv` must be installed before `make dev` can create the virtualenv. The update script handles this.
- `git config core.hooksPath` may be set by the Cloud Agent environment; if pre-commit hook installation fails with "Cowardly refusing to install hooks with `core.hooksPath` set", run `git config --unset-all core.hooksPath` first.
- Pyright is pinned to `1.1.401` in `pyproject.toml`; ignore "new version available" warnings.
- `make test` enforces a minimum 75% code coverage threshold (currently ~89%).
