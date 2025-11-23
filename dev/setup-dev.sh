#!/bin/bash
# Setup script for developers

set -euo pipefail

echo "🔧 Setting up development environment..."

# Choose Python interpreter
PYTHON="python3"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "❌ python3 not found. Please install Python 3.11+ and re-run."
    exit 1
fi

# Create virtual environment if missing
if [ ! -x "venv/bin/python" ]; then
    echo "🧰 Creating virtual environment at ./venv ..."
    "$PYTHON" -m venv venv
fi

# Activate venv for this script and upgrade pip
source venv/bin/activate
PYTHON_VENV="$(command -v python)"

echo "⬆️  Upgrading pip/setuptools/wheel in venv..."
"$PYTHON_VENV" -m pip install -U pip setuptools wheel

# Install the package with dev dependencies in venv
echo "📦 Installing package with dev dependencies..."
"$PYTHON_VENV" -m pip install -e '.[dev]'

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
"$PYTHON_VENV" -m pre_commit install

# Run pre-commit on all files to ensure everything is set up correctly
echo "✅ Running pre-commit checks..."
"$PYTHON_VENV" -m pre_commit run --all-files || true

echo "🎉 Development environment setup complete!"
echo ""
echo "👉 To use the environment in your shell, run:"
echo "   source venv/bin/activate  # ✅ activates venv"
echo ""
echo "💡 Useful commands:"
echo "   make check      # ✅ ruff + pyright + schema + tests"
echo "   make qt         # ✅ quick tests (no slow/benchmark)"
echo "   make docs       # ✅ regenerate API docs"
