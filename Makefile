# NetGraph Development Makefile
# This Makefile provides convenient shortcuts for common development tasks

.PHONY: help setup install dev-install check test clean docs build check-dist publish-test publish docker-build docker-run

# Default target - show help
.DEFAULT_GOAL := help

help:
	@echo "🔧 NetGraph Development Commands"
	@echo ""
	@echo "Setup & Installation:"
	@echo "  make setup         - Full development environment setup (install + hooks)"
	@echo "  make install       - Install package in development mode (no dev deps)"
	@echo "  make dev-install   - Install package with all dev dependencies"
	@echo ""
	@echo "Code Quality & Testing:"
	@echo "  make check         - Run all pre-commit checks and tests"
	@echo "  make lint          - Run only linting (ruff + pyright)"
	@echo "  make format        - Auto-format code with ruff"
	@echo "  make test          - Run tests with coverage"
	@echo "  make test-quick    - Run tests without coverage"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs          - Generate API documentation"
	@echo "  make docs-test     - Test API documentation generation"
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
	@echo "Docker (if available):"
	@echo "  make docker-build  - Build Docker image"
	@echo "  make docker-run    - Run Docker container with Jupyter"
	@echo ""
	@echo "Utilities:"
	@echo "  make info          - Show project information"

# Setup and Installation
setup:
	@echo "🚀 Setting up development environment..."
	@bash dev/setup-dev.sh

install:
	@echo "📦 Installing package in development mode (no dev dependencies)..."
	pip install -e .

dev-install:
	@echo "📦 Installing package with dev dependencies..."
	pip install -e '.[dev]'

# Code Quality and Testing
check:
	@echo "🔍 Running complete code quality checks and tests..."
	@bash dev/run-checks.sh

lint:
	@echo "🧹 Running linting checks..."
	@pre-commit run ruff --all-files
	@pre-commit run pyright --all-files

format:
	@echo "✨ Auto-formatting code..."
	@pre-commit run ruff-format --all-files

test:
	@echo "🧪 Running tests with coverage..."
	@pytest

test-quick:
	@echo "⚡ Running tests without coverage..."
	@pytest --no-cov

# Documentation
docs:
	@echo "📚 Generating API documentation..."
	@echo "ℹ️  This regenerates docs/reference/api-full.md from source code"
	@python dev/generate_api_docs.py --write-file

docs-test:
	@echo "🧪 Testing API documentation generation..."
	@python dev/test_doc_generation.py

docs-serve:
	@echo "🌐 Serving documentation locally..."
	@if command -v mkdocs >/dev/null 2>&1; then \
		mkdocs serve; \
	else \
		echo "❌ mkdocs not installed. Install dev dependencies with: make dev-install"; \
		exit 1; \
	fi

# Build and Package
build:
	@echo "🏗️  Building distribution packages..."
	@if python -c "import build" >/dev/null 2>&1; then \
		python -m build; \
	else \
		echo "❌ build module not installed. Install dev dependencies with: make dev-install"; \
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

# Docker commands (optional)
docker-build:
	@echo "🐳 Building Docker image..."
	@if [ -f "Dockerfile" ]; then \
		bash run.sh build; \
	else \
		echo "❌ Dockerfile not found"; \
		exit 1; \
	fi

docker-run:
	@echo "🐳 Running Docker container with Jupyter..."
	@if [ -f "run.sh" ]; then \
		bash run.sh run; \
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
		echo "❌ twine not installed. Install dev dependencies with: make dev-install"; \
		exit 1; \
	fi

publish-test:
	@echo "📦 Publishing to Test PyPI..."
	@if python -c "import twine" >/dev/null 2>&1; then \
		python -m twine upload --repository testpypi dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev-install"; \
		exit 1; \
	fi

publish:
	@echo "🚀 Publishing to PyPI..."
	@if python -c "import twine" >/dev/null 2>&1; then \
		python -m twine upload dist/*; \
	else \
		echo "❌ twine not installed. Install dev dependencies with: make dev-install"; \
		exit 1; \
	fi

# Project Information
info:
	@echo "📋 NetGraph Project Information"
	@echo "================================"
	@echo "Python version: $$(python --version)"
	@echo "Package version: $$(python -c 'import ngraph; print(ngraph.__version__)' 2>/dev/null || echo 'Not installed')"
	@echo "Virtual environment: $$(echo $$VIRTUAL_ENV | sed 's|.*/||' || echo 'None active')"
	@echo "Pre-commit installed: $$(pre-commit --version 2>/dev/null || echo 'Not installed')"
	@echo "Git status:"
	@git status --porcelain | head -5 || echo "Not a git repository"
