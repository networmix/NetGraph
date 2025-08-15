"""Tests for notebook analysis components."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ngraph.workflow.analysis import (
    AnalysisContext,
    CapacityMatrixAnalyzer,
    DataLoader,
    NotebookAnalyzer,
    PackageManager,
    SummaryAnalyzer,
)


class TestAnalysisContext:
    """Test AnalysisContext dataclass."""

    def test_analysis_context_creation(self) -> None:
        """Test creating AnalysisContext."""
        context = AnalysisContext(
            step_name="test_step",
            results={"data": "value"},
            config={"setting": "value"},
        )

        assert context.step_name == "test_step"
        assert context.results == {"data": "value"}
        assert context.config == {"setting": "value"}


class TestCapacityMatrixAnalyzer:
    """Test CapacityMatrixAnalyzer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CapacityMatrixAnalyzer()


class TestPackageManager:
    """Test PackageManager."""

    def test_required_packages(self) -> None:
        """Test required packages are defined."""
        assert "itables" in PackageManager.REQUIRED_PACKAGES
        assert "matplotlib" in PackageManager.REQUIRED_PACKAGES

    @patch("importlib.import_module")
    def test_check_and_install_packages_all_available(
        self, mock_import: MagicMock
    ) -> None:
        """Test when all packages are available."""
        mock_import.return_value = MagicMock()

        result = PackageManager.check_and_install_packages()

        assert result["missing_packages"] == []
        assert result["installation_needed"] is False
        assert result["message"] == "All required packages are available"

    @patch("subprocess.check_call")
    @patch("importlib.import_module")
    def test_check_and_install_packages_missing(
        self, mock_import: MagicMock, mock_subprocess: MagicMock
    ) -> None:
        """Test when packages are missing and need installation."""

        # Mock import to raise ImportError for one package
        def side_effect(package_name: str) -> MagicMock:
            if package_name == "itables":
                raise ImportError("Package not found")
            return MagicMock()

        mock_import.side_effect = side_effect
        mock_subprocess.return_value = None

        result = PackageManager.check_and_install_packages()

        assert "itables" in result["missing_packages"]
        assert result["installation_needed"] is True
        assert result["installation_success"] is True
        # The mocked subprocess call should work without errors

    @patch("importlib.import_module")
    def test_check_and_install_packages_installation_failure(
        self, mock_import: MagicMock
    ) -> None:
        """Test when package installation fails."""

        # Mock import to raise ImportError for one package
        def side_effect(package_name: str) -> MagicMock:
            if package_name == "itables":
                raise ImportError("Package not found")
            return MagicMock()

        mock_import.side_effect = side_effect

        # Mock the entire check_and_install_packages with a failure scenario
        with patch.object(PackageManager, "check_and_install_packages") as mock_method:
            mock_method.return_value = {
                "missing_packages": ["itables"],
                "installation_needed": True,
                "installation_success": False,
                "error": "Mock installation failure",
                "message": "Installation failed: Mock installation failure",
            }

            result = PackageManager.check_and_install_packages()

            assert "itables" in result["missing_packages"]
            assert result["installation_needed"] is True
            assert result["installation_success"] is False
            assert "error" in result

    @patch("warnings.filterwarnings")
    @patch("ngraph.workflow.analysis.plt.style.use")
    @patch("ngraph.workflow.analysis.itables_opt")
    def test_setup_environment_success(
        self,
        mock_itables_opt: MagicMock,
        mock_plt_style: MagicMock,
        mock_warnings: MagicMock,
    ) -> None:
        """Test successful environment setup."""
        with patch.object(PackageManager, "check_and_install_packages") as mock_check:
            mock_check.return_value = {"installation_success": True}

            result = PackageManager.setup_environment()

            assert result["status"] == "success"
            mock_plt_style.assert_called_once()
            mock_warnings.assert_called_once()

    def test_setup_environment_installation_failure(self) -> None:
        """Test environment setup when installation fails."""
        with patch.object(PackageManager, "check_and_install_packages") as mock_check:
            mock_check.return_value = {
                "installation_success": False,
                "message": "Installation failed",
            }

            result = PackageManager.setup_environment()

            assert result["installation_success"] is False
            assert result["message"] == "Installation failed"

    @patch("warnings.filterwarnings")
    @patch("ngraph.workflow.analysis.plt.style.use")
    def test_setup_environment_exception(
        self, mock_plt_style: MagicMock, mock_warnings: MagicMock
    ) -> None:
        """Test environment setup when configuration fails."""
        mock_plt_style.side_effect = Exception("Style error")

        with patch.object(PackageManager, "check_and_install_packages") as mock_check:
            mock_check.return_value = {"installation_success": True}

            result = PackageManager.setup_environment()

            assert result["status"] == "error"
            assert "Environment setup failed" in result["message"]


class TestDataLoader:
    """Test DataLoader."""

    def test_load_results_file_not_found(self) -> None:
        """Test loading from non-existent file."""
        result = DataLoader.load_results("/nonexistent/path.json")

        assert result["success"] is False
        assert "Results file not found" in result["message"]
        assert result["results"] == {}

    def test_load_results_invalid_json(self) -> None:
        """Test loading invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name

        try:
            result = DataLoader.load_results(temp_path)

            assert result["success"] is False
            assert "Invalid JSON format" in result["message"]
            assert result["results"] == {}
        finally:
            Path(temp_path).unlink()

    def test_load_results_not_dict(self) -> None:
        """Test loading JSON that's not a dictionary."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(["not", "a", "dict"], f)
            temp_path = f.name

        try:
            result = DataLoader.load_results(temp_path)

            assert result["success"] is False
            assert "Invalid results format - expected dictionary" in result["message"]
            assert result["results"] == {}
        finally:
            Path(temp_path).unlink()

    def test_load_results_success(self) -> None:
        """Test successful loading of results."""
        test_data = {
            "workflow": {},
            "steps": {"step1": {"data": "value1"}, "step2": {"data": "value2"}},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = DataLoader.load_results(temp_path)

            assert result["success"] is True
            assert result["results"] == test_data
            assert result["step_count"] == 2
            assert set(result["step_names"]) == {"step1", "step2"}
            assert "Loaded 2 analysis steps" in result["message"]
        finally:
            Path(temp_path).unlink()

    def test_load_results_with_pathlib_path(self) -> None:
        """Test loading with pathlib.Path object."""
        test_data = {"workflow": {}, "steps": {"step1": {"data": "value"}}}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            result = DataLoader.load_results(temp_path)

            assert result["success"] is True
            assert result["results"] == test_data
        finally:
            temp_path.unlink()

    def test_load_results_general_exception(self) -> None:
        """Test loading with general exception (like permission error)."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", side_effect=PermissionError("Access denied")),
        ):
            result = DataLoader.load_results("/some/path.json")

            assert result["success"] is False
            assert "Error loading results" in result["message"]
            assert "Access denied" in result["message"]


class TestSummaryAnalyzer:
    """Test SummaryAnalyzer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = SummaryAnalyzer()

    def test_get_description(self) -> None:
        """Test get_description method."""
        description = self.analyzer.get_description()
        assert "summary" in description.lower()

    def test_analyze_empty_results(self) -> None:
        """Test analyze with empty results."""
        results = {}
        analysis = self.analyzer.analyze(results)

        assert analysis["status"] == "success"
        assert analysis["total_steps"] == 0
        assert analysis["capacity_steps"] == 0
        assert analysis["flow_steps"] == 0
        assert analysis["other_steps"] == 0

    def test_analyze_mixed_results(self) -> None:
        """Test analyze with mixed result types in new schema."""
        results = {
            "steps": {
                "capacity_step": {"data": {"flow_results": [{}]}},
                "flow_step": {"data": {"flow_results": [{}]}},
                "other_step": {"data": {"x": 1}},
                "combined_step": {"data": {"y": 2}},
            }
        }

        analysis = self.analyzer.analyze(results)

        assert analysis["status"] == "success"
        assert analysis["total_steps"] == 4
        assert analysis["capacity_steps"] == 2
        assert analysis["flow_steps"] == 0
        assert analysis["other_steps"] == 2

    def test_analyze_non_dict_step(self) -> None:
        """Test analyze with non-dict step data."""
        results = {
            "steps": {
                "valid_step": {"data": {"flow_results": []}},
                "invalid_step": "not_a_dict",
                "another_invalid": ["also", "not", "dict"],
            }
        }

        analysis = self.analyzer.analyze(results)

        assert analysis["status"] == "success"
        assert analysis["total_steps"] == 3
        assert analysis["capacity_steps"] == 1
        assert analysis["flow_steps"] == 0
        assert analysis["other_steps"] == 2

    @patch("builtins.print")
    def test_display_analysis(self, mock_print: MagicMock) -> None:
        """Test display_analysis method."""
        analysis = {
            "total_steps": 5,
            "capacity_steps": 2,
            "flow_steps": 0,
            "other_steps": 3,
        }

        self.analyzer.display_analysis(analysis)

        # Check that summary information is printed
        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("NetGraph Analysis Summary" in call for call in calls)
        assert any("Total Analysis Steps: 5" in call for call in calls)
        assert any("Steps with flow_results: 2" in call for call in calls)
        assert any("Other Data Steps: 3" in call for call in calls)

    @patch("builtins.print")
    def test_display_analysis_no_results(self, mock_print: MagicMock) -> None:
        """Test display_analysis with no results."""
        analysis = {
            "total_steps": 0,
            "capacity_steps": 0,
            "flow_steps": 0,
            "other_steps": 0,
        }

        self.analyzer.display_analysis(analysis)

        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("❌ No analysis results found" in call for call in calls)

    @patch("builtins.print")
    def test_analyze_and_display_summary(self, mock_print: MagicMock) -> None:
        """Test analyze_and_display method."""
        results = {"steps": {"step1": {"data": "value"}}}
        self.analyzer.analyze_and_display(results)

        # Should call both analyze and display_analysis
        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("NetGraph Analysis Summary" in call for call in calls)

    @patch("builtins.print")
    def test_analyze_network_stats_success(self, mock_print: MagicMock) -> None:
        """Test analyze_network_stats with complete data."""
        results = {
            "steps": {
                "network_step": {
                    "node_count": 50,
                    "link_count": 100,
                    "total_capacity": 1000.0,
                    "mean_capacity": 10.0,
                    "median_capacity": 8.5,
                    "min_capacity": 1.0,
                    "max_capacity": 50.0,
                    "mean_cost": 25.5,
                    "median_cost": 20.0,
                    "min_cost": 5.0,
                    "max_cost": 100.0,
                    "mean_degree": 4.2,
                    "median_degree": 4.0,
                    "min_degree": 2.0,
                    "max_degree": 8.0,
                }
            }
        }

        self.analyzer.analyze_network_stats(results, step_name="network_step")

        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("📊 Network Statistics: network_step" in call for call in calls)
        assert any("Nodes: 50" in call for call in calls)
        assert any("Links: 100" in call for call in calls)
        assert any("Total Capacity: 1,000.00" in call for call in calls)
        assert any("Mean Capacity: 10.00" in call for call in calls)
        assert any("Mean Cost: 25.50" in call for call in calls)
        assert any("Mean Degree: 4.2" in call for call in calls)

    @patch("builtins.print")
    def test_analyze_network_stats_partial_data(self, mock_print: MagicMock) -> None:
        """Test analyze_network_stats with partial data."""
        results = {
            "steps": {
                "partial_step": {
                    "node_count": 25,
                    "mean_capacity": 15.0,
                    "max_degree": 6.0,
                    # Missing many optional fields
                }
            }
        }

        self.analyzer.analyze_network_stats(results, step_name="partial_step")

        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("📊 Network Statistics: partial_step" in call for call in calls)
        assert any("Nodes: 25" in call for call in calls)
        assert any("Mean Capacity: 15.00" in call for call in calls)
        assert any("Max Degree: 6.0" in call for call in calls)
        # Should not display missing fields
        assert not any("Links:" in call for call in calls)
        assert not any("Cost Statistics:" in call for call in calls)

    def test_analyze_network_stats_missing_step_name(self) -> None:
        """Test analyze_network_stats without step_name."""
        results = {"steps": {"step": {"data": "value"}}}

        with pytest.raises(ValueError, match="No step name provided"):
            self.analyzer.analyze_network_stats(results)

    def test_analyze_network_stats_step_not_found(self) -> None:
        """Test analyze_network_stats with non-existent step."""
        results = {"steps": {"other_step": {"data": "value"}}}

        with pytest.raises(ValueError, match="No data found for step: missing_step"):
            self.analyzer.analyze_network_stats(results, step_name="missing_step")

    def test_analyze_network_stats_empty_step_data(self) -> None:
        """Test analyze_network_stats with empty step data."""
        results = {"steps": {"empty_step": {}}}

        with pytest.raises(ValueError, match="No data found for step: empty_step"):
            self.analyzer.analyze_network_stats(results, step_name="empty_step")

    @patch("builtins.print")
    def test_analyze_build_graph_success(self, mock_print: MagicMock) -> None:
        """Test analyze_build_graph with graph data."""
        results = {
            "graph_step": {
                "graph": {"nodes": ["A", "B"], "edges": [("A", "B")]},
                "metadata": "some_data",
            }
        }

        self.analyzer.analyze_build_graph(results, step_name="graph_step")

        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("🔗 Graph Construction: graph_step" in call for call in calls)
        assert any("✅ Graph successfully constructed" in call for call in calls)

    @patch("builtins.print")
    def test_analyze_build_graph_no_graph(self, mock_print: MagicMock) -> None:
        """Test analyze_build_graph without graph data."""
        results = {
            "no_graph_step": {
                "other_data": "value",
                # No graph field
            }
        }

        self.analyzer.analyze_build_graph(results, step_name="no_graph_step")

        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("🔗 Graph Construction: no_graph_step" in call for call in calls)
        assert any("❌ No graph data found" in call for call in calls)

    def test_analyze_build_graph_missing_step_name(self) -> None:
        """Test analyze_build_graph without step_name."""
        results = {"step": {"graph": {}}}

        with pytest.raises(ValueError, match="No step name provided"):
            self.analyzer.analyze_build_graph(results)

    def test_analyze_build_graph_step_not_found(self) -> None:
        """Test analyze_build_graph with non-existent step."""
        results = {"other_step": {"graph": {}}}

        with pytest.raises(ValueError, match="No data found for step: missing_step"):
            self.analyzer.analyze_build_graph(results, step_name="missing_step")

    def test_analyze_build_graph_empty_step_data(self) -> None:
        """Test analyze_build_graph with empty step data."""
        results = {"empty_step": {}}

        with pytest.raises(ValueError, match="No data found for step: empty_step"):
            self.analyzer.analyze_build_graph(results, step_name="empty_step")


# Add additional tests to improve coverage


class TestNotebookAnalyzer:
    """Test the abstract base class methods."""

    def test_analyze_and_display(self) -> None:
        """Test the analyze_and_display default implementation."""

        # Create a concrete implementation for testing
        class TestAnalyzer(NotebookAnalyzer):
            def analyze(self, results, **kwargs):
                return {"test": "result"}

            def get_description(self):
                return "Test analyzer"

            def display_analysis(self, analysis, **kwargs):
                # This will be mocked
                pass

        analyzer = TestAnalyzer()

        with (
            patch.object(analyzer, "analyze") as mock_analyze,
            patch.object(analyzer, "display_analysis") as mock_display,
        ):
            mock_analyze.return_value = {"test": "result"}

            results = {"steps": {"step1": {"data": "value"}}}
            analyzer.analyze_and_display(results, step_name="test_step")

            mock_analyze.assert_called_once_with(results, step_name="test_step")
            mock_display.assert_called_once_with(
                {"test": "result"}, step_name="test_step"
            )
