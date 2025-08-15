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
                "step_type": "MaxFlow",
                "step_name": "step2",
                "execution_order": 1,
            },
        },
        "steps": {
            "step1": {"data": {"node_count": 8, "link_count": 12}},
            "step2": {"data": {"flow_results": []}},
        },
    }


@pytest.fixture
def results_file(sample_results):
    """Create temporary results file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(sample_results, f)
        return Path(f.name)


@pytest.mark.parametrize(
    "include_code, expect_no_input",
    [
        (False, True),
        (True, False),
    ],
)
@patch("ngraph.report.subprocess.run")
def test_generate_html_report_args(
    mock_subprocess, results_file, include_code, expect_no_input
):
    """Ensure HTML export builds expected nbconvert args with/without code cells."""
    generator = ReportGenerator(results_file)
    generator.load_results()

    mock_subprocess.return_value = Mock(returncode=0)

    with tempfile.TemporaryDirectory() as tmpdir:
        notebook_path = Path(tmpdir) / "notebook.ipynb"
        html_path = Path(tmpdir) / "report.html"

        notebook_path.write_text("{}")

        result = generator.generate_html_report(
            notebook_path=notebook_path,
            html_path=html_path,
            include_code=include_code,
        )

        assert result == html_path

        args = mock_subprocess.call_args[0][0]
        assert "jupyter" in args
        assert "nbconvert" in args
        assert "--execute" in args
        assert "--to" in args and "html" in args
        assert ("--no-input" in args) == expect_no_input


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


def test_notebook_subtitle_matches_results_file(tmp_path: Path) -> None:
    """Notebook should include a subtitle with the results filename."""
    # Create a deterministic results file name
    results_path = tmp_path / "baseline_run.json"
    results_path.write_text(
        json.dumps(
            {
                "workflow": {
                    "step1": {
                        "step_type": "NetworkStats",
                        "step_name": "step1",
                        "execution_order": 0,
                    }
                },
                "steps": {"step1": {"data": {}}},
            }
        )
    )

    generator = ReportGenerator(results_path)
    generator.load_results()

    nb = generator._create_analysis_notebook()

    # First two cells are title and subtitle
    assert len(nb.cells) >= 2
    assert nb.cells[0].cell_type == "markdown"
    assert "# NetGraph Results Analysis" in nb.cells[0]["source"]

    assert nb.cells[1].cell_type == "markdown"
    assert nb.cells[1]["source"] == f"### {results_path.name}"
