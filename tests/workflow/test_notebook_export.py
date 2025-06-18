from pathlib import Path
from unittest.mock import MagicMock

import nbformat
import pytest

from ngraph.results import Results
from ngraph.scenario import Scenario
from ngraph.workflow.notebook_export import NotebookExport


def test_notebook_export_creates_file(tmp_path: Path) -> None:
    """Test basic notebook creation with simple results."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()
    scenario.results.put("step1", "value", 123)

    output_file = tmp_path / "out.ipynb"
    json_file = tmp_path / "out.json"
    step = NotebookExport(
        name="nb", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    assert any(cell.cell_type == "code" for cell in nb.cells)

    stored_path = scenario.results.get("nb", "notebook_path")
    assert stored_path == str(output_file)


def test_notebook_export_empty_results_throws_exception(tmp_path: Path) -> None:
    """Test that empty results throw an exception by default."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    output_file = tmp_path / "empty.ipynb"
    json_file = tmp_path / "empty.json"
    step = NotebookExport(
        name="empty_nb", notebook_path=str(output_file), json_path=str(json_file)
    )

    with pytest.raises(ValueError, match="No analysis results found"):
        step.run(scenario)

    # File should not be created when exception is thrown
    assert not output_file.exists()


def test_notebook_export_empty_results_with_allow_flag(tmp_path: Path) -> None:
    """Test notebook creation when no results are available but allow_empty_results=True."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    output_file = tmp_path / "empty.ipynb"
    json_file = tmp_path / "empty_allow.json"
    step = NotebookExport(
        name="empty_nb",
        notebook_path=str(output_file),
        json_path=str(json_file),
        allow_empty_results=True,
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    assert len(nb.cells) >= 1
    assert any("No analysis results" in cell.source for cell in nb.cells)


def test_notebook_export_with_capacity_envelopes(tmp_path: Path) -> None:
    """Test notebook creation with capacity envelope data."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    # Add capacity envelope data
    envelope_data = {
        "flow1": {"values": [100, 150, 200, 180, 220], "min": 100, "max": 220},
        "flow2": {"values": [80, 90, 85, 95, 88], "min": 80, "max": 95},
    }
    scenario.results.put("CapacityAnalysis", "capacity_envelopes", envelope_data)

    output_file = tmp_path / "envelopes.ipynb"
    json_file = tmp_path / "envelopes.json"
    step = NotebookExport(
        name="env_nb", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    # Should have cells for capacity matrix analysis
    assert any(
        "## Capacity Matrix Analysis" in cell.source
        for cell in nb.cells
        if hasattr(cell, "source")
    )


def test_notebook_export_with_flow_data(tmp_path: Path) -> None:
    """Test notebook creation with flow analysis data."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    # Add flow data
    scenario.results.put("FlowProbe", "max_flow:[node1 -> node2]", 150.5)
    scenario.results.put("FlowProbe", "max_flow:[node2 -> node3]", 200.0)

    output_file = tmp_path / "flows.ipynb"
    json_file = tmp_path / "flows.json"
    step = NotebookExport(
        name="flow_nb", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    # Should have cells for flow analysis
    assert any(
        "Flow Analysis" in cell.source for cell in nb.cells if hasattr(cell, "source")
    )


def test_notebook_export_mixed_data(tmp_path: Path) -> None:
    """Test notebook creation with multiple types of analysis results."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    # Add various types of data
    scenario.results.put("TopologyAnalysis", "node_count", 50)
    scenario.results.put("TopologyAnalysis", "edge_count", 120)

    envelope_data = {
        "critical_path": {"values": [100, 110, 105], "min": 100, "max": 110}
    }
    scenario.results.put(
        "CapacityEnvelopeAnalysis", "capacity_envelopes", envelope_data
    )

    scenario.results.put("MaxFlowProbe", "max_flow:[source -> sink]", 250.0)

    output_file = tmp_path / "mixed.ipynb"
    json_file = tmp_path / "mixed.json"
    step = NotebookExport(
        name="mixed_nb", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    # Should contain multiple analysis sections
    cell_contents = " ".join(
        cell.source for cell in nb.cells if hasattr(cell, "source")
    )
    assert "## Capacity Matrix Analysis" in cell_contents
    assert "## Flow Analysis" in cell_contents
    assert "## Summary" in cell_contents


def test_notebook_export_creates_output_directory(tmp_path: Path) -> None:
    """Test that output directory is created if it doesn't exist."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()
    scenario.results.put("test", "data", "value")

    nested_dir = tmp_path / "nested" / "path"
    output_file = nested_dir / "output.ipynb"
    json_file = nested_dir / "output.json"

    step = NotebookExport(
        name="dir_test", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()
    assert nested_dir.exists()


def test_notebook_export_configuration_options(tmp_path: Path) -> None:
    """Test various configuration options."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()
    scenario.results.put("test", "data", list(range(200)))  # Large dataset

    output_file = tmp_path / "config.ipynb"
    json_file = tmp_path / "config.json"
    step = NotebookExport(
        name="config_nb",
        notebook_path=str(output_file),
        json_path=str(json_file),
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    # Check that notebook was created successfully with configuration
    cell_contents = " ".join(
        cell.source for cell in nb.cells if hasattr(cell, "source")
    )
    # Verify the notebook contains our analysis infrastructure
    assert "DataLoader" in cell_contents
    assert "PackageManager" in cell_contents
    # Verify it has the expected structure
    assert "## Summary" in cell_contents


def test_notebook_export_large_dataset(tmp_path: Path) -> None:
    """Test handling of large datasets."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    # Create large dataset
    large_data = {f"item_{i}": f"value_{i}" * 100 for i in range(100)}
    scenario.results.put("LargeDataStep", "large_dict", large_data)

    output_file = tmp_path / "large.ipynb"
    json_file = tmp_path / "large.json"
    step = NotebookExport(
        name="large_nb", notebook_path=str(output_file), json_path=str(json_file)
    )
    step.run(scenario)

    assert output_file.exists()

    nb = nbformat.read(output_file, as_version=4)
    # Should handle large data gracefully
    assert len(nb.cells) > 0


@pytest.mark.parametrize(
    "bad_path",
    [
        "/root/cannot_write_here.ipynb",  # Permission denied (on most systems)
        "",  # Empty path
    ],
)
def test_notebook_export_invalid_paths(bad_path: str) -> None:
    """Test handling of invalid output paths."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()
    scenario.results.put("test", "data", "value")

    step = NotebookExport(
        name="bad_path", notebook_path=bad_path, json_path="/tmp/test.json"
    )

    # Should handle gracefully or raise appropriate exception
    if bad_path == "":
        with pytest.raises((ValueError, OSError, TypeError)):
            step.run(scenario)
    else:
        # For permission errors, it might succeed or fail depending on system
        try:
            step.run(scenario)
        except (PermissionError, OSError):
            pass  # Expected for permission denied


def test_notebook_export_serialization_error_handling(tmp_path: Path) -> None:
    """Test handling of data that's difficult to serialize."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()

    # Add data that might cause serialization issues
    class UnserializableClass:
        def __str__(self):
            return "UnserializableObject"

    scenario.results.put("problem_step", "unserializable", UnserializableClass())

    output_file = tmp_path / "serialization.ipynb"
    json_file = tmp_path / "serialization.json"
    step = NotebookExport(
        name="ser_nb", notebook_path=str(output_file), json_path=str(json_file)
    )

    # Should handle gracefully with default=str in json.dumps
    step.run(scenario)

    assert output_file.exists()
    nb = nbformat.read(output_file, as_version=4)
    assert len(nb.cells) > 0


def test_flow_availability_detection() -> None:
    """Test detection of flow availability data."""
    export_step = NotebookExport()

    # Results with bandwidth availability data
    results_with_bandwidth = {
        "capacity_analysis": {
            "capacity_envelopes": {"flow1": {"percentiles": [10, 20, 30]}},
            "total_capacity_samples": [100.0, 90.0, 80.0],
        }
    }

    # Results without bandwidth availability data
    results_without_bandwidth = {
        "capacity_analysis": {
            "capacity_envelopes": {"flow1": {"percentiles": [10, 20, 30]}}
        }
    }

    # Results with empty bandwidth availability data
    results_empty_bandwidth = {
        "capacity_analysis": {
            "capacity_envelopes": {"flow1": {"percentiles": [10, 20, 30]}},
            "total_capacity_samples": [],
        }
    }

    # Test detection
    assert export_step._has_flow_availability_data(results_with_bandwidth) is True
    assert export_step._has_flow_availability_data(results_without_bandwidth) is False
    assert export_step._has_flow_availability_data(results_empty_bandwidth) is False


def test_notebook_includes_flow_availability(tmp_path: Path) -> None:
    """Test that notebook includes flow availability analysis when data is present."""
    scenario = MagicMock(spec=Scenario)
    scenario.results = Results()
    scenario.results.put(
        "capacity_envelope",
        "capacity_envelopes",
        {"dc1->edge1": {"percentiles": [80, 85, 90, 95, 100]}},
    )
    scenario.results.put(
        "capacity_envelope",
        "total_capacity_samples",
        [100.0, 95.0, 90.0, 85.0, 80.0, 75.0],
    )

    export_step = NotebookExport(
        name="test_export",
        notebook_path=str(tmp_path / "test.ipynb"),
        json_path=str(tmp_path / "test.json"),
    )

    # Run the export
    export_step.run(scenario)

    # Check that notebook was created
    notebook_path = tmp_path / "test.ipynb"
    assert notebook_path.exists()

    # Read and verify notebook content
    with open(notebook_path, "r") as f:
        nb_content = f.read()

    # Should contain flow availability analysis
    assert "Flow Availability Analysis" in nb_content
    assert "analyze_and_display_flow_availability" in nb_content
