#!/bin/bash
# Run all code quality checks and tests
# This script runs the complete validation suite: pre-commit hooks + schema validation + tests

set -e  # Exit on any error

# Check if pre-commit is installed
if ! command -v pre-commit &> /dev/null; then
    echo "❌ pre-commit is not installed. Please run 'pip install pre-commit' first."
    exit 1
fi

# Check if pytest is installed
if ! command -v pytest &> /dev/null; then
    echo "❌ pytest is not installed. Please run 'pip install -e .[dev]' first."
    exit 1
fi

# Check if pre-commit hooks are installed
if [ ! -f .git/hooks/pre-commit ]; then
    echo "⚠️  Pre-commit hooks not installed. Installing now..."
    pre-commit install
    echo ""
fi

# Run pre-commit checks
echo "🏃 Running pre-commit on all files..."
pre-commit run --all-files

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Pre-commit checks failed. Please fix the issues above before running tests."
    echo "💡 Tip: Most formatting issues can be auto-fixed by running the checks again."
    exit 1
fi

echo ""
echo "✅ Pre-commit checks passed!"
echo ""

# Run schema validation
echo "📋 Validating YAML schemas..."
if python -c "import jsonschema" >/dev/null 2>&1; then
    python -c "import json, yaml, jsonschema, pathlib; \
    schema = json.load(open('schemas/scenario.json')); \
    scenario_files = list(pathlib.Path('scenarios').rglob('*.yaml')); \
    integration_files = list(pathlib.Path('tests/integration').glob('*.yaml')); \
    all_files = scenario_files + integration_files; \
    [jsonschema.validate(yaml.safe_load(open(f)), schema) for f in all_files]; \
    print(f'✅ Validated {len(all_files)} YAML files against schema ({len(scenario_files)} scenarios, {len(integration_files)} integration tests)')"

    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ Schema validation failed. Please fix the YAML files above."
        exit 1
    fi
else
    echo "⚠️  jsonschema not installed. Skipping schema validation"
fi

echo ""

# Run tests with coverage (includes slow and benchmark tests for regression detection)
echo "🧪 Running tests with coverage..."
pytest

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 All checks and tests passed! Your code is ready for commit."
else
    echo ""
    echo "❌ Some tests failed. Please fix the issues above and try again."
    exit 1
fi
