# NetGraph Development Makefile
# This Makefile provides convenient shortcuts for common development tasks

.PHONY: help dev install check test qt clean docs docs-serve build check-dist publish-test publish docker-build docker-run validate perf

# Default target - show help
.DEFAULT_GOAL := help

help:
	@echo "🔧 NetGraph Development Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make install       - Install package for usage (no dev dependencies)"
	@echo "  make dev           - Full development environment (package + dev deps + hooks)"
	@echo ""
	@echo "Code Quality & Testing:"
	@echo "  make check         - Run all pre-commit checks and tests (includes slow and benchmark)"
	@echo "  make check-ci      - Run non-mutating checks and tests (CI entrypoint)"
	@echo "  make lint          - Run only linting (non-mutating: ruff + pyright)"
	@echo "  make format        - Auto-format code with ruff"
	@echo "  make test          - Run tests with coverage (includes slow and benchmark)"
	@echo "  make qt            - Run quick tests only (excludes slow and benchmark)"
	@echo "  make perf          - Run performance analysis with comprehensive reports and plots"
	@echo "  make validate      - Validate YAML files against JSON schema"
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
	@echo "Docker (containerized development):"
	@echo "  make docker-build  - Build Docker image for JupyterLab environment"
	@echo "  make docker-run    - Run Docker container with JupyterLab (port 8788)"
	@echo ""
	@echo "Utilities:"
	@echo "  make info          - Show project information"

# Setup and Installation
dev:
	@echo "🚀 Setting up development environment..."
	@bash dev/setup-dev.sh

install:
	@echo "📦 Installing package for usage (no dev dependencies)..."
	pip install -e .

# Code Quality and Testing
check:
	@echo "🔍 Running complete code quality checks and tests..."
	@bash dev/run-checks.sh

check-ci:
	@echo "🔍 Running CI checks (non-mutating lint + schema validation + tests)..."
	@$(MAKE) lint
	@$(MAKE) validate
	@$(MAKE) test

lint:
	@echo "🧹 Running linting checks (non-mutating)..."
	@ruff format --check .
	@ruff check .
	@pyright

format:
	@echo "✨ Auto-formatting code..."
	@pre-commit run ruff-format --all-files

test:
	@echo "🧪 Running tests with coverage (includes slow and benchmark)..."
	@pytest

qt:
	@echo "⚡ Running quick tests only (excludes slow and benchmark)..."
	@pytest --no-cov -m "not slow and not benchmark"

perf:
	@echo "📊 Running performance analysis with tables and graphs..."
	@python -m dev.perf.main run || (echo "❌ Performance analysis failed."; exit 1)

validate:
	@echo "📋 Validating YAML schemas..."
	@if python -c "import jsonschema" >/dev/null 2>&1; then \
		python -c "import json, yaml, jsonschema, pathlib; \
		schema = json.load(open('schemas/scenario.json')); \
		scenario_files = list(pathlib.Path('scenarios').rglob('*.yaml')); \
		integration_files = list(pathlib.Path('tests/integration').glob('*.yaml')); \
		all_files = scenario_files + integration_files; \
		[jsonschema.validate(yaml.safe_load(open(f)), schema) for f in all_files]; \
		print(f'✅ Validated {len(all_files)} YAML files against schema ({len(scenario_files)} scenarios, {len(integration_files)} integration tests)')"; \
	else \
		echo "⚠️  jsonschema not installed. Skipping schema validation"; \
	fi

# Documentation
docs:
	@echo "📚 Generating API documentation..."
	@echo "ℹ️  This regenerates docs/reference/api-full.md from source code"
	@python dev/generate_api_docs.py --write-file

docs-serve:
	@echo "🌐 Serving documentation locally..."
	@if command -v mkdocs >/dev/null 2>&1; then \
		mkdocs serve; \
	else \
		echo "❌ mkdocs not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

# Build and Package
build:
	@echo "🏗️  Building distribution packages..."
	@if python -c "import build" >/dev/null 2>&1; then \
		python -m build; \
	else \
		echo "❌ build module not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

clean:
	@echo "🧹 Cleaning build artifacts and cache files..."
	@rm -rf build/
	@rm -rf dist/
	@rm -rf *.egg-info/
	@find . -type f -name "*.pyc" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete
	@find . -type f -name "*~" -delete
	@find . -type f -name "*.orig" -delete
	@echo "✅ Cleanup complete!"

# Docker commands (containerized development environment)
docker-build:
	@echo "🐳 Building Docker image for JupyterLab environment..."
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "❌ Docker not installed. Please install Docker first."; \
		exit 1; \
	fi
	@if [ -f "Dockerfile" ]; then \
		bash run.sh build; \
	else \
		echo "❌ Dockerfile not found"; \
		exit 1; \
	fi

docker-run:
	@echo "🐳 Running Docker container with JupyterLab (port 8788)..."
	@if ! command -v docker >/dev/null 2>&1; then \
		echo "❌ Docker not installed. Please install Docker first."; \
		exit 1; \
	fi
	@if [ -f "run.sh" ]; then \
		bash run.sh run; \
		echo "ℹ️  Additional Docker commands: ./run.sh stop|shell|killall|forcecleanall"; \
	else \
		echo "❌ run.sh not found"; \
		exit 1; \
	fi

# Publishing
check-dist:
	@echo "🔍 Checking distribution packages..."
	@if python -c "import twine" >/dev/null 2>&1; then \
		python -m twine check dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

publish-test:
	@echo "📦 Publishing to Test PyPI..."
	@if python -c "import twine" >/dev/null 2>&1; then \
		python -m twine upload --repository testpypi dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev"; \
		exit 1; \
	fi

publish:
	@echo "🚀 Publishing to PyPI..."
	@if python -c "import twine" >/dev/null 2>&1; then \
		python -m twine upload dist/*; \
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
	@echo "  Python version: $$(python --version)"
	@echo "  Package version: $$(python -c 'import importlib.metadata; print(importlib.metadata.version("ngraph"))' 2>/dev/null || echo 'Not installed')"
	@echo "  Virtual environment: $$(echo $$VIRTUAL_ENV | sed 's|.*/||' || echo 'None active')"
	@echo ""
	@echo "🔧 Development Tools:"
	@echo "  Pre-commit: $$(pre-commit --version 2>/dev/null || echo 'Not installed')"
	@echo "  Docker: $$(docker --version 2>/dev/null || echo 'Not installed')"
	@echo "  Pytest: $$(pytest --version 2>/dev/null || echo 'Not installed')"
	@echo "  Ruff: $$(ruff --version 2>/dev/null || echo 'Not installed')"
	@echo "  Pyright: $$(pyright --version 2>/dev/null | head -1 || echo 'Not installed')"
	@echo "  MkDocs: $$(mkdocs --version 2>/dev/null | sed 's/mkdocs, version //' | sed 's/ from.*//' || echo 'Not installed')"
	@echo "  Build: $$(python -m build --version 2>/dev/null | sed 's/build //' | sed 's/ (.*//' || echo 'Not installed')"
	@echo "  Twine: $$(python -m twine --version 2>/dev/null | grep -o 'twine version [0-9.]*' | cut -d' ' -f3 || echo 'Not installed')"
	@echo "  JsonSchema: $$(python -c 'import importlib.metadata; print(importlib.metadata.version("jsonschema"))' 2>/dev/null || echo 'Not installed')"
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
