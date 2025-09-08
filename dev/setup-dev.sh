#!/bin/bash
# Setup script for developers

set -euo pipefail

echo "🔧 Setting up development environment..."

# Choose Python interpreter (prefer python3.13 if available, fallback to python3)
PYTHON_FROM_ENV="${PYTHON:-}"
if [ -n "$PYTHON_FROM_ENV" ]; then
    PYTHON="$PYTHON_FROM_ENV"
else
    if command -v python3.13 >/dev/null 2>&1; then
        PYTHON="python3.13"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    else
        echo "❌ python3.13 or python3 not found. Please install Python 3.12+ and re-run."
        exit 1
    fi
fi

# Enforce minimal version >= 3.12
if ! "$PYTHON" -c 'import sys; assert sys.version_info >= (3,12)' 2>/dev/null; then
    echo "❌ Python >= 3.12 required. Found: $($PYTHON --version 2>&1). Install python3.13 and re-run."
    exit 1
fi

# Create virtual environment if missing
if [ ! -x "ngraph-venv/bin/python" ]; then
    echo "🧰 Creating virtual environment at ./ngraph-venv ..."
    "$PYTHON" -m venv ngraph-venv
fi

# Activate venv for this script and upgrade pip
source ngraph-venv/bin/activate
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
echo "   source ngraph-venv/bin/activate  # ✅ activates venv"
echo ""
echo "💡 Useful commands:"
echo "   make check      # ✅ ruff + pyright + schema + tests"
echo "   make qt         # ✅ quick tests (no slow/benchmark)"
echo "   make docs       # ✅ regenerate API docs"
