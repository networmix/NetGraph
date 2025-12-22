from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.results.store import Results
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


def _mock_scenario_with_matrix() -> MagicMock:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source = "A"
    td.sink = "B"
    td.demand = 10.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]
    return mock_scenario


@patch.object(MaximumSupportedDemand, "_evaluate_alpha")
@patch.object(MaximumSupportedDemand, "_build_cache")
def test_msd_basic_bracket_and_bisect(
    mock_build_cache: MagicMock, mock_eval: MagicMock
) -> None:
    """Test binary search logic with mocked evaluation."""
    mock_build_cache.return_value = MagicMock()

    # Feasible if alpha <= 1.3, infeasible otherwise
    def _eval(cache, alpha, seeds):
        feasible = alpha <= 1.3
        return feasible, {
            "seeds": 1,
            "feasible_seeds": 1 if feasible else 0,
            "min_placement_ratio": 1.0 if feasible else 0.9,
        }

    mock_eval.side_effect = _eval

    scenario = _mock_scenario_with_matrix()
    step = MaximumSupportedDemand(
        name="msd_step",
        matrix_name="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        max_bisect_iters=32,
        max_bracket_iters=16,
        seeds_per_alpha=1,
    )
    scenario.results = Results()
    step.execute(scenario)

    exported = scenario.results.to_dict()
    alpha_star = exported["steps"]["msd_step"]["data"]["alpha_star"]
    assert abs(alpha_star - 1.3) <= 0.02
    ctx = exported["steps"]["msd_step"]["data"].get("context", {})
    assert ctx.get("acceptance_rule") == "hard"
    base = exported["steps"]["msd_step"]["data"].get("base_demands", [])
    assert base and base[0]["source"] == "A"


@patch.object(MaximumSupportedDemand, "_evaluate_alpha")
@patch.object(MaximumSupportedDemand, "_build_cache")
def test_msd_no_feasible_raises(
    mock_build_cache: MagicMock, mock_eval: MagicMock
) -> None:
    """Test that MSD raises when no feasible alpha is found."""
    mock_build_cache.return_value = MagicMock()

    # Always infeasible
    def _eval(cache, alpha, seeds):
        return False, {"seeds": 1, "feasible_seeds": 0, "min_placement_ratio": 0.0}

    mock_eval.side_effect = _eval

    scenario = _mock_scenario_with_matrix()
    step = MaximumSupportedDemand(
        name="msd_step",
        matrix_name="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        alpha_min=0.25,
        max_bracket_iters=8,
    )
    scenario.results = Results()
    with pytest.raises(ValueError):
        step.execute(scenario)


def test_msd_end_to_end_single_link() -> None:
    """Test MSD end-to-end with a simple single-link scenario."""
    from ngraph.analysis.functions import demand_placement_analysis
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

    # Build a tiny deterministic scenario: A --(cap=10)--> B, demand base=5
    scenario = (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B"])
        .with_simple_links([("A", "B", 10.0)])
        .with_traffic_demand("A", "B", 5.0, matrix_name="default")
        .build_scenario()
    )

    step = MaximumSupportedDemand(
        name="msd_e2e",
        matrix_name="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        seeds_per_alpha=1,
    )
    scenario.results = Results()
    step.execute(scenario)

    # Expected alpha* ~ 2.0 (capacity 10 / base 5)
    exported = scenario.results.to_dict()
    data = exported["steps"]["msd_e2e"]["data"]
    alpha_star = data.get("alpha_star")
    assert alpha_star is not None
    assert abs(float(alpha_star) - 2.0) <= 0.02

    base_demands = data.get("base_demands")
    assert isinstance(base_demands, list) and base_demands

    # Verify feasibility at alpha* using demand_placement_analysis
    scaled_demands = MSD._build_scaled_demands(base_demands, float(alpha_star))
    demands_config = [
        {
            "id": d.id,
            "source": d.source,
            "sink": d.sink,
            "demand": d.demand,
            "mode": d.mode,
            "priority": d.priority,
            "flow_policy_config": d.flow_policy_config,
        }
        for d in scaled_demands
    ]

    result = demand_placement_analysis(
        network=scenario.network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=demands_config,
        placement_rounds=1,
    )

    # At alpha*, all demands should be fully placed
    assert result.summary.overall_ratio >= 1.0 - 1e-9

    # Verify infeasibility just above alpha*
    alpha_above = float(alpha_star) + 0.05
    scaled_demands_above = MSD._build_scaled_demands(base_demands, alpha_above)
    demands_config_above = [
        {
            "id": d.id,
            "source": d.source,
            "sink": d.sink,
            "demand": d.demand,
            "mode": d.mode,
            "priority": d.priority,
            "flow_policy_config": d.flow_policy_config,
        }
        for d in scaled_demands_above
    ]

    result_above = demand_placement_analysis(
        network=scenario.network,
        excluded_nodes=set(),
        excluded_links=set(),
        demands_config=demands_config_above,
        placement_rounds=1,
    )

    # Above alpha*, placement should fail (ratio < 1.0)
    assert result_above.summary.overall_ratio < 1.0 - 1e-9


def test_msd_auto_vs_one_equivalence_single_link() -> None:
    """Test that MSD with auto vs 1 placement rounds produces equivalent results."""
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

    # Same single-link scenario; compare auto vs 1 rounds
    scenario = (
        ScenarioDataBuilder()
        .with_simple_nodes(["A", "B"])
        .with_simple_links([("A", "B", 10.0)])
        .with_traffic_demand("A", "B", 5.0, matrix_name="default")
        .build_scenario()
    )

    step_auto = MSD(
        name="msd_auto",
        matrix_name="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        seeds_per_alpha=1,
        placement_rounds="auto",
    )
    step_one = MSD(
        name="msd_one",
        matrix_name="default",
        alpha_start=1.0,
        growth_factor=2.0,
        resolution=0.01,
        seeds_per_alpha=1,
        placement_rounds=1,
    )

    scenario.results = Results()
    step_auto.execute(scenario)
    step_one.execute(scenario)

    exported = scenario.results.to_dict()
    alpha_auto = float(exported["steps"]["msd_auto"]["data"]["alpha_star"])
    alpha_one = float(exported["steps"]["msd_one"]["data"]["alpha_star"])
    # Both should find approximately the same alpha* for this simple case
    assert abs(alpha_auto - alpha_one) <= 0.02
