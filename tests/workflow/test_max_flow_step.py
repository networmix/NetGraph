from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.model.failure.policy import FailurePolicy, FailureRule
from ngraph.model.failure.policy_set import FailurePolicySet
from ngraph.model.network import Link, Network, Node
from ngraph.results import Results
from ngraph.results.flow import FlowEntry, FlowIterationResult, FlowSummary
from ngraph.scenario import Scenario
from ngraph.types.base import FlowPlacement
from ngraph.workflow.max_flow_step import MaxFlow


@pytest.fixture
def simple_network() -> Network:
    """A -> B (cap 10) -> C (cap 5)."""
    network = Network()
    network.add_node(Node("A"))
    network.add_node(Node("B"))
    network.add_node(Node("C"))
    network.add_link(Link("A", "B", capacity=10.0))
    network.add_link(Link("B", "C", capacity=5.0))
    return network


@pytest.fixture
def simple_failure_policy() -> FailurePolicy:
    """Create a simple failure policy that fails one link."""
    rule = FailureRule(
        scope="link",
        mode="choice",
        count=1,
    )
    return FailurePolicy(
        modes=[
            __import__(
                "ngraph.model.failure.policy", fromlist=["FailureMode"]
            ).FailureMode(weight=1.0, rules=[rule])
        ]
    )


@pytest.fixture
def mock_scenario(simple_network, simple_failure_policy) -> Scenario:
    """MagicMock Scenario with simple_network and failure policy 'test_policy'."""
    scenario = MagicMock(spec=Scenario)
    scenario.network = simple_network
    scenario.results = Results()

    policy_set = FailurePolicySet()
    policy_set.add("test_policy", simple_failure_policy)
    scenario.failure_policy_set = policy_set

    return scenario


class TestMaxFlowStep:
    """Test suite for MaxFlow workflow step."""

    def test_initialization_defaults(self):
        """Test MaxFlow initialization with defaults."""
        step = MaxFlow(source="^A", target="^C")

        assert step.source == "^A"
        assert step.target == "^C"
        assert step.mode == "combine"
        assert step.failure_policy is None
        assert step.iterations == 1
        assert step.parallelism == "auto"
        assert step.shortest_path is False
        assert step.flow_placement == FlowPlacement.PROPORTIONAL
        assert step.seed is None
        assert step.store_failure_patterns is False
        assert step.include_flow_details is False

    def test_initialization_custom_values(self):
        """Test MaxFlow initialization with custom values."""
        step = MaxFlow(
            source="^src",
            target="^dst",
            mode="pairwise",
            failure_policy="test_policy",
            iterations=100,
            parallelism=4,
            shortest_path=True,
            flow_placement=FlowPlacement.EQUAL_BALANCED,
            seed=42,
            store_failure_patterns=True,
            include_flow_details=True,
        )

        assert step.source == "^src"
        assert step.target == "^dst"
        assert step.mode == "pairwise"
        assert step.failure_policy == "test_policy"
        assert step.iterations == 100
        assert step.parallelism == 4
        assert step.shortest_path is True
        assert step.flow_placement == FlowPlacement.EQUAL_BALANCED
        assert step.seed == 42
        assert step.store_failure_patterns is True
        assert step.include_flow_details is True

    def test_validation_errors(self):
        """Invalid iterations, parallelism and mode raise ValueError."""
        with pytest.raises(ValueError, match="iterations must be >= 0"):
            MaxFlow(source="^A", target="^C", iterations=-1)

        with pytest.raises(ValueError, match="parallelism must be >= 1"):
            MaxFlow(source="^A", target="^C", parallelism=0)

        for bad in (2.5, True, "4"):
            with pytest.raises(ValueError, match="integer or 'auto'"):
                MaxFlow(source="^A", target="^C", parallelism=bad)

        with pytest.raises(ValueError, match="Invalid mode"):
            MaxFlow(source="^A", target="^C", mode="invalid")

    def test_flow_placement_enum_usage(self):
        """flow_placement keeps the FlowPlacement enum value passed in."""
        step = MaxFlow(
            source="^A", target="^C", flow_placement=FlowPlacement.PROPORTIONAL
        )
        assert step.flow_placement == FlowPlacement.PROPORTIONAL

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_run_with_mock_failure_manager(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test running the workflow step with mocked FailureManager."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Baseline is separate; results holds only failure iterations
        entry = FlowEntry(
            source="A",
            destination="C",
            priority=0,
            demand=5.0,
            placed=5.0,
            dropped=0.0,
        )
        mock_raw = {
            "baseline": FlowIterationResult(
                flows=[entry],
                summary=FlowSummary(
                    total_demand=5.0,
                    total_placed=5.0,
                    overall_ratio=1.0,
                    dropped_flows=0,
                    num_flows=1,
                ),
            ),
            "results": [],  # No failure iterations for this test
            "metadata": {"iterations": 1, "parallelism": 1},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        step = MaxFlow(
            source="^A",
            target="^C",
            failure_policy="test_policy",
            iterations=1,
            parallelism=1,
        )
        step.name = "envelope"
        step.execute(mock_scenario)

        mock_failure_manager_class.assert_called_once_with(
            network=mock_scenario.network,
            failure_policy_set=mock_scenario.failure_policy_set,
            policy_name="test_policy",
        )

        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["source"] == "^A"
        assert kwargs["target"] == "^C"
        assert kwargs["mode"] == "combine"
        assert kwargs["iterations"] == 1
        assert kwargs["parallelism"] == 1
        assert kwargs["shortest_path"] is False
        assert kwargs["flow_placement"] == step.flow_placement
        assert kwargs["seed"] is None
        assert kwargs["store_failure_patterns"] is False
        assert kwargs["include_flow_details"] is False

        exported = mock_scenario.results.to_dict()
        data = exported["steps"]["envelope"]["data"]
        assert isinstance(data, dict)
        assert "flow_results" in data and isinstance(data["flow_results"], list)
        # No failure results, but baseline should be present
        assert "baseline" in data

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_run_with_failure_patterns(self, mock_failure_manager_class, mock_scenario):
        """Test running with failure pattern storage enabled."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        mock_raw = {
            "baseline": FlowIterationResult(),
            "results": [
                FlowIterationResult(
                    failure_id="deadbeef",
                    failure_state={"excluded_nodes": ["node1"], "excluded_links": []},
                    failure_trace={"mode_index": 0},
                    occurrence_count=2,
                )
            ],
            "metadata": {"iterations": 2, "parallelism": 1, "unique_patterns": 1},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        step = MaxFlow(
            source="^A",
            target="^C",
            iterations=2,
            store_failure_patterns=True,
            parallelism=1,
        )
        step.execute(mock_scenario)

        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["store_failure_patterns"] is True
        assert kwargs["include_flow_details"] is False

    def test_capacity_envelope_with_failures_mocked(self):
        """MaxFlow in a real Scenario stores metadata and data."""
        step = MaxFlow(
            source="^A",
            target="^C",
            mode="combine",
            iterations=2,
            parallelism=1,
            store_failure_patterns=True,
        )

        scenario = Scenario(
            network=MagicMock(),
            workflow=[],  # Empty workflow for testing
            failure_policy_set=MagicMock(),
            results=Results(),
        )

        # Baseline is separate; results holds only failure iterations
        mock_raw = {
            "baseline": FlowIterationResult(
                failure_state={"excluded_nodes": [], "excluded_links": []}
            ),
            "results": [
                FlowIterationResult(
                    failure_id="abc123",
                    failure_state={"excluded_nodes": [], "excluded_links": ["link1"]},
                    failure_trace={"mode_index": 0},
                )
            ],
            "metadata": {"iterations": 2, "parallelism": 1},
        }

        with patch("ngraph.workflow.max_flow_step.FailureManager") as mock_fm_class:
            mock_fm_instance = mock_fm_class.return_value
            mock_fm_instance.run_max_flow_monte_carlo.return_value = mock_raw

            step.name = "envelope"
            step.execute(scenario)

        exported = scenario.results.to_dict()
        assert exported["steps"]["envelope"]["metadata"] is not None
        assert exported["steps"]["envelope"]["data"] is not None

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_include_flow_details_functionality(
        self, mock_failure_manager_class, mock_scenario
    ):
        """include_flow_details=True is forwarded to run_max_flow_monte_carlo."""
        mock_failure_manager = MagicMock()
        mock_failure_manager_class.return_value = mock_failure_manager

        # Mock results with flow details (cost_distribution and min_cut edges)
        entry = FlowEntry(
            source="A",
            destination="C",
            priority=0,
            demand=5.0,
            placed=5.0,
            dropped=0.0,
            cost_distribution={3.0: 5.0},
            data={"edges": ["A|B|0:fwd"], "edges_kind": "min_cut"},
        )
        summary = FlowSummary(
            total_demand=5.0,
            total_placed=5.0,
            overall_ratio=1.0,
            dropped_flows=0,
            num_flows=1,
        )
        mock_raw = {
            "baseline": FlowIterationResult(flows=[entry], summary=summary),
            "results": [FlowIterationResult(flows=[entry], summary=summary)],
            "metadata": {"iterations": 1, "parallelism": 1, "unique_patterns": 1},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        step = MaxFlow(
            source="^A",
            target="^C",
            iterations=1,
            include_flow_details=True,
            parallelism=1,
        )
        step.execute(mock_scenario)

        _, kwargs = mock_failure_manager.run_max_flow_monte_carlo.call_args
        assert kwargs["include_flow_details"] is True

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_failure_trace_persisted_on_results(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test that failure_trace is persisted on flow_results."""
        mock_failure_manager = mock_failure_manager_class.return_value

        mock_result = MagicMock()
        mock_result.failure_id = "abc123"
        mock_result.failure_state = {"excluded_nodes": [], "excluded_links": ["link1"]}
        mock_result.failure_trace = {
            "mode_index": 0,
            "mode_attrs": {"severity": "single"},
            "selections": [
                {
                    "rule_index": 0,
                    "scope": "link",
                    "mode": "choice",
                    "matched_count": 3,
                    "selected_ids": ["link1"],
                }
            ],
            "expansion": {"nodes": [], "links": []},
        }
        mock_result.occurrence_count = 2
        mock_result.to_dict.return_value = {
            "failure_id": "abc123",
            "failure_state": {"excluded_nodes": [], "excluded_links": ["link1"]},
            "failure_trace": mock_result.failure_trace,
            "occurrence_count": 2,
            "flows": [],
            "summary": {
                "total_demand": 0.0,
                "total_placed": 0.0,
                "overall_ratio": 1.0,
                "dropped_flows": 0,
                "num_flows": 0,
            },
        }

        mock_baseline = MagicMock()
        mock_baseline.to_dict.return_value = {
            "failure_id": "",
            "failure_state": {"excluded_nodes": [], "excluded_links": []},
            "failure_trace": None,
            "occurrence_count": 1,
            "flows": [],
            "summary": {
                "total_demand": 0.0,
                "total_placed": 0.0,
                "overall_ratio": 1.0,
                "dropped_flows": 0,
                "num_flows": 0,
            },
        }

        mock_raw = {
            "baseline": mock_baseline,
            "results": [mock_result],
            "metadata": {"iterations": 2, "parallelism": 1, "unique_patterns": 1},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        step = MaxFlow(
            name="test_step",
            source="^A",
            target="^C",
            iterations=2,
            store_failure_patterns=True,
            parallelism=1,
        )
        step.execute(mock_scenario)

        exported = mock_scenario.results.to_dict()
        data = exported["steps"]["test_step"]["data"]

        assert len(data["flow_results"]) == 1
        result = data["flow_results"][0]
        assert result["failure_id"] == "abc123"
        assert result["failure_trace"]["mode_index"] == 0
        assert result["occurrence_count"] == 2

        # Baseline is stored separately from flow_results
        assert "baseline" in data
        assert data["baseline"]["failure_id"] == ""

    @patch("ngraph.workflow.max_flow_step.FailureManager")
    def test_no_failure_trace_when_disabled(
        self, mock_failure_manager_class, mock_scenario
    ):
        """Test that failure_trace is None when store_failure_patterns=False."""
        mock_failure_manager = mock_failure_manager_class.return_value

        mock_result = MagicMock()
        mock_result.failure_trace = None  # No trace when disabled
        mock_result.occurrence_count = 1
        mock_result.to_dict.return_value = {
            "failure_id": "",
            "failure_state": None,
            "failure_trace": None,
            "occurrence_count": 1,
            "flows": [],
            "summary": {
                "total_demand": 0.0,
                "total_placed": 0.0,
                "overall_ratio": 1.0,
                "dropped_flows": 0,
                "num_flows": 0,
            },
        }

        mock_raw = {
            "baseline": FlowIterationResult(),
            "results": [mock_result],
            "metadata": {"iterations": 1, "parallelism": 1, "unique_patterns": 1},
        }
        mock_failure_manager.run_max_flow_monte_carlo.return_value = mock_raw

        step = MaxFlow(
            name="test_step_disabled",
            source="^A",
            target="^C",
            iterations=1,
            store_failure_patterns=False,
            parallelism=1,
        )
        step.execute(mock_scenario)

        exported = mock_scenario.results.to_dict()
        data = exported["steps"]["test_step_disabled"]["data"]
        assert len(data["flow_results"]) == 1
        assert data["flow_results"][0]["failure_trace"] is None
