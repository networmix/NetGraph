"""Tests for standalone report generation functionality."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ngraph.report import ReportGenerator


@pytest.fixture
def sample_results():
    """Sample results data for testing."""
    return {
        "workflow": {
            "step1": {
                "step_type": "NetworkStats",
                "step_name": "step1",
                "execution_order": 0,
            },
            "step2": {
                "step_type": "CapacityEnvelopeAnalysis",
                "step_name": "step2",
                "execution_order": 1,
            },
        },
        "step1": {"node_count": 8, "link_count": 12},
        "step2": {"capacity_envelopes": {"flow1": {"max": 1000, "min": 500}}},
    }


@pytest.fixture
def results_file(sample_results):
    """Create temporary results file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_results, f)
        return Path(f.name)


def test_report_generator_init():
    """Test ReportGenerator initialization."""
    generator = ReportGenerator(Path("test.json"))
    assert generator.results_path == Path("test.json")
    assert generator._results == {}
    assert generator._workflow_metadata == {}


def test_load_results_missing_file():
    """Test loading results from missing file."""
    generator = ReportGenerator(Path("missing.json"))

    with pytest.raises(FileNotFoundError, match="Results file not found"):
        generator.load_results()


def test_load_results_invalid_json():
    """Test loading results from invalid JSON file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ invalid json }")
        invalid_path = Path(f.name)

    generator = ReportGenerator(invalid_path)

    with pytest.raises(ValueError, match="Invalid JSON"):
        generator.load_results()


def test_load_results_empty_data():
    """Test loading empty results data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({}, f)
        empty_path = Path(f.name)

    generator = ReportGenerator(empty_path)

    with pytest.raises(ValueError, match="Results file is empty"):
        generator.load_results()


def test_load_results_no_analysis_data():
    """Test loading results with only workflow metadata."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"workflow": {"step1": {}}}, f)
        metadata_only_path = Path(f.name)

    generator = ReportGenerator(metadata_only_path)

    with pytest.raises(ValueError, match="No analysis results found"):
        generator.load_results()


def test_load_results_success(results_file, sample_results):
    """Test successful results loading."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    assert generator._results == sample_results
    assert generator._workflow_metadata == sample_results["workflow"]


def test_generate_notebook_no_results():
    """Test generating notebook without loaded results."""
    generator = ReportGenerator(Path("test.json"))

    with pytest.raises(ValueError, match="No results loaded"):
        generator.generate_notebook()


@patch("ngraph.report.nbformat")
def test_generate_notebook_success(mock_nbformat, results_file):
    """Test successful notebook generation."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock nbformat
    mock_notebook = Mock()
    mock_nbformat.v4.new_notebook.return_value = mock_notebook
    mock_nbformat.v4.new_markdown_cell.return_value = Mock()
    mock_nbformat.v4.new_code_cell.return_value = Mock()

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test.ipynb"
        result = generator.generate_notebook(output_path)

        assert result == output_path
        assert output_path.exists()

        # Verify nbformat calls
        mock_nbformat.v4.new_notebook.assert_called_once()
        mock_nbformat.write.assert_called_once()


@patch("ngraph.report.subprocess.run")
def test_generate_html_report_success(mock_subprocess, results_file):
    """Test successful HTML report generation."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock successful subprocess call
    mock_subprocess.return_value = Mock(returncode=0)

    with tempfile.TemporaryDirectory() as tmpdir:
        notebook_path = Path(tmpdir) / "notebook.ipynb"
        html_path = Path(tmpdir) / "report.html"

        # Create mock notebook file
        notebook_path.write_text("{}")

        result = generator.generate_html_report(
            notebook_path=notebook_path, html_path=html_path, include_code=False
        )

        assert result == html_path

        # Verify subprocess was called with correct arguments
        mock_subprocess.assert_called_once()
        args = mock_subprocess.call_args[0][0]
        assert "jupyter" in args
        assert "nbconvert" in args
        assert "--execute" in args
        assert "--to" in args
        assert "html" in args
        assert "--no-input" in args  # Should exclude code


@patch("ngraph.report.subprocess.run")
def test_generate_html_report_with_code(mock_subprocess, results_file):
    """Test HTML report generation including code cells."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock successful subprocess call
    mock_subprocess.return_value = Mock(returncode=0)

    with tempfile.TemporaryDirectory() as tmpdir:
        notebook_path = Path(tmpdir) / "notebook.ipynb"
        html_path = Path(tmpdir) / "report.html"

        # Create mock notebook file
        notebook_path.write_text("{}")

        generator.generate_html_report(
            notebook_path=notebook_path, html_path=html_path, include_code=True
        )

        # Verify --no-input is NOT in the arguments
        args = mock_subprocess.call_args[0][0]
        assert "--no-input" not in args


@patch("ngraph.report.subprocess.run")
def test_generate_html_report_nbconvert_failure(mock_subprocess, results_file):
    """Test HTML report generation with nbconvert failure."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock failed subprocess call
    from subprocess import CalledProcessError

    mock_subprocess.side_effect = CalledProcessError(
        1, "nbconvert", stderr="Error message"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        notebook_path = Path(tmpdir) / "notebook.ipynb"
        html_path = Path(tmpdir) / "report.html"

        # Create mock notebook file
        notebook_path.write_text("{}")

        with pytest.raises(RuntimeError, match="Failed to generate HTML report"):
            generator.generate_html_report(
                notebook_path=notebook_path, html_path=html_path
            )


@patch("ngraph.report.ReportGenerator.generate_notebook")
@patch("ngraph.report.subprocess.run")
def test_generate_html_report_creates_notebook(
    mock_subprocess, mock_generate_notebook, results_file
):
    """Test HTML report generation creates notebook if it doesn't exist."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock successful subprocess call
    mock_subprocess.return_value = Mock(returncode=0)
    mock_generate_notebook.return_value = Path("notebook.ipynb")

    with tempfile.TemporaryDirectory() as tmpdir:
        notebook_path = Path(tmpdir) / "nonexistent.ipynb"
        html_path = Path(tmpdir) / "report.html"

        generator.generate_html_report(notebook_path=notebook_path, html_path=html_path)

        # Verify notebook generation was called
        mock_generate_notebook.assert_called_once_with(notebook_path)


def test_create_analysis_sections_with_registry(results_file):
    """Test that analysis sections are created based on registry."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    # Mock nbformat for testing internal methods
    with patch("ngraph.report.nbformat") as mock_nbformat:
        mock_notebook = Mock()
        mock_notebook.cells = []
        mock_nbformat.v4.new_notebook.return_value = mock_notebook
        mock_nbformat.v4.new_markdown_cell.return_value = Mock()
        mock_nbformat.v4.new_code_cell.return_value = Mock()

        notebook = generator._create_analysis_notebook()

        # Verify the notebook is returned and cells were added
        assert notebook is mock_notebook
        assert len(mock_notebook.cells) > 0

        # Verify markdown and code cells were created
        assert mock_nbformat.v4.new_markdown_cell.call_count > 0
        assert mock_nbformat.v4.new_code_cell.call_count > 0
