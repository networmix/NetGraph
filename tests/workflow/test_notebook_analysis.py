"""Tests for notebook analysis components."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
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
            "step1": {"data": "value1"},
            "step2": {"data": "value2"},
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name

        try:
            result = DataLoader.load_results(temp_path)

            assert result["success"] is True
            assert result["results"] == test_data
            assert result["step_count"] == 2
            assert result["step_names"] == ["step1", "step2"]
            assert "Loaded 2 analysis steps" in result["message"]
        finally:
            Path(temp_path).unlink()

    def test_load_results_with_pathlib_path(self) -> None:
        """Test loading with pathlib.Path object."""
        test_data = {"step1": {"data": "value"}}

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
        """Test analyze with mixed result types."""
        results = {
            "capacity_step": {"capacity_envelopes": {"A->B": 100}},
            "flow_step": {"max_flow:[A->B]": 50},
            "other_step": {"other_data": "value"},
            "combined_step": {
                "capacity_envelopes": {"C->D": 200},
                "max_flow:[C->D]": 150,
            },
        }

        analysis = self.analyzer.analyze(results)

        assert analysis["status"] == "success"
        assert analysis["total_steps"] == 4
        assert analysis["capacity_steps"] == 2  # capacity_step and combined_step
        assert analysis["flow_steps"] == 2  # flow_step and combined_step
        assert analysis["other_steps"] == 0  # 4 - 2 - 2 = 0

    def test_analyze_non_dict_step(self) -> None:
        """Test analyze with non-dict step data."""
        results = {
            "valid_step": {"capacity_envelopes": {"A->B": 100}},
            "invalid_step": "not_a_dict",
            "another_invalid": ["also", "not", "dict"],
        }

        analysis = self.analyzer.analyze(results)

        assert analysis["status"] == "success"
        assert analysis["total_steps"] == 3
        assert analysis["capacity_steps"] == 1  # Only valid_step
        assert analysis["flow_steps"] == 0
        assert analysis["other_steps"] == 2  # 3 - 1 - 0 = 2

    @patch("builtins.print")
    def test_display_analysis(self, mock_print: MagicMock) -> None:
        """Test display_analysis method."""
        analysis = {
            "total_steps": 5,
            "capacity_steps": 2,
            "flow_steps": 2,
            "other_steps": 1,
        }

        self.analyzer.display_analysis(analysis)

        # Check that summary information is printed
        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("NetGraph Analysis Summary" in call for call in calls)
        assert any("Total Analysis Steps: 5" in call for call in calls)
        assert any("Capacity Envelope Steps: 2" in call for call in calls)
        assert any("Flow Analysis Steps: 2" in call for call in calls)
        assert any("Other Data Steps: 1" in call for call in calls)

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
        results = {"step1": {"data": "value"}}
        self.analyzer.analyze_and_display(results)

        # Should call both analyze and display_analysis
        calls = [call.args[0] for call in mock_print.call_args_list]
        assert any("NetGraph Analysis Summary" in call for call in calls)

    @patch("builtins.print")
    def test_analyze_network_stats_success(self, mock_print: MagicMock) -> None:
        """Test analyze_network_stats with complete data."""
        results = {
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
            "partial_step": {
                "node_count": 25,
                "mean_capacity": 15.0,
                "max_degree": 6.0,
                # Missing many optional fields
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
        results = {"step": {"data": "value"}}

        with pytest.raises(ValueError, match="No step name provided"):
            self.analyzer.analyze_network_stats(results)

    def test_analyze_network_stats_step_not_found(self) -> None:
        """Test analyze_network_stats with non-existent step."""
        results = {"other_step": {"data": "value"}}

        with pytest.raises(ValueError, match="No data found for step: missing_step"):
            self.analyzer.analyze_network_stats(results, step_name="missing_step")

    def test_analyze_network_stats_empty_step_data(self) -> None:
        """Test analyze_network_stats with empty step data."""
        results = {"empty_step": {}}

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

            results = {"step1": {"data": "value"}}
            analyzer.analyze_and_display(results, step_name="test_step")

            mock_analyze.assert_called_once_with(results, step_name="test_step")
            mock_display.assert_called_once_with(
                {"test": "result"}, step_name="test_step"
            )


# Add tests for additional edge cases
class TestCapacityMatrixAnalyzerEdgeCases:
    """Test edge cases for CapacityMatrixAnalyzer."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.analyzer = CapacityMatrixAnalyzer()

    def test_parse_flow_path_bidirectional(self) -> None:
        """Test _parse_flow_path with bidirectional flow."""
        result = self.analyzer._parse_flow_path("datacenter<->edge")

        assert result is not None
        assert result["source"] == "datacenter"
        assert result["destination"] == "edge"
        assert result["direction"] == "bidirectional"

    def test_parse_flow_path_directed(self) -> None:
        """Test _parse_flow_path with directed flow."""
        result = self.analyzer._parse_flow_path("datacenter->edge")

        assert result is not None
        assert result["source"] == "datacenter"
        assert result["destination"] == "edge"
        assert result["direction"] == "directed"

    def test_parse_flow_path_with_whitespace(self) -> None:
        """Test _parse_flow_path handles whitespace correctly."""
        result = self.analyzer._parse_flow_path(" datacenter -> edge ")

        assert result is not None
        assert result["source"] == "datacenter"
        assert result["destination"] == "edge"
        assert result["direction"] == "directed"

    def test_parse_flow_path_invalid_format(self) -> None:
        """Test _parse_flow_path with invalid format."""
        result = self.analyzer._parse_flow_path("invalid_format")
        assert result is None

    def test_parse_flow_path_empty_string(self) -> None:
        """Test _parse_flow_path with empty string."""
        result = self.analyzer._parse_flow_path("")
        assert result is None

    def test_extract_capacity_value_numeric(self) -> None:
        """Test _extract_capacity_value with numeric values."""
        assert self.analyzer._extract_capacity_value(100) == 100.0
        assert self.analyzer._extract_capacity_value(50.5) == 50.5
        assert self.analyzer._extract_capacity_value(0) == 0.0

    def test_extract_capacity_value_dict_format(self) -> None:
        """Test _extract_capacity_value with dict format."""
        envelope_data = {"max": 100, "min": 0, "avg": 50}
        assert self.analyzer._extract_capacity_value(envelope_data) == 100.0

    def test_extract_capacity_value_dict_non_numeric_max(self) -> None:
        """Test _extract_capacity_value with non-numeric max in dict."""
        envelope_data = {"max": "invalid", "min": 0, "avg": 50}
        assert self.analyzer._extract_capacity_value(envelope_data) is None

    def test_extract_capacity_value_dict_missing_max(self) -> None:
        """Test _extract_capacity_value with missing max key."""
        envelope_data = {"min": 0, "avg": 50}
        assert self.analyzer._extract_capacity_value(envelope_data) is None

    def test_extract_capacity_value_invalid_types(self) -> None:
        """Test _extract_capacity_value with invalid types."""
        assert self.analyzer._extract_capacity_value("string") is None
        assert self.analyzer._extract_capacity_value([1, 2, 3]) is None
        assert self.analyzer._extract_capacity_value(None) is None

    def test_extract_matrix_data_mixed_formats(self) -> None:
        """Test _extract_matrix_data with mixed envelope formats."""
        envelopes = {
            "datacenter->edge": 100,  # Numeric
            "edge->datacenter": {"max": 80, "min": 20},  # Dict format
            "invalid_flow_format": 50,  # Invalid flow path
            "datacenter<->core": {"max": "invalid"},  # Invalid capacity
        }

        matrix_data = self.analyzer._extract_matrix_data(envelopes)

        # Should only extract valid entries
        assert len(matrix_data) == 2

        # Check first entry
        entry1 = next(d for d in matrix_data if d["flow_path"] == "datacenter->edge")
        assert entry1["source"] == "datacenter"
        assert entry1["destination"] == "edge"
        assert entry1["capacity"] == 100.0
        assert entry1["direction"] == "directed"

        # Check second entry
        entry2 = next(d for d in matrix_data if d["flow_path"] == "edge->datacenter")
        assert entry2["source"] == "edge"
        assert entry2["destination"] == "datacenter"
        assert entry2["capacity"] == 80.0
        assert entry2["direction"] == "directed"

    def test_extract_matrix_data_empty_envelopes(self) -> None:
        """Test _extract_matrix_data with empty envelopes."""
        matrix_data = self.analyzer._extract_matrix_data({})
        assert matrix_data == []

    def test_create_capacity_matrix(self) -> None:
        """Test _create_capacity_matrix helper method."""
        # Create test dataframe
        matrix_data = [
            {"source": "A", "destination": "B", "capacity": 100},
            {"source": "B", "destination": "A", "capacity": 80},
            {"source": "A", "destination": "C", "capacity": 120},
        ]
        df = pd.DataFrame(matrix_data)

        matrix = self.analyzer._create_capacity_matrix(df)

        assert isinstance(matrix, pd.DataFrame)
        assert matrix.loc["A", "B"] == 100
        assert matrix.loc["B", "A"] == 80
        assert matrix.loc["A", "C"] == 120
        # Fill value should be 0 for missing combinations
        assert matrix.loc["B", "C"] == 0

    def test_calculate_statistics_empty_matrix(self) -> None:
        """Test _calculate_statistics with empty matrix."""
        empty_matrix = pd.DataFrame()
        stats = self.analyzer._calculate_statistics(empty_matrix)

        assert not stats["has_data"]

    def test_calculate_statistics_all_zero_matrix(self) -> None:
        """Test _calculate_statistics with all-zero matrix."""
        matrix = pd.DataFrame({"A": [0, 0], "B": [0, 0]}, index=["A", "B"])

        stats = self.analyzer._calculate_statistics(matrix)
        assert not stats["has_data"]

    def test_calculate_statistics_valid_matrix(self) -> None:
        """Test _calculate_statistics with valid matrix."""
        matrix = pd.DataFrame({"A": [0, 80], "B": [100, 0]}, index=["A", "B"])

        stats = self.analyzer._calculate_statistics(matrix)

        assert stats["has_data"]
        assert "flow_density" in stats
        assert "capacity_max" in stats  # Correct key name
        assert "capacity_mean" in stats  # Correct key name
        assert "capacity_min" in stats  # Correct key name

    @pytest.mark.parametrize("step_name", [None, ""])
    def test_analyze_missing_step_name(self, step_name) -> None:
        """Test analyze method with missing or empty step name."""
        results = {"some_step": {"capacity_envelopes": {}}}

        with pytest.raises(ValueError, match="step_name required"):
            self.analyzer.analyze(results, step_name=step_name)

    def test_analyze_step_not_found(self) -> None:
        """Test analyze method with non-existent step."""
        results = {"other_step": {"capacity_envelopes": {}}}

        with pytest.raises(
            ValueError, match="No capacity envelope data found for step: missing_step"
        ):
            self.analyzer.analyze(results, step_name="missing_step")

    def test_analyze_no_capacity_envelopes(self) -> None:
        """Test analyze method with step data but no capacity envelopes."""
        results = {"step": {"other_data": "value"}}

        with pytest.raises(
            ValueError, match="No capacity envelope data found for step: step"
        ):
            self.analyzer.analyze(results, step_name="step")

    def test_analyze_empty_capacity_envelopes(self) -> None:
        """Test analyze method with empty capacity envelopes."""
        results = {"step": {"capacity_envelopes": {}}}

        with pytest.raises(
            ValueError, match="No capacity envelope data found for step: step"
        ):
            self.analyzer.analyze(results, step_name="step")

    def test_analyze_invalid_envelope_data(self) -> None:
        """Test analyze method with invalid envelope data."""
        results = {
            "step": {
                "capacity_envelopes": {
                    "invalid_flow": "string_value",
                    "another_invalid": None,
                }
            }
        }

        with pytest.raises(
            RuntimeError, match="Error analyzing capacity matrix for step"
        ):
            self.analyzer.analyze(results, step_name="step")
