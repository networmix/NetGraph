"""A Python step object uses its constructor field as its declaration location."""

import pytest

from ngraph.workflow.base import step_type

CASES = [
    (
        "BuildGraph_name",
        "BuildGraph",
        {},
        {"name": 3},
        "ValueError",
        "workflow step name: expected text, got 3",
    ),
    (
        "BuildGraph_seed",
        "BuildGraph",
        {},
        {"seed": True},
        "ValueError",
        "workflow step seed: expected an integer, got True",
    ),
    (
        "BuildGraph_yaml_label",
        "BuildGraph",
        {},
        {"yaml_label": 3},
        "ValueError",
        "workflow step yaml_label: expected text, got 3",
    ),
    (
        "BuildGraph_derived_seed",
        "BuildGraph",
        {},
        {"derived_seed": True},
        "ValueError",
        "workflow step derived_seed: expected an integer, got True",
    ),
    (
        "BuildGraph_add_reverse",
        "BuildGraph",
        {},
        {"add_reverse": "false"},
        "ValueError",
        "BuildGraph.add_reverse: expected bool, got 'false'",
    ),
    (
        "CostPower_include_disabled",
        "CostPower",
        {},
        {"include_disabled": "false"},
        "ValueError",
        "CostPower.include_disabled: expected bool, got 'false'",
    ),
    (
        "CostPower_aggregation_level",
        "CostPower",
        {},
        {"aggregation_level": -1},
        "ValueError",
        "CostPower.aggregation_level: integer outside [0, inf), got -1",
    ),
    (
        "NetworkStats_include_disabled",
        "NetworkStats",
        {},
        {"include_disabled": "false"},
        "ValueError",
        "NetworkStats.include_disabled: expected bool, got 'false'",
    ),
    (
        "NetworkStats_excluded_nodes",
        "NetworkStats",
        {},
        {"excluded_nodes": "A"},
        "ValueError",
        "NetworkStats.excluded_nodes: expected a sequence of names, got 'A'",
    ),
    (
        "NetworkStats_excluded_links",
        "NetworkStats",
        {},
        {"excluded_links": [3]},
        "ValueError",
        "NetworkStats.excluded_links: expected text, got 3",
    ),
    (
        "MaxFlow_source",
        "MaxFlow",
        {},
        {"source": 3},
        "TypeError",
        "MaxFlow endpoints: expected Selectors, got (3, Selector(path='.*', group_by=None, match=None, active...",
    ),
    (
        "MaxFlow_target",
        "MaxFlow",
        {},
        {"target": 3},
        "TypeError",
        "MaxFlow endpoints: expected Selectors, got (Selector(path='.*', group_by=None, match=None, active_on...",
    ),
    (
        "MaxFlow_mode",
        "MaxFlow",
        {},
        {"mode": "missing"},
        "ValueError",
        "MaxFlow.mode: expected combine or pairwise, got 'missing'",
    ),
    (
        "MaxFlow_preset",
        "MaxFlow",
        {},
        {"preset": "missing"},
        "TypeError",
        "MaxFlow.preset: expected FlowPolicyPreset, got 'missing'",
    ),
    (
        "MaxFlow_model",
        "MaxFlow",
        {},
        {"model": "missing"},
        "TypeError",
        "MaxFlow.model: expected a declared model or native FlowPolicyConfig, got 'missing'",
    ),
    (
        "MaxFlow_offer",
        "MaxFlow",
        {},
        {"offer": -1},
        "ValueError",
        "MaxFlow.offer: expected a finite nonnegative amount, got -1",
    ),
    (
        "MaxFlow_design_demand",
        "MaxFlow",
        {},
        {"design_demand": -1},
        "ValueError",
        "MaxFlow.design_demand: expected a finite nonnegative amount, got -1",
    ),
    (
        "MaxFlow_iterations",
        "MaxFlow",
        {},
        {"iterations": -1},
        "ValueError",
        "MaxFlow.iterations: integer outside [0, inf), got -1",
    ),
    (
        "MaxFlow_workers",
        "MaxFlow",
        {},
        {"workers": 0},
        "ValueError",
        "workers: integer outside [1, inf), got 0",
    ),
    (
        "MaxFlow_failure_trace",
        "MaxFlow",
        {},
        {"failure_trace": "false"},
        "ValueError",
        "MaxFlow.failure_trace: expected bool, got 'false'",
    ),
    (
        "MaxFlow_outputs",
        "MaxFlow",
        {},
        {"outputs": {}},
        "TypeError",
        "MaxFlow.outputs: expected native OutputOptions, got {}",
    ),
    (
        "MaxFlow_export_details",
        "MaxFlow",
        {},
        {"export_details": "false"},
        "ValueError",
        "MaxFlow.export_details: expected bool, got 'false'",
    ),
    (
        "MaxFlow_export_cost_distribution",
        "MaxFlow",
        {},
        {"export_cost_distribution": "false"},
        "ValueError",
        "MaxFlow.export_cost_distribution: expected bool, got 'false'",
    ),
    (
        "MaxFlow_failure_policy",
        "MaxFlow",
        {},
        {"failure_policy": ""},
        "ValueError",
        "MaxFlow.failure_policy: expected a nonempty name, got ''",
    ),
    (
        "MaximumSupportedDemand_demand_set",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": ""},
        "ValueError",
        "MaximumSupportedDemand.demand_set: expected a nonempty name, got ''",
    ),
    (
        "MaximumSupportedDemand_alpha_start",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_start": 0},
        "ValueError",
        "MaximumSupportedDemand.alpha_start: expected a finite positive amount, got 0",
    ),
    (
        "MaximumSupportedDemand_growth_factor",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "growth_factor": 1},
        "ValueError",
        "MaximumSupportedDemand.growth_factor: must exceed 1, got 1",
    ),
    (
        "MaximumSupportedDemand_alpha_min",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_min": 0},
        "ValueError",
        "MaximumSupportedDemand.alpha_min: expected a finite positive amount, got 0",
    ),
    (
        "MaximumSupportedDemand_alpha_max",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_max": 0},
        "ValueError",
        "MaximumSupportedDemand.alpha_max: expected a finite positive amount, got 0",
    ),
    (
        "MaximumSupportedDemand_alpha_tolerance",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_tolerance": 0},
        "ValueError",
        "MaximumSupportedDemand.alpha_tolerance: expected a finite positive amount, got 0",
    ),
    (
        "MaximumSupportedDemand_max_bracket_iters",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "max_bracket_iters": 0},
        "ValueError",
        "MaximumSupportedDemand.max_bracket_iters: integer outside [1, inf), got 0",
    ),
    (
        "MaximumSupportedDemand_max_bisect_iters",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "max_bisect_iters": 0},
        "ValueError",
        "MaximumSupportedDemand.max_bisect_iters: integer outside [1, inf), got 0",
    ),
    (
        "MaximumSupportedDemand_export_details",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "export_details": "false"},
        "ValueError",
        "MaximumSupportedDemand.export_details: expected bool, got 'false'",
    ),
    (
        "TrafficMatrixPlacement_demand_set",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": ""},
        "ValueError",
        "TrafficMatrixPlacement.demand_set: expected a nonempty name, got ''",
    ),
    (
        "TrafficMatrixPlacement_alpha",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha": 0},
        "ValueError",
        "TrafficMatrixPlacement.alpha: expected a finite positive amount, got 0",
    ),
    (
        "TrafficMatrixPlacement_alpha_from_step",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_from_step": ""},
        "ValueError",
        "TrafficMatrixPlacement.alpha_from_step: expected a nonempty name, got ''",
    ),
    (
        "TrafficMatrixPlacement_failure_states",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "failure_states": "converged"},
        "ValueError",
        "workflow.TrafficMatrixPlacement.failure_states: expected a list of failure states, got "
        "'converged'",
    ),
    (
        "TrafficMatrixPlacement_interaction",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "interaction": "missing"},
        "ValueError",
        "workflow.TrafficMatrixPlacement.interaction: expected ordered or simultaneous, got 'missing'",
    ),
    (
        "TrafficMatrixPlacement_failure_policy",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "failure_policy": ""},
        "ValueError",
        "TrafficMatrixPlacement.failure_policy: expected a nonempty name, got ''",
    ),
    (
        "TrafficMatrixPlacement_iterations",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "iterations": -1},
        "ValueError",
        "TrafficMatrixPlacement.iterations: integer outside [0, inf), got -1",
    ),
    (
        "TrafficMatrixPlacement_workers",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "workers": 0},
        "ValueError",
        "workers: integer outside [1, inf), got 0",
    ),
    (
        "TrafficMatrixPlacement_failure_trace",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "failure_trace": "false"},
        "ValueError",
        "TrafficMatrixPlacement.failure_trace: expected bool, got 'false'",
    ),
    (
        "TrafficMatrixPlacement_outputs",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "outputs": {}},
        "TypeError",
        "TrafficMatrixPlacement.outputs: expected native OutputOptions, got {}",
    ),
    (
        "TrafficMatrixPlacement_export_details",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "export_details": "false"},
        "ValueError",
        "TrafficMatrixPlacement.export_details: expected bool, got 'false'",
    ),
    (
        "TrafficMatrixPlacement_export_cost_distribution",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "export_cost_distribution": "false"},
        "ValueError",
        "TrafficMatrixPlacement.export_cost_distribution: expected bool, got 'false'",
    ),
    (
        "TunnelCountAnalysis_demand_set",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {"demand_set": "", "counts": [1], "design_demand": 1, "offer": 1},
        "ValueError",
        "TunnelCountAnalysis.demand_set: expected a nonempty name, got ''",
    ),
    (
        "TunnelCountAnalysis_counts",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {"demand_set": "load", "counts": [], "design_demand": 1, "offer": 1},
        "ValueError",
        "workflow step TunnelCountAnalysis: tunnel_counts.counts: give at least one count or up_to, got "
        "()",
    ),
    (
        "TunnelCountAnalysis_up_to",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "up_to": 0,
        },
        "ValueError",
        "workflow step TunnelCountAnalysis: tunnel_counts.up_to: expected an integer in [1, 10000], got "
        "0",
    ),
    (
        "TunnelCountAnalysis_design_demand",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {"demand_set": "load", "counts": [1], "design_demand": None, "offer": 1},
        "ValueError",
        "TunnelCountAnalysis.design_demand: required",
    ),
    (
        "TunnelCountAnalysis_offer",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": None},
        "ValueError",
        "TunnelCountAnalysis.offer: required",
    ),
    (
        "TunnelCountAnalysis_workers",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "workers": 0,
        },
        "ValueError",
        "workflow step TunnelCountAnalysis: workers: integer outside [1, inf), got 0",
    ),
    (
        "TunnelCountAnalysis_outputs",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "outputs": {},
        },
        "TypeError",
        "workflow step TunnelCountAnalysis: tunnel_counts.outputs: expected native OutputOptions, got "
        "{}",
    ),
    (
        "TunnelCountAnalysis_export_details",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "design_demand": 1, "offer": 1},
        {
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "export_details": "false",
        },
        "ValueError",
        "workflow step TunnelCountAnalysis: export_details: expected bool, got 'false'",
    ),
    (
        "MaxFlow_exclusive",
        "MaxFlow",
        {},
        {"preset": "p", "model": "m"},
        "ValueError",
        "MaxFlow: preset and model are exclusive, got ('p', 'm')",
    ),
    (
        "Placement_exclusive",
        "TrafficMatrixPlacement",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha": 1, "alpha_from_step": "prior"},
        "ValueError",
        "TrafficMatrixPlacement: alpha and alpha_from_step are exclusive, got (1, 'prior')",
    ),
    (
        "MSD_range",
        "MaximumSupportedDemand",
        {"demand_set": "load"},
        {"demand_set": "load", "alpha_start": 1, "alpha_min": 2},
        "ValueError",
        "MaximumSupportedDemand: require alpha_min <= alpha_start <= alpha_max, got (2, 1, "
        "1000000000.0)",
    ),
    (
        "Counts_duplicate",
        "TunnelCountAnalysis",
        {"demand_set": "load", "counts": [1], "offer": 1, "design_demand": 1},
        {"demand_set": "load", "counts": [1, 1], "offer": 1, "design_demand": 1},
        "ValueError",
        "workflow step TunnelCountAnalysis: tunnel_counts.counts: duplicate count 1",
    ),
]


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "case, kind, valid, invalid, error_type, expected", CASES, ids=[r[0] for r in CASES]
)
def test_python_constructor_field_and_raw_value(
    case, kind, valid, invalid, error_type, expected
):
    cls = step_type(kind)
    assert cls is not None
    cls(**valid)
    error_class = TypeError if error_type == "TypeError" else ValueError
    with pytest.raises(error_class) as error:
        cls(**invalid)
    assert type(error.value) is error_class
    assert str(error.value) == expected


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "case, expected",
    [
        (
            "maxflow",
            "MaxFlow: preset and model are exclusive, got (<unprintable Bad>, <unprintable Bad>)",
        ),
        (
            "alpha",
            "TrafficMatrixPlacement: alpha and alpha_from_step are exclusive, got (1, <unprintable Bad>)",
        ),
        (
            "states",
            "workflow.TrafficMatrixPlacement.failure_states: expected a list of failure states, got <unprintable Bad>",
        ),
    ],
)
def test_a_raw_value_cannot_replace_its_refusal(case, expected):
    from ngraph.workflow import MaxFlow, TrafficMatrixPlacement

    class Bad:
        def __repr__(self):
            raise RuntimeError("unprintable")

    with pytest.raises(ValueError) as error:
        if case == "maxflow":
            MaxFlow(preset=Bad(), model=Bad())
        elif case == "alpha":
            TrafficMatrixPlacement(demand_set="load", alpha=1, alpha_from_step=Bad())
        else:
            TrafficMatrixPlacement(demand_set="load", failure_states=Bad())
    assert str(error.value) == expected
    if case == "maxflow":
        MaxFlow()
    else:
        TrafficMatrixPlacement(
            demand_set="load", alpha=1, failure_states=("converged",)
        )
