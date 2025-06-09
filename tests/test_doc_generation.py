"""
Test API documentation generation functionality.

This script verifies that the API documentation generator script exists, is executable, and produces valid output.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_api_doc_generation_imports():
    """Test that the API documentation generator script can run and generate docs."""
    project_root = Path(__file__).parent.parent
    scripts_dir = project_root / "dev"
    generator_script = scripts_dir / "generate_api_docs.py"

    # Verify script exists
    assert generator_script.exists(), (
        f"Generator script not found at {generator_script}"
    )

    # Verify script is executable
    stat_info = generator_script.stat()
    assert stat_info.st_mode & 0o111, "Generator script is not executable"

    # Test that script can generate documentation to stdout (no file writes)
    try:
        result = subprocess.run(
            [sys.executable, str(generator_script)],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=project_root,
        )

        assert result.returncode == 0, (
            f"Generator script failed with code {result.returncode}:\n"
            f"STDOUT: {result.stdout[:1000]}...\n"
            f"STDERR: {result.stderr}"
        )

        # Verify the output contains expected documentation
        output = result.stdout
        assert len(output) > 10000, (
            f"Generated docs seem too short: {len(output)} characters"
        )
        assert "NetGraph API Reference (Auto-Generated)" in output, (
            "Missing expected header"
        )
        assert "ngraph.scenario" in output, "Module ngraph.scenario not found in output"
        assert "ngraph.network" in output, "Module ngraph.network not found in output"

    except subprocess.TimeoutExpired:
        pytest.fail("Generator script timed out - possible infinite loop")


def test_api_documentation_exists_and_valid():
    """Test that the existing API documentation file has valid content."""
    project_root = Path(__file__).parent.parent
    api_doc_path = project_root / "docs" / "reference" / "api-full.md"

    # The file should exist (generated separately via make docs)
    assert api_doc_path.exists(), (
        f"API documentation missing at {api_doc_path}. Run 'make docs' to generate it."
    )

    content = api_doc_path.read_text()

    # Verify substantial content
    assert len(content) > 10000, (
        f"API documentation seems too short: {len(content)} characters"
    )

    # Verify expected header
    assert "NetGraph API Reference (Auto-Generated)" in content, (
        "Missing expected header"
    )

    # Verify key modules are documented
    expected_modules = [
        "ngraph.scenario",
        "ngraph.network",
        "ngraph.components",
        "ngraph.lib.algorithms.spf",
    ]

    for module in expected_modules:
        assert module in content, f"Module {module} not found in documentation"

    # Verify it includes method documentation
    assert "**Methods:**" in content, "No method documentation found"
    assert "**Attributes:**" in content, "No attribute documentation found"


def test_api_doc_generator_can_run():
    """Test that the API documentation generator script can be executed without errors."""
    project_root = Path(__file__).parent.parent

    # Test dry-run: just check that the script can import its modules without crashing
    # We'll use Python's -c flag to test imports without actually generating docs
    test_code = """
import sys
sys.path.insert(0, ".")
try:
    import ngraph.scenario
    import ngraph.network
    import ngraph.components
    print("SUCCESS: All modules can be imported")
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=project_root,
    )

    assert result.returncode == 0, (
        f"API doc generator dependencies failed to import:\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    assert "SUCCESS" in result.stdout, "Expected success message not found"


def test_documentation_cross_references():
    """Test that documentation files properly cross-reference each other."""
    docs_dir = Path(__file__).parent.parent / "docs" / "reference"

    # Check main API guide
    api_md = docs_dir / "api.md"
    assert api_md.exists(), "Main API documentation missing"

    api_content = api_md.read_text()
    assert "api-full.md" in api_content, (
        "Main API guide doesn't reference auto-generated docs"
    )

    # Check auto-generated API docs
    api_full_md = docs_dir / "api-full.md"
    assert api_full_md.exists(), "Auto-generated API documentation missing"

    api_full_content = api_full_md.read_text()
    assert "api.md" in api_full_content, (
        "Auto-generated docs don't reference main API guide"
    )


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Skip integration test in CI to avoid circular dependency",
)
def test_scripts_directory_structure():
    """Test that dev directory has expected structure."""
    scripts_dir = Path(__file__).parent.parent / "dev"

    assert scripts_dir.exists(), "Dev directory missing"
    assert (scripts_dir / "generate_api_docs.py").exists(), (
        "API generator script missing"
    )

    # Verify script is executable
    generator_script = scripts_dir / "generate_api_docs.py"
    stat_info = generator_script.stat()
    assert stat_info.st_mode & 0o111, "Generator script is not executable"
