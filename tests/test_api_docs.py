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
    """Test that the API documentation generator script exists and is executable."""
    scripts_dir = Path(__file__).parent.parent / "dev"
    generator_script = scripts_dir / "generate_api_docs.py"

    # Verify script exists
    assert (
        generator_script.exists()
    ), f"Generator script not found at {generator_script}"

    # Verify script is executable
    stat_info = generator_script.stat()
    assert stat_info.st_mode & 0o111, "Generator script is not executable"

    # Test that script can be run with --help or similar (quick syntax check)
    try:
        result = subprocess.run(
            [sys.executable, str(generator_script), "--help"],
            capture_output=True,
            timeout=10,
            cwd=scripts_dir.parent,  # Run from project root
        )
        # Script might not support --help, but it should at least not crash with syntax errors
        # Exit code 0 (success) or 2 (argument error) are both acceptable
        assert result.returncode in [
            0,
            2,
        ], f"Script syntax check failed with code {result.returncode}"
    except subprocess.TimeoutExpired:
        pytest.fail("Generator script timed out - possible infinite loop")


def test_api_doc_generation_output():
    """Test that API documentation generation produces valid output."""
    scripts_dir = Path(__file__).parent.parent / "dev"
    generator_script = scripts_dir / "generate_api_docs.py"
    project_root = Path(__file__).parent.parent

    # Run the generator script
    result = subprocess.run(
        [sys.executable, str(generator_script)],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=project_root,  # Run from project root (required by generator)
    )

    # Check that script ran successfully
    assert (
        result.returncode == 0
    ), f"Generator script failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"

    # Verify the file was created and has content
    api_doc_path = project_root / "docs" / "reference" / "api-full.md"

    assert api_doc_path.exists(), f"API documentation not generated at {api_doc_path}"

    content = api_doc_path.read_text()

    # Verify substantial content
    assert (
        len(content) > 10000
    ), f"API documentation seems too short: {len(content)} characters"

    # Verify expected header
    assert (
        "NetGraph API Reference (Auto-Generated)" in content
    ), "Missing expected header"

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


def test_documentation_cross_references():
    """Test that documentation files properly cross-reference each other."""
    docs_dir = Path(__file__).parent.parent / "docs" / "reference"

    # Check main API guide
    api_md = docs_dir / "api.md"
    assert api_md.exists(), "Main API documentation missing"

    api_content = api_md.read_text()
    assert (
        "api-full.md" in api_content
    ), "Main API guide doesn't reference auto-generated docs"

    # Check auto-generated API docs
    api_full_md = docs_dir / "api-full.md"
    assert api_full_md.exists(), "Auto-generated API documentation missing"

    api_full_content = api_full_md.read_text()
    assert (
        "api.md" in api_full_content
    ), "Auto-generated docs don't reference main API guide"


@pytest.mark.skipif(
    os.environ.get("CI") == "true",
    reason="Skip integration test in CI to avoid circular dependency",
)
def test_scripts_directory_structure():
    """Test that dev directory has expected structure."""
    scripts_dir = Path(__file__).parent.parent / "dev"

    assert scripts_dir.exists(), "Dev directory missing"
    assert (
        scripts_dir / "generate_api_docs.py"
    ).exists(), "API generator script missing"

    # Verify script is executable
    generator_script = scripts_dir / "generate_api_docs.py"
    stat_info = generator_script.stat()
    assert stat_info.st_mode & 0o111, "Generator script is not executable"
