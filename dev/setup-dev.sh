#!/bin/bash
# Setup script for developers

echo "🔧 Setting up development environment..."

# Install the package with dev dependencies
echo "📦 Installing package with dev dependencies..."
pip install -e '.[dev]'

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Run pre-commit on all files to ensure everything is set up correctly
echo "✅ Running pre-commit checks..."
pre-commit run --all-files

echo "🎉 Development environment setup complete!"
echo ""
echo "🚀 You're ready to contribute! Pre-commit hooks will now run automatically on each commit."
echo "💡 To manually run all checks: pre-commit run --all-files"
