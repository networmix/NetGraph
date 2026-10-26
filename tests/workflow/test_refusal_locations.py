"""A refused workflow entry identifies its position, name, field and supplied value."""

from copy import deepcopy

import pytest
import yaml

from ngraph import Scenario, prepare

NET = {
    "nodes": {"A": {}, "B": {}, "C": {}},
    "links": [
        {"source": "A", "target": "B", "capacity": 8, "cost": 3},
        {"source": "B", "target": "C", "capacity": 8, "cost": 5},
    ],
}


def document(entry):
    return {
        "network": NET,
        "demands": {"load": [{"source": "^A$", "target": "^B$", "volume": 1}]},
        "units": {"resolution": 1},
        "workflow": [
            {"type": "BuildGraph", "name": "g"},
            {"type": "BuildGraph", "name": "g2"},
            entry,
        ],
    }


CASES = [
    (
        "unknown_type",
        {"type": "NoSuchStep", "name": "bad"},
        "load",
        "workflow[2] (name 'bad').type = 'NoSuchStep': unrecognized step type",
    ),
    (
        "unknown_unnamed_type",
        {"type": "NoSuchStep"},
        "load",
        "workflow[2].type = 'NoSuchStep': unrecognized step type",
    ),
    (
        "missing_type",
        {"name": "bad"},
        "load",
        "workflow[2] (name 'bad') = {'name': 'bad'}: 'type' is a required property",
    ),
    (
        "non_string_type",
        {"type": 3, "name": "bad"},
        "load",
        "workflow[2] (name 'bad').type = 3: 3 is not of type 'string'",
    ),
    ("non_mapping_entry", 7, "load", "workflow[2] = 7: 7 is not of type 'object'"),
    (
        "duplicate_name",
        {"type": "BuildGraph", "name": "g"},
        "load",
        "workflow[2] (name 'g').name = 'g': Duplicate workflow step name 'g'. Each step must have a "
        "unique name; got 'g'.",
    ),
    (
        "unknown_field",
        {"type": "BuildGraph", "name": "bad", "bogus": 1},
        "load",
        "workflow[2] (name 'bad') = {'type': 'BuildGraph', 'name': 'bad', 'bogus': 1}: Additional "
        "properties are not allowed ('bogus' was unexpected)",
    ),
    (
        "bad_name",
        {"type": "BuildGraph", "name": 3},
        "load",
        "workflow[2].name = 3: 3 is not of type 'string'",
    ),
    (
        "bad_seed",
        {"type": "BuildGraph", "name": "bad", "seed": True},
        "load",
        "workflow[2] (name 'bad').seed = True: True is not of type 'integer', 'null'",
    ),
    (
        "bad_build_flag",
        {"type": "BuildGraph", "name": "bad", "add_reverse": "false"},
        "load",
        "workflow[2] (name 'bad').add_reverse = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "bad_cost_flag",
        {"type": "CostPower", "name": "bad", "include_disabled": "false"},
        "load",
        "workflow[2] (name 'bad').include_disabled = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "bad_cost_level",
        {"type": "CostPower", "name": "bad", "aggregation_level": -1},
        "load",
        "workflow[2] (name 'bad').aggregation_level = -1: -1 is less than the minimum of 0",
    ),
    (
        "bad_stats_nodes",
        {"type": "NetworkStats", "name": "bad", "excluded_nodes": "A"},
        "load",
        "workflow[2] (name 'bad').excluded_nodes = 'A': 'A' is not of type 'array'",
    ),
    (
        "bad_stats_links",
        {"type": "NetworkStats", "name": "bad", "excluded_links": [3]},
        "load",
        "workflow[2] (name 'bad').excluded_links[0] = 3: 3 is not of type 'string'",
    ),
    (
        "unknown_node",
        {"type": "NetworkStats", "name": "bad", "excluded_nodes": ["missing"]},
        "prepare",
        "workflow[2] (name 'bad').excluded_nodes: unknown node 'missing'",
    ),
    (
        "unknown_link",
        {"type": "NetworkStats", "name": "bad", "excluded_links": ["missing"]},
        "prepare",
        "workflow[2] (name 'bad').excluded_links: unknown link 'missing'",
    ),
    (
        "missing_source",
        {"type": "MaxFlow", "name": "bad", "target": "^B$"},
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'target': '^B$'}: 'source' is a "
        "required property",
    ),
    (
        "missing_target",
        {"type": "MaxFlow", "name": "bad", "source": "^A$"},
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$'}: 'target' is a "
        "required property",
    ),
    (
        "bad_source_pattern",
        {"type": "MaxFlow", "name": "bad", "source": "[", "target": "^B$"},
        "load",
        "workflow[2] (name 'bad').source.path = '[': invalid pattern '[': unterminated character set at "
        "position 0",
    ),
    (
        "bad_target_pattern",
        {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "["},
        "load",
        "workflow[2] (name 'bad').target.path = '[': invalid pattern '[': unterminated character set at "
        "position 0",
    ),
    (
        "unknown_preset",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "preset": "NO_SUCH",
        },
        "load",
        "workflow[2] (name 'bad').preset = 'NO_SUCH': 'NO_SUCH' is not valid under any of the given "
        "schemas",
    ),
    (
        "exclusive_model",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "preset": "TE_MAXFLOW_UNLIM",
            "model": {"routing": {"type": "centralized_te"}},
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$', 'targ...: {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$', 'target': '^B$', 'preset': 'TE_MAXFLOW_UNLIM', 'model': {'routing': {'type': 'centralized_te'}}} should not be valid under {'required': ['preset', 'model'], 'propert...",
    ),
    (
        "unknown_model_kind",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "missing"}},
        },
        "load",
        "workflow[2] (name 'bad').model.routing = {'type': 'missing'}: {'type': 'missing'} is not valid "
        "under any of the given schemas",
    ),
    (
        "bad_model_enum",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "shortest_paths", "allocation": "missing"}},
        },
        "load",
        "workflow[2] (name 'bad').model.routing = {'type': 'shortest_paths', 'allocation': 'missing'}: "
        "{'type': 'shortest_paths', 'allocation': 'missing'} is not valid under any of the given "
        "schemas",
    ),
    (
        "bad_workers",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "workers": 0,
        },
        "load",
        "workflow[2] (name 'bad').workers = 0: 0 is less than the minimum of 1",
    ),
    (
        "bad_mode",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "mode": "missing",
        },
        "load",
        "workflow[2] (name 'bad').mode = 'missing': 'missing' is not one of ['combine', 'pairwise']",
    ),
    (
        "bad_offer",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "offer": -1,
        },
        "load",
        "workflow[2] (name 'bad').offer = -1: -1 is less than the minimum of 0",
    ),
    (
        "bad_design",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "design_demand": -1,
        },
        "load",
        "workflow[2] (name 'bad').design_demand = -1: -1 is less than the minimum of 0",
    ),
    (
        "bad_iterations",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "iterations": -1,
        },
        "load",
        "workflow[2] (name 'bad').iterations = -1: -1 is less than the minimum of 0",
    ),
    (
        "bad_failure_trace",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "failure_trace": "false",
        },
        "load",
        "workflow[2] (name 'bad').failure_trace = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "unknown_failure",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "failure_policy": "missing",
        },
        "prepare",
        "workflow[2] (name 'bad').failure_policy = 'missing': unknown failure policy",
    ),
    (
        "unknown_demand_placement",
        {"type": "TrafficMatrixPlacement", "name": "bad", "demand_set": "missing"},
        "prepare",
        "workflow[2] (name 'bad').demand_set = 'missing': unknown demand set",
    ),
    (
        "unknown_demand_msd",
        {"type": "MaximumSupportedDemand", "name": "bad", "demand_set": "missing"},
        "prepare",
        "workflow[2] (name 'bad').demand_set = 'missing': unknown demand set",
    ),
    (
        "unknown_demand_counts",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "missing",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
        },
        "prepare",
        "workflow[2] (name 'bad').demand_set = 'missing': unknown demand set",
    ),
    (
        "unknown_alpha_step",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "alpha_from_step": "missing",
        },
        "prepare",
        "workflow[2] (name 'bad').alpha_from_step = 'missing': must name an earlier MSD step",
    ),
    (
        "exclusive_alpha",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "alpha": 1,
            "alpha_from_step": "missing",
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'TrafficMatrixPlacement', 'name': 'bad', 'demand...: "
        "{'type': 'TrafficMatrixPlacement', 'name': 'bad', 'demand_set': 'load', 'alpha': 1, "
        "'alpha_from_step': 'missing'} should not be valid under {'required': ['alpha', "
        "'alpha_from_step']}",
    ),
    (
        "bad_interaction",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "interaction": "missing",
        },
        "load",
        "workflow[2] (name 'bad').interaction = 'missing': 'missing' is not one of ['ordered', "
        "'simultaneous']",
    ),
    (
        "bad_states",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "failure_states": ["missing"],
        },
        "load",
        "workflow[2] (name 'bad').failure_states[0] = 'missing': 'missing' is not one of ['converged', "
        "'stale', 'repair']",
    ),
    (
        "empty_states",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "failure_states": [],
        },
        "load",
        "workflow[2] (name 'bad').failure_states = []: [] should be non-empty",
    ),
    (
        "bad_alpha",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "alpha": 0,
        },
        "load",
        "workflow[2] (name 'bad').alpha = 0: 0 is less than or equal to the minimum of 0",
    ),
    (
        "bad_alpha_name",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "alpha_from_step": "",
        },
        "load",
        "workflow[2] (name 'bad').alpha_from_step = '': '' should be non-empty",
    ),
    (
        "bad_failure_name",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "failure_policy": "",
        },
        "load",
        "workflow[2] (name 'bad').failure_policy = '': '' should be non-empty",
    ),
    (
        "bad_output_flag",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "outputs": {"details": "false"},
        },
        "load",
        "workflow[2] (name 'bad').outputs.details = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "old_output_field",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "export_details": True,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$', 'targ...: "
        "Additional properties are not allowed ('export_details' was unexpected)",
    ),
    (
        "old_cost_output_field",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "export_cost_distribution": True,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$', 'targ...: "
        "Additional properties are not allowed ('export_cost_distribution' was unexpected)",
    ),
    (
        "unknown_output_field",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "outputs": {"bogus": True},
        },
        "load",
        "workflow[2] (name 'bad').outputs = {'bogus': True}: Additional properties are not allowed "
        "('bogus' was unexpected)",
    ),
    (
        "msd_old_output",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "export_details": True,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaximumSupportedDemand', 'name': 'bad', 'demand...: "
        "Additional properties are not allowed ('export_details' was unexpected)",
    ),
    (
        "msd_bad_output",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "outputs": {"details": "false"},
        },
        "load",
        "workflow[2] (name 'bad').outputs.details = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "msd_bad_growth",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "growth_factor": 1,
        },
        "load",
        "workflow[2] (name 'bad').growth_factor = 1: 1 is less than or equal to the minimum of 1",
    ),
    (
        "msd_bad_range",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "alpha_min": 2,
            "alpha_start": 1,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'MaximumSupportedDemand', 'name': 'bad', 'demand...: "
        "require alpha_min <= alpha_start <= alpha_max, got (2, 1, 1000000000.0)",
    ),
    (
        "counts_old_output",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "export_details": True,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'TunnelCountAnalysis', 'name': 'bad', 'demand_se...: "
        "Additional properties are not allowed ('export_details' was unexpected)",
    ),
    (
        "counts_bad_output",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "outputs": {"details": "false"},
        },
        "load",
        "workflow[2] (name 'bad').outputs.details = 'false': 'false' is not of type 'boolean'",
    ),
    (
        "counts_not_list",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": "1",
            "design_demand": 1,
            "offer": 1,
        },
        "load",
        "workflow[2] (name 'bad').counts = '1': '1' is not of type 'array'",
    ),
    (
        "counts_duplicate",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1, 1],
            "design_demand": 1,
            "offer": 1,
        },
        "load",
        "workflow[2] (name 'bad').counts = [1, 1]: [1, 1] has non-unique elements",
    ),
    (
        "counts_empty",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [],
            "design_demand": 1,
            "offer": 1,
        },
        "load",
        "workflow[2] (name 'bad').counts = []: give at least one count or up_to, got ()",
    ),
    (
        "counts_bad_value",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [0],
            "design_demand": 1,
            "offer": 1,
        },
        "load",
        "workflow[2] (name 'bad').counts[0] = 0: 0 is less than the minimum of 1",
    ),
    (
        "counts_bad_up_to",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "up_to": 0,
        },
        "load",
        "workflow[2] (name 'bad').up_to = 0: 0 is less than the minimum of 1",
    ),
    (
        "counts_missing_offer",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'TunnelCountAnalysis', 'name': 'bad', 'demand_se...: "
        "'offer' is a required property",
    ),
    (
        "counts_missing_design",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "offer": 1,
        },
        "load",
        "workflow[2] (name 'bad') = {'type': 'TunnelCountAnalysis', 'name': 'bad', 'demand_se...: "
        "'design_demand' is a required property",
    ),
    (
        "counts_wrong_model",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
        },
        "prepare",
        "workflow[2] (name 'bad').demand_set = 'load': workflow.bad.demands: demand load|0|0: "
        "TunnelCountAnalysis needs a CentralizedTE model with a tunnel count",
    ),
    (
        "empty_source",
        {"type": "MaxFlow", "name": "bad", "source": "^missing$", "target": "^B$"},
        "prepare",
        "workflow[2] (name 'bad').source: empty selection",
    ),
    (
        "empty_target",
        {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "^missing$"},
        "prepare",
        "workflow[2] (name 'bad').target: empty selection",
    ),
    (
        "overlapping_pairs",
        {"type": "MaxFlow", "name": "bad", "source": "^(A|B)$", "target": "^(B|C)$"},
        "prepare",
        "workflow[2] (name 'bad'): step bad.pair[0]: "
        "non-diagonal source/target overlap: ['B']",
    ),
    (
        "unknown_route",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "pinned", "routes": ["missing"]}},
        },
        "prepare",
        "workflow[2] (name 'bad').model.routing.routes: unknown route 'missing'",
    ),
    (
        "unknown_weights",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {
                "routing": {
                    "type": "shortest_paths",
                    "allocation": "weighted",
                    "weight_basis": "explicit",
                    "edge_weights": "missing",
                }
            },
        },
        "prepare",
        "workflow[2] (name 'bad').model.routing.edge_weights = 'missing': unknown weights",
    ),
]


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "case, entry, stage, expected", CASES, ids=[r[0] for r in CASES]
)
def test_refusal_identifies_the_declaration(case, entry, stage, expected):
    text = yaml.safe_dump(document(entry), sort_keys=False)
    if stage == "load":

        def call():
            return Scenario.from_yaml(text)
    else:
        scenario = Scenario.from_yaml(text)

        def call():
            return prepare(scenario)

    with pytest.raises(ValueError) as error:
        call()
    assert str(error.value) == expected


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "case, entry, stage, expected", CASES, ids=[r[0] for r in CASES]
)
def test_each_refusal_has_a_valid_control(case, entry, stage, expected):
    # Correct only the refused field (or one side of an exclusive pair).
    if not isinstance(entry, dict):
        fixed = {"type": "BuildGraph", "name": "bad"}
    else:
        fixed = deepcopy(entry)
    changes = {
        "unknown_type": {"type": "BuildGraph"},
        "unknown_unnamed_type": {"type": "BuildGraph", "name": "bad"},
        "missing_type": {"type": "BuildGraph"},
        "non_string_type": {"type": "BuildGraph"},
        "duplicate_name": {"name": "bad"},
        "bad_name": {"name": "bad"},
        "bad_seed": {"seed": 3},
        "bad_build_flag": {"add_reverse": False},
        "bad_cost_flag": {"include_disabled": False},
        "bad_cost_level": {"aggregation_level": 0},
        "bad_stats_nodes": {"excluded_nodes": ["A"]},
        "bad_stats_links": {"excluded_links": ["A|B|0"]},
        "unknown_node": {"excluded_nodes": ["A"]},
        "unknown_link": {"excluded_links": ["A|B|0"]},
        "missing_source": {"source": "^A$"},
        "bad_source_pattern": {"source": "^A$"},
        "missing_target": {"target": "^B$"},
        "bad_target_pattern": {"target": "^B$"},
        "unknown_preset": {"preset": "TE_MAXFLOW_UNLIM"},
        "unknown_model_kind": {"model": {"routing": {"type": "shortest_paths"}}},
        "bad_model_enum": {
            "model": {"routing": {"type": "shortest_paths", "allocation": "equal"}}
        },
        "bad_workers": {"workers": 1},
        "bad_mode": {"mode": "combine"},
        "bad_offer": {"offer": 1},
        "bad_design": {"design_demand": 1, "offer": 1, "preset": "TE_ECMP_16_LSP"},
        "bad_iterations": {"iterations": 0},
        "bad_failure_trace": {"failure_trace": False},
        "unknown_failure": {"failure_policy": "f"},
        "bad_failure_name": {"failure_policy": "f"},
        "unknown_demand_placement": {"demand_set": "load"},
        "unknown_demand_msd": {"demand_set": "load"},
        "unknown_demand_counts": {"demand_set": "load"},
        "unknown_alpha_step": {"alpha_from_step": "msd"},
        "bad_alpha_name": {"alpha_from_step": "msd"},
        "bad_interaction": {"interaction": "ordered"},
        "bad_states": {"failure_states": ["converged"]},
        "empty_states": {"failure_states": ["converged"]},
        "bad_alpha": {"alpha": 1},
        "bad_output_flag": {"outputs": {"details": False}},
        "unknown_output_field": {"outputs": {"details": True}},
        "msd_bad_output": {"outputs": {"details": False}},
        "msd_bad_growth": {"growth_factor": 2},
        "msd_bad_range": {"alpha_min": 1},
        "counts_bad_output": {"outputs": {"details": False}},
        "counts_not_list": {"counts": [1]},
        "counts_duplicate": {"counts": [1]},
        "counts_empty": {"counts": [1]},
        "counts_bad_value": {"counts": [1]},
        "counts_bad_up_to": {"up_to": 1},
        "counts_missing_offer": {"offer": 1},
        "counts_missing_design": {"design_demand": 1},
        "empty_source": {"source": "^A$"},
        "empty_target": {"target": "^B$"},
        "overlapping_pairs": {"target": "^C$"},
    }
    fixed.update(changes.get(case, {}))
    for key, cases in {
        "bogus": {"unknown_field"},
        "model": {"exclusive_model"},
        "alpha_from_step": {"exclusive_alpha"},
        "export_details": {"old_output_field", "msd_old_output", "counts_old_output"},
        "export_cost_distribution": {"old_cost_output_field"},
    }.items():
        if case in cases:
            fixed.pop(key)
    data = deepcopy(document(fixed))
    data["demands"]["load"][0]["model"] = {
        "routing": {
            "type": "centralized_te",
            "source_allocation": "equal",
            "tunnel_count": {"per_head": 1},
        },
        "admission": "lossy",
    }
    data["failures"] = {"f": {"modes": [{"weight": 1, "rules": []}]}}
    if case in {"unknown_alpha_step", "bad_alpha_name"}:
        data["workflow"][1] = {
            "type": "MaximumSupportedDemand",
            "name": "msd",
            "demand_set": "load",
        }
    if case == "unknown_route":
        data["routes"] = {"missing": {"head": "A", "nodes": ["A", "B"]}}
    if case == "unknown_weights":
        data["weights"] = {"missing": {"entries": []}}
    scenario = Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False))
    assert len(scenario.workflow) == 3
    assert prepare(scenario).scenario.workflow[2].name == "bad"


@pytest.mark.timeout(10)
@pytest.mark.parametrize("name, clause", [("bad", " (name 'bad')"), (None, "")])
def test_yaml_scalar_conversion_refusal_identifies_the_step(name, clause):
    import sys

    previous = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    try:
        declaration = "   name: bad" if name else "   # unnamed"
        text = (
            "network: {}\nworkflow:\n - {type: BuildGraph, name: g}\n"
            " - {type: BuildGraph, name: g2}\n - type: BuildGraph\n"
            f"{declaration}\n   seed: {'9' * 5000}\n"
        )
        with pytest.raises(ValueError) as error:
            Scenario.from_yaml(text)
        assert str(error.value) == (
            f"workflow[2]{clause}.seed = an integer of 5000 digits: "
            "invalid YAML scalar at line 7, column 10"
        )
        prepare(Scenario.from_yaml(text.replace("9" * 5000, "9")))
    finally:
        sys.set_int_max_str_digits(previous)


@pytest.mark.timeout(10)
def test_an_empty_type_identifies_the_supplied_field():
    entry = {"type": "", "name": "bad"}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(document(entry), sort_keys=False))
    assert (
        str(error.value) == "workflow[2] (name 'bad').type = '': '' should be non-empty"
    )
    from ngraph.workflow.parse import build_workflow_steps

    with pytest.raises(ValueError) as error:
        build_workflow_steps(document(entry)["workflow"], lambda name: None)
    assert str(error.value) == (
        "workflow[2] (name 'bad').type = '': Each workflow entry must have a 'type' field "
        "indicating the WorkflowStep subclass to use."
    )
    entry["type"] = "BuildGraph"
    prepare(Scenario.from_yaml(yaml.safe_dump(document(entry), sort_keys=False)))


@pytest.mark.timeout(10)
@pytest.mark.parametrize("endpoint", ["source", "target"])
@pytest.mark.parametrize(
    "value, suffix",
    [
        (float("nan"), ""),
        ({"rate.avg": float("nan")}, ".rate.avg"),
        ([1, float("nan")], "[1]"),
    ],
)
def test_nested_selector_values_keep_their_field_and_raw_value(endpoint, value, suffix):
    entry = {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "^B$"}
    entry[endpoint] = {
        "path": "^A$" if endpoint == "source" else "^B$",
        "match": {"conditions": [{"attr": "role", "op": "==", "value": value}]},
    }
    data = deepcopy(document(entry))
    for node in data["network"]["nodes"].values():
        node["attrs"] = {"role": 1}
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False))
    assert str(error.value) == (
        f"workflow[2] (name 'bad').{endpoint}.match.conditions[0].value{suffix} = nan: "
        "expected finite JSON data, got float = nan"
    )
    data["workflow"][2][endpoint]["match"]["conditions"][0]["value"] = 1
    prepare(Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False)))


@pytest.mark.timeout(10)
@pytest.mark.parametrize("endpoint", ["source", "target"])
@pytest.mark.parametrize("preset", [None, "TE_ECMP_16_LSP"])
def test_empty_selector_names_the_normalized_field(endpoint, preset):
    entry = {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "^B$"}
    if preset is not None:
        entry["preset"] = preset
    entry[endpoint] = {"path": "^missing$"}
    with pytest.raises(ValueError) as error:
        prepare(Scenario.from_yaml(yaml.safe_dump(document(entry), sort_keys=False)))
    assert str(error.value) == (f"workflow[2] (name 'bad').{endpoint}: empty selection")
    entry[endpoint] = {"path": "^A$" if endpoint == "source" else "^B$"}
    prepare(Scenario.from_yaml(yaml.safe_dump(document(entry), sort_keys=False)))
