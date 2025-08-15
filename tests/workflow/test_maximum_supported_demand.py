from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ngraph.results.store import Results
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand


def _mock_scenario_with_matrix() -> MagicMock:
    mock_scenario = MagicMock()
    td = MagicMock()
    td.source_path = "A"
    td.sink_path = "B"
    td.demand = 10.0
    td.mode = "pairwise"
    td.priority = 0
    td.flow_policy_config = None
    mock_scenario.traffic_matrix_set.get_matrix.return_value = [td]
    return mock_scenario


@patch(
    "ngraph.workflow.maximum_supported_demand_step.MaximumSupportedDemand._evaluate_alpha"
)
def test_msd_basic_bracket_and_bisect(mock_eval: MagicMock) -> None:
    # Feasible if alpha <= 1.3, infeasible otherwise
    def _eval(*, alpha, scenario, matrix_name, placement_rounds, seeds):  # type: ignore[no-redef]
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
    assert base and base[0]["source_path"] == "A"


@patch(
    "ngraph.workflow.maximum_supported_demand_step.MaximumSupportedDemand._evaluate_alpha"
)
def test_msd_no_feasible_raises(mock_eval: MagicMock) -> None:
    # Always infeasible
    def _eval(*, alpha, scenario, matrix_name, placement_rounds, seeds):  # type: ignore[no-redef]
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
    # Build a tiny deterministic scenario: A --(cap=10)--> B, demand base=5
    from ngraph.demand.manager.manager import TrafficManager
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

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

    # Verify feasibility at alpha*
    tmset = MSD._build_scaled_matrix(base_demands, float(alpha_star))
    tm = TrafficManager(
        network=scenario.network, traffic_matrix_set=tmset, matrix_name="temp"
    )
    tm.build_graph(add_reverse=True)
    tm.expand_demands()
    tm.place_all_demands(placement_rounds="auto")
    res = tm.get_traffic_results(detailed=False)
    for r in res:
        total = float(r.total_volume)
        placed = float(r.placed_volume)
        assert pytest.approx(placed, rel=1e-9, abs=1e-9) == total

    # Verify infeasibility just above alpha*
    alpha_above = float(alpha_star) + 0.05
    tmset2 = MSD._build_scaled_matrix(base_demands, alpha_above)
    tm2 = TrafficManager(
        network=scenario.network, traffic_matrix_set=tmset2, matrix_name="temp"
    )
    tm2.build_graph(add_reverse=True)
    tm2.expand_demands()
    tm2.place_all_demands(placement_rounds="auto")
    res2 = tm2.get_traffic_results(detailed=False)
    ratios = []
    for r in res2:
        total = float(r.total_volume)
        placed = float(r.placed_volume)
        ratios.append(1.0 if total == 0 else placed / total)
    assert any(x < 1.0 - 1e-9 for x in ratios)


def test_msd_auto_vs_one_equivalence_single_link() -> None:
    # Same single-link scenario; compare auto vs 1 rounds
    from ngraph.workflow.maximum_supported_demand_step import (
        MaximumSupportedDemand as MSD,
    )
    from tests.integration.helpers import ScenarioDataBuilder

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
    assert abs(alpha_auto - alpha_one) <= 0.02
