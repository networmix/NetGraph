# NetGraph Development Makefile
# This Makefile provides convenient shortcuts for common development tasks

.PHONY: help venv clean-venv dev install check check-ci lint format test qt build clean check-dist publish-test publish info hooks check-python docs docs-serve docs-diagrams validate perf

# Default target - show help
.DEFAULT_GOAL := help

# Toolchain (prefer project venv if present)
VENV_BIN := $(PWD)/venv/bin
PY_FIND := $(shell command -v python3 2>/dev/null || command -v python 2>/dev/null)
PYTHON ?= $(if $(wildcard $(VENV_BIN)/python),$(VENV_BIN)/python,$(PY_FIND))
PIP := $(PYTHON) -m pip
PYTEST := $(PYTHON) -m pytest
RUFF := $(PYTHON) -m ruff
PRECOMMIT := $(PYTHON) -m pre_commit

help:
	@echo "🔧 NetGraph Development Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make venv          - Create a local virtualenv (./venv)"
	@echo "  make dev           - Full development environment (package + dev deps + hooks)"
	@echo "  make install       - Install package for usage (no dev dependencies)"
	@echo "  make clean-venv    - Remove virtual environment"
	@echo ""
	@echo "Code Quality & Testing:"
	@echo "  make check         - Run pre-commit (auto-fix) + schema + tests, then lint"
	@echo "  make check-ci      - Run non-mutating checks and tests (CI entrypoint)"
	@echo "  make lint          - Run only linting (non-mutating: ruff + pyright)"
	@echo "  make format        - Auto-format code with ruff"
	@echo "  make test          - Run tests with coverage (includes slow and benchmark)"
	@echo "  make qt            - Run quick tests only (excludes slow and benchmark)"
	@echo "  make perf          - Run performance analysis with comprehensive reports and plots"
	@echo "  make validate      - Validate YAML schemas"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs          - Generate API documentation"
	@echo "  make docs-serve    - Serve documentation locally"
	@echo ""
	@echo "Build & Package:"
	@echo "  make build         - Build distribution packages"
	@echo "  make clean         - Clean build artifacts and cache files"
	@echo ""
	@echo "Publishing:"
	@echo "  make check-dist    - Check distribution packages with twine"
	@echo "  make publish-test  - Publish to Test PyPI"
	@echo "  make publish       - Publish to PyPI"
	@echo ""
	@echo "Utilities:"
	@echo "  make info          - Show project information"
	@echo "  make hooks         - Run pre-commit on all files"
	@echo "  make check-python  - Check if venv Python matches system Python"

# Setup and Installation
dev:
	@echo "🚀 Setting up development environment..."
	@if [ ! -x "$(VENV_BIN)/python" ]; then \
		if [ -z "$(PY_FIND)" ]; then \
			echo "❌ Error: No Python interpreter found (python3 or python)"; \
			exit 1; \
		fi; \
		echo "🐍 Creating virtual environment with $(PY_FIND) ..."; \
		$(PY_FIND) -m venv venv || { echo "❌ Failed to create venv"; exit 1; }; \
		if [ ! -x "$(VENV_BIN)/python" ]; then \
			echo "❌ Error: venv creation failed - $(VENV_BIN)/python not found"; \
			exit 1; \
		fi; \
		$(VENV_BIN)/python -m pip install -U pip wheel; \
	fi
	@echo "📦 Installing dev dependencies..."
	@$(VENV_BIN)/python -m pip install -e .'[dev]'
	@echo "🔗 Installing pre-commit hooks..."
	@$(VENV_BIN)/python -m pre_commit install --install-hooks
	@echo "✅ Dev environment ready. Activate with: source venv/bin/activate"
	@$(MAKE) check-python

venv:
	@echo "🐍 Creating virtual environment in ./venv ..."
	@if [ -z "$(PY_FIND)" ]; then \
		echo "❌ Error: No Python interpreter found (python3 or python)"; \
		exit 1; \
	fi
	@$(PY_FIND) -m venv venv || { echo "❌ Failed to create venv"; exit 1; }
	@if [ ! -x "$(VENV_BIN)/python" ]; then \
		echo "❌ Error: venv creation failed - $(VENV_BIN)/python not found"; \
		exit 1; \
	fi
	@$(VENV_BIN)/python -m pip install -U pip wheel
	@echo "✅ venv ready. Activate with: source venv/bin/activate"

clean-venv:
	@rm -rf venv/

install:
	@echo "📦 Installing package for usage (no dev dependencies)..."
	@$(PIP) install -e .

# Code Quality and Testing
check:
	@echo "🔍 Running complete code quality checks and tests..."
	@PYTHON=$(PYTHON) bash dev/run-checks.sh
	@$(MAKE) lint

check-ci:
	@echo "🔍 Running CI checks (non-mutating lint + schema validation + tests)..."
	@$(MAKE) lint
	@$(MAKE) validate
	@$(MAKE) test

lint:
	@echo "🧹 Running linting checks (non-mutating)..."
	@$(RUFF) format --check .
	@$(RUFF) check .
	@$(PYTHON) -m pyright

format:
	@echo "✨ Auto-formatting code..."
	@$(RUFF) format .

test:
	@echo "🧪 Running tests with coverage (includes slow and benchmark)..."
	@$(PYTEST)

qt:
	@echo "⚡ Running quick tests only (excludes slow and benchmark)..."
	@$(PYTEST) --no-cov -m "not slow and not benchmark"

perf:
	@echo "📊 Running performance analysis with tables and graphs..."
	@$(PYTHON) -m dev.perf.main run || (echo "❌ Performance analysis failed."; exit 1)

validate:
	@echo "📋 Validating YAML schemas..."
	@if $(PYTHON) -c "import jsonschema" >/dev/null 2>&1; then \
		$(PYTHON) -c "import json, yaml, jsonschema, pathlib; from importlib import resources as res; f=res.files('ngraph.schemas').joinpath('scenario.json').open('r', encoding='utf-8'); schema=json.load(f); f.close(); scenario_files=list(pathlib.Path('scenarios').rglob('*.yaml')); integration_files=list(pathlib.Path('tests/integration').glob('*.yaml')); all_files=scenario_files+integration_files; [jsonschema.validate(yaml.safe_load(open(fp)), schema) for fp in all_files]; print(f'✅ Validated {len(all_files)} YAML files against schema ({len(scenario_files)} scenarios, {len(integration_files)} integration tests)')"; \
	else \
		echo "⚠️  jsonschema not installed. Skipping schema validation"; \
	fi

# Documentation
docs:
	@echo "📚 Generating API documentation..."
	@$(MAKE) docs-diagrams
	@echo "ℹ️  This regenerates docs/reference/api-full.md from source code"
	@$(PYTHON) dev/generate_api_docs.py --write-file

docs-diagrams:
	@echo "🖼️  Generating diagram SVGs from DOT (if any)..."
	@if ls docs/assets/diagrams/*.dot >/dev/null 2>&1; then \
		if command -v dot >/dev/null 2>&1; then \
			dot -Tsvg docs/assets/diagrams/*.dot -O; \
			echo "✅ Generated diagram SVGs"; \
		else \
			echo "⚠️  graphviz 'dot' not installed. Skipping diagram generation"; \
		fi; \
	else \
		echo "ℹ️  No .dot files found in docs/assets/diagrams/"; \
	fi

docs-serve:
	@echo "🌐 Serving documentation locally..."
	@if $(PYTHON) -c "import mkdocs" >/dev/null 2>&1; then \
		$(PYTHON) -m mkdocs serve; \
	else \
		echo "❌ mkdocs not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

# Build and Package
build:
	@echo "🏗️  Building distribution packages..."
	@if $(PYTHON) -c "import build" >/dev/null 2>&1; then \
		$(PYTHON) -m build; \
	else \
		echo "❌ build module not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

clean:
	@echo "🧹 Cleaning build artifacts and cache files..."
	@rm -rf build/ dist/ *.egg-info/
	@rm -rf .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage coverage.xml coverage-*.xml .benchmarks .pytest-benchmark || true
	@find . -path "./venv" -prune -o -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -path "./venv" -prune -o -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -path "./venv" -prune -o -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -path "./venv" -prune -o -type f -name "*~" -delete 2>/dev/null || true
	@find . -path "./venv" -prune -o -type f -name "*.orig" -delete 2>/dev/null || true
	@echo "✅ Cleanup complete!"

# Publishing
check-dist:
	@echo "🔍 Checking distribution packages..."
	@if $(PYTHON) -c "import twine" >/dev/null 2>&1; then \
		$(PYTHON) -m twine check dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

publish-test:
	@echo "📦 Publishing to Test PyPI..."
	@if $(PYTHON) -c "import twine" >/dev/null 2>&1; then \
		$(PYTHON) -m twine upload --repository testpypi dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

publish:
	@echo "🚀 Publishing to PyPI..."
	@if $(PYTHON) -c "import twine" >/dev/null 2>&1; then \
		$(PYTHON) -m twine upload dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

# Project Information
info:
	@echo "📋 NetGraph Project Information"
	@echo "================================"
	@echo ""
	@echo "🐍 Python Environment:"
	@echo "  Python (active): $$($(PYTHON) --version)"
	@echo "  Python (system): $$($(PY_FIND) --version 2>/dev/null || echo 'missing')"
	@$(MAKE) check-python
	@echo "  Package version: $$($(PYTHON) -c 'import importlib.metadata; print(importlib.metadata.version("ngraph"))' 2>/dev/null || echo 'Not installed')"
	@echo "  Virtual environment: $$(echo $$VIRTUAL_ENV | sed 's|.*/||' || echo 'None active')"
	@echo ""
	@echo "🔧 Development Tools:"
	@echo "  Pre-commit: $$($(PRECOMMIT) --version 2>/dev/null || echo 'Not installed')"
	@echo "  Pytest: $$($(PYTEST) --version 2>/dev/null || echo 'Not installed')"
	@echo "  Ruff: $$($(RUFF) --version 2>/dev/null || echo 'Not installed')"
	@echo "  Pyright: $$($(PYTHON) -m pyright --version 2>/dev/null | head -1 || echo 'Not installed')"
	@echo "  MkDocs: $$($(PYTHON) -m mkdocs --version 2>/dev/null | sed 's/mkdocs, version //' | sed 's/ from.*//' || echo 'Not installed')"
	@echo "  Build: $$($(PYTHON) -m build --version 2>/dev/null | sed 's/build //' | sed 's/ (.*//' || echo 'Not installed')"
	@echo "  Twine: $$($(PYTHON) -m twine --version 2>/dev/null | grep -o 'twine version [0-9.]*' | cut -d' ' -f3 || echo 'Not installed')"
	@echo "  JsonSchema: $$($(PYTHON) -c 'import importlib.metadata; print(importlib.metadata.version("jsonschema"))' 2>/dev/null || echo 'Not installed')"
	@echo ""
	@echo "📂 Git Repository:"
	@echo "  Current branch: $$(git branch --show-current 2>/dev/null || echo 'Not a git repository')"
	@echo "  Status: $$(git status --porcelain | wc -l | tr -d ' ') modified files"
	@if [ "$$(git status --porcelain | wc -l | tr -d ' ')" != "0" ]; then \
		echo "  Modified files:"; \
		git status --porcelain | head -5 | sed 's/^/    /'; \
		if [ "$$(git status --porcelain | wc -l | tr -d ' ')" -gt "5" ]; then \
			echo "    ... and $$(( $$(git status --porcelain | wc -l | tr -d ' ') - 5 )) more"; \
		fi; \
	fi

hooks:
	@echo "🔗 Running pre-commit on all files..."
	@$(PRECOMMIT) run --all-files || (echo "Some pre-commit hooks failed. Fix and re-run." && exit 1)

check-python:
	@if [ -x "$(VENV_BIN)/python" ]; then \
		VENV_VER=$$($(VENV_BIN)/python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown"); \
		SYS_VER=$$($(PY_FIND) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "unknown"); \
		if [ -n "$$VENV_VER" ] && [ -n "$$SYS_VER" ] && [ "$$VENV_VER" != "$$SYS_VER" ]; then \
			echo "⚠️  WARNING: venv Python ($$VENV_VER) != system Python ($$SYS_VER)"; \
			echo "   Run 'make clean-venv && make dev' to recreate venv with system Python"; \
		fi; \
	fi
