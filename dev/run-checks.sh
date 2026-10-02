#!/bin/bash
# Run pre-commit (fix pass, then verify pass), schema validation, and all tests.

set -e

# make check passes PYTHON; default to python3 on PATH.
PYTHON=${PYTHON:-python3}

if ! "$PYTHON" -m pre_commit --version &> /dev/null; then
    echo "❌ pre-commit is not installed. Please run 'make dev' first."
    exit 1
fi

if ! "$PYTHON" -m pytest --version &> /dev/null; then
    echo "❌ pytest is not installed. Please run 'make dev' first."
    exit 1
fi

# Hooks live in the common git dir, shared by linked worktrees.
if [ ! -f "$(git rev-parse --git-path hooks/pre-commit)" ]; then
    echo "⚠️  Pre-commit hooks not installed. Installing now..."
    "$PYTHON" -m pre_commit install
    echo ""
fi

# First pass applies auto-fixes; a failure here is not fatal.
echo "🏃 Running pre-commit (first pass: apply auto-fixes if needed)..."
set +e
"$PYTHON" -m pre_commit run --all-files
first_pass_status=$?
set -e

if [ $first_pass_status -ne 0 ]; then
    echo "ℹ️  Some hooks modified files or reported issues. Re-running checks..."
fi

# Second pass must be clean.
echo "🏃 Running pre-commit (second pass: verify all checks)..."
if ! "$PYTHON" -m pre_commit run --all-files; then
    echo ""
    echo "❌ Pre-commit checks failed after applying fixes. Please address the issues above."
    exit 1
fi

autofixed=0
if [ $first_pass_status -ne 0 ]; then
    autofixed=1
fi

echo ""
echo "✅ Pre-commit checks passed!"
echo ""

make validate PYTHON="$PYTHON"
echo ""

# Run tests with coverage (includes slow tests); set -e aborts on failure
echo "🧪 Running tests with coverage..."
"$PYTHON" -m pytest

echo ""
if [ $autofixed -eq 1 ]; then
    echo "🎉 All checks and tests passed. Auto-fixes were applied by pre-commit."
else
    echo "🎉 All checks and tests passed."
fi
