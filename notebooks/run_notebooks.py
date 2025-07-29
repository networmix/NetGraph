#!/usr/bin/env python3
"""Test script to validate all notebooks execute successfully.

This script executes all notebooks in the notebooks directory and reports
which ones pass or fail. Used to ensure notebooks stay current with API changes.
"""

import sys
from pathlib import Path

try:
    import nbformat  # type: ignore
    import pytest  # type: ignore
    from nbclient.exceptions import CellExecutionError  # type: ignore
    from nbconvert.preprocessors import ExecutePreprocessor  # type: ignore
except ImportError as e:
    print(f"Missing notebook dependencies: {e}")
    print("Run: pip install nbformat pytest nbclient nbconvert")
    sys.exit(1)


def execute_notebook(notebook_path: Path) -> tuple[bool, str]:
    """Test if a notebook executes successfully.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        Tuple of (success, error_message)
    """
    try:
        with open(notebook_path, "r") as f:
            nb = nbformat.read(f, as_version=4)

        ep = ExecutePreprocessor(timeout=600, kernel_name="python3")
        ep.preprocess(nb, {"metadata": {"path": str(notebook_path.parent)}})
        return True, ""

    except CellExecutionError as e:
        # This is a cell execution failure - the notebook ran but a cell failed
        error_msg = "Cell execution failed"

        if hasattr(e, "traceback") and e.traceback:
            # Extract the actual error from the traceback
            lines = e.traceback.split("\n")

            # Look for the final error line (usually the last non-empty line)
            error_lines = []
            for line in reversed(lines):
                line = line.strip()
                if (
                    line
                    and not line.startswith("Cell In")
                    and not line.startswith("File ")
                ):
                    if any(
                        err_type in line
                        for err_type in [
                            "Error:",
                            "Exception:",
                            "KeyError",
                            "AttributeError",
                            "NameError",
                            "TypeError",
                            "ValueError",
                            "ImportError",
                        ]
                    ):
                        error_lines.append(line)
                        break
                    elif line.startswith(
                        (
                            "KeyError",
                            "AttributeError",
                            "NameError",
                            "TypeError",
                            "ValueError",
                            "ImportError",
                        )
                    ):
                        error_lines.append(line)
                        break

            if error_lines:
                error_msg = error_lines[0]
            else:
                # Fallback: look for any line with "Error" or exception types
                for line in lines:
                    if (
                        any(word in line.lower() for word in ["error", "exception"])
                        and line.strip()
                    ):
                        error_msg = line.strip()
                        break

        return False, error_msg

    except FileNotFoundError:
        return False, f"Notebook file not found: {notebook_path}"

    except nbformat.ValidationError as e:
        return False, f"Invalid notebook format: {e}"

    except Exception as e:
        # Unexpected error during setup/reading
        return False, f"Unexpected error: {e}"


def get_notebook_files():
    """Get list of notebook files to test."""
    notebooks_dir = Path(__file__).parent
    notebook_files = list(notebooks_dir.glob("*.ipynb"))

    # Filter out checkpoint files and test files
    notebook_files = [
        f
        for f in notebook_files
        if not f.name.startswith(".")
        and "checkpoint" not in f.name.lower()
        and not f.name.startswith("test_")
    ]

    return sorted(notebook_files)


@pytest.mark.slow
@pytest.mark.parametrize("notebook_path", get_notebook_files())
def test_notebook_execution(notebook_path):
    """Test that a notebook executes successfully."""
    success, error_msg = execute_notebook(notebook_path)

    if not success:
        pytest.fail(f"Notebook {notebook_path.name} failed: {error_msg}")


def main():
    """Test all notebooks in the current directory (for standalone execution)."""
    notebooks_dir = Path(".")
    notebook_files = list(notebooks_dir.glob("*.ipynb"))

    # Filter out checkpoint files and test files
    notebook_files = [
        f
        for f in notebook_files
        if not f.name.startswith(".")
        and "checkpoint" not in f.name.lower()
        and not f.name.startswith("test_")
    ]

    if not notebook_files:
        print("No notebook files found in current directory")
        return 1

    print(f"Testing {len(notebook_files)} notebooks...")
    print()

    passed = 0
    failed = 0
    failures = []

    for notebook_path in sorted(notebook_files):
        print(f"Testing {notebook_path.name}...", end=" ")
        success, error_msg = execute_notebook(notebook_path)

        if success:
            print("✅ PASS")
            passed += 1
        else:
            print("❌ FAIL")
            failures.append((notebook_path.name, error_msg))
            failed += 1

    print()
    print(f"Results: {passed} passed, {failed} failed")

    if failed > 0:
        print()
        for name, error in failures:
            print(f"❌ {name}: {error}")
        return 1
    else:
        print("✅ All notebooks executed successfully")
        return 0


if __name__ == "__main__":
    sys.exit(main())
