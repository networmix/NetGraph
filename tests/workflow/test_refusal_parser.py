"""Workflow parser refusals retain field context before constructor normalization."""

from copy import deepcopy

import pytest

from ngraph.workflow.parse import build_workflow_steps

CASES = [
    (
        "parser_missing_type",
        {"name": "bad"},
        "workflow[2] (name 'bad') = {'name': 'bad'}: Each workflow entry must have a 'type' field "
        "indicating the WorkflowStep subclass to use.",
    ),
    (
        "parser_unknown_field",
        {"type": "BuildGraph", "name": "bad", "bogus": 1},
        "workflow[2] (name 'bad') = {'type': 'BuildGraph', 'name': 'bad', 'bogus': 1}: Unrecognized "
        "key(s) in workflow step 'bad': bogus. Allowed keys are: ['add_reverse', 'name', 'seed']",
    ),
    (
        "parser_missing_source",
        {"type": "MaxFlow", "name": "bad", "target": "^B$"},
        "workflow[2] (name 'bad').source = None: source is required",
    ),
    (
        "parser_missing_target",
        {"type": "MaxFlow", "name": "bad", "source": "^A$"},
        "workflow[2] (name 'bad').target = None: target is required",
    ),
    (
        "parser_bad_source",
        {"type": "MaxFlow", "name": "bad", "source": 3, "target": "^B$"},
        "workflow[2] (name 'bad').source = 3: Selector must be string or dict, got int",
    ),
    (
        "parser_bad_target",
        {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": 3},
        "workflow[2] (name 'bad').target = 3: Selector must be string or dict, got int",
    ),
    (
        "parser_bad_selector_match",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": {"match": {"conditions": [3]}},
            "target": "^B$",
        },
        "workflow[2] (name 'bad').source.match = {'conditions': [3]}: Condition in match must be a "
        "dict, got int",
    ),
    (
        "parser_source_condition",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": {"match": {"conditions": [{"attr": "x", "op": "missing"}]}},
            "target": "^B$",
        },
        "workflow[2] (name 'bad').source.match.conditions[0].op = 'missing': expected one of "
        "['!=', '<', '<=', '==', '>', '>=', 'contains', 'exists', 'in', 'not_contains', 'not_exists', 'not_in'], got 'missing'",
    ),
    (
        "parser_unknown_preset",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "preset": "missing",
        },
        "workflow[2] (name 'bad').preset = 'missing': unknown preset 'missing'",
    ),
    (
        "parser_exclusive_model",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "preset": "SHORTEST_PATHS_ECMP",
            "model": {},
        },
        "workflow[2] (name 'bad') = {'type': 'MaxFlow', 'name': 'bad', 'source': '^A$', 'targ...: preset "
        "and model are exclusive",
    ),
    (
        "parser_model_mapping",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": 3,
        },
        "workflow[2] (name 'bad').model = 3: expected mapping",
    ),
    (
        "parser_model_missing_routing",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {},
        },
        "workflow[2] (name 'bad').model.routing = None: expected mapping",
    ),
    (
        "parser_model_extra",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"bogus": 1},
        },
        "workflow[2] (name 'bad').model = {'bogus': 1}: Unrecognized key(s) in workflow step bad.model: "
        "bogus. Allowed keys are: ['admission', 'routing']",
    ),
    (
        "parser_model_admission",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"admission": "missing", "routing": {"type": "shortest_paths"}},
        },
        "workflow[2] (name 'bad').model.admission = 'missing': unknown value 'missing'",
    ),
    (
        "parser_model_uppercase",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"admission": "LOSSY", "routing": {"type": "shortest_paths"}},
        },
        "workflow[2] (name 'bad').model.admission = 'LOSSY': expected lowercase enum name",
    ),
    (
        "parser_model_nontext_enum",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"admission": 3, "routing": {"type": "shortest_paths"}},
        },
        "workflow[2] (name 'bad').model.admission = 3: expected lowercase enum name",
    ),
    (
        "parser_model_type",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "missing"}},
        },
        "workflow[2] (name 'bad').model.routing.type = 'missing': unknown routing type 'missing'",
    ),
    (
        "parser_model_weights",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "shortest_paths", "edge_weights": ""}},
        },
        "workflow[2] (name 'bad').model.routing.edge_weights = '': expected a name",
    ),
    (
        "parser_route_names",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {"routing": {"type": "pinned", "routes": []}},
        },
        "workflow[2] (name 'bad').model.routing.routes = []: expected nonempty list of names",
    ),
    (
        "parser_tunnel_count",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {
                "routing": {"type": "distributed_te", "tunnel_count": {"per_head": 0}}
            },
        },
        "workflow[2] (name 'bad').model.routing.tunnel_count.per_head = 0: integer outside [1, 10001), "
        "got 0",
    ),
    (
        "parser_cost_ceiling",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {
                "routing": {
                    "type": "distributed_te",
                    "tunnel_count": {"per_head": 1},
                    "cost_ceiling": {"type": "missing", "value": 1},
                }
            },
        },
        "workflow[2] (name 'bad').model.routing.cost_ceiling.type = 'missing': expected absolute or "
        "stretch",
    ),
    (
        "parser_missing_ceiling",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {
                "routing": {
                    "type": "distributed_te",
                    "tunnel_count": {"per_head": 1},
                    "cost_ceiling": {"type": "absolute"},
                }
            },
        },
        "workflow[2] (name 'bad').model.routing.cost_ceiling = {'type': 'absolute'}: type and value are "
        "required",
    ),
    (
        "parser_bad_ceiling_value",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "model": {
                "routing": {
                    "type": "distributed_te",
                    "tunnel_count": {"per_head": 1},
                    "cost_ceiling": {"type": "stretch", "value": 1.5},
                }
            },
        },
        "workflow[2] (name 'bad').model.routing.cost_ceiling.value = 1.5: expected exact integer or "
        "fraction string, got 1.5",
    ),
    (
        "parser_output_mapping",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "outputs": 3,
        },
        "workflow[2] (name 'bad').outputs = 3: expected mapping",
    ),
    (
        "parser_output_extra",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "outputs": {"bogus": 1},
        },
        "workflow[2] (name 'bad').outputs = {'bogus': 1}: Unrecognized key(s) in workflow step "
        "bad.outputs: bogus. Allowed keys are: ['cost_distribution', 'details', 'edge_flows', "
        "'edge_reservations', 'min_cut', 'residual', 'saturated_boundary_edges']",
    ),
    (
        "parser_output_flag",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "outputs": {"details": "false"},
        },
        "workflow[2] (name 'bad').outputs.details = 'false': expected bool, got 'false'",
    ),
    (
        "parser_old_details",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "export_details": True,
        },
        "workflow[2] (name 'bad').export_details = True: unknown key export_details; use "
        "outputs.details",
    ),
    (
        "parser_old_cost",
        {
            "type": "MaxFlow",
            "name": "bad",
            "source": "^A$",
            "target": "^B$",
            "export_cost_distribution": True,
        },
        "workflow[2] (name 'bad').export_cost_distribution = True: unknown key export_cost_distribution; "
        "use outputs.cost_distribution",
    ),
    (
        "parser_msd_old_details",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "export_details": True,
        },
        "workflow[2] (name 'bad').export_details = True: unknown key export_details; use "
        "outputs.details",
    ),
    (
        "parser_msd_output_extra",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "outputs": {"bogus": 1},
        },
        "workflow[2] (name 'bad').outputs = {'bogus': 1}: Unrecognized key(s) in workflow step "
        "bad.outputs: bogus. Allowed keys are: ['details']",
    ),
    (
        "parser_msd_output_flag",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "outputs": {"details": "false"},
        },
        "workflow[2] (name 'bad').outputs.details = 'false': expected bool, got 'false'",
    ),
    (
        "parser_counts_old_details",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "export_details": True,
        },
        "workflow[2] (name 'bad').export_details = True: unknown key export_details; use "
        "outputs.details",
    ),
    (
        "parser_counts_output_extra",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "outputs": {"cost_distribution": True},
        },
        "workflow[2] (name 'bad').outputs = {'cost_distribution': True}: Unrecognized key(s) in workflow "
        "step bad.outputs: cost_distribution. Allowed keys are: ['details', 'edge_flows', "
        "'edge_reservations', 'min_cut', 'residual', 'saturated_boundary_edges']",
    ),
    (
        "parser_counts_output_flag",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
            "offer": 1,
            "outputs": {"details": "false"},
        },
        "workflow[2] (name 'bad').outputs.details = 'false': expected bool, got 'false'",
    ),
    (
        "parser_counts_not_list",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": 4,
            "design_demand": 1,
            "offer": 1,
        },
        "workflow[2] (name 'bad').counts = 4: expected a list of integers",
    ),
    (
        "parser_counts_duplicate",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1, 1],
            "design_demand": 1,
            "offer": 1,
        },
        "workflow[2] (name 'bad').counts = [1, 1]: duplicate count 1",
    ),
    (
        "parser_counts_invalid",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1.5],
            "design_demand": 1,
            "offer": 1,
        },
        "workflow[2] (name 'bad').counts[0] = 1.5: expected an integer in [1, 10000], got 1.5",
    ),
    (
        "parser_counts_missing_offer",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "design_demand": 1,
        },
        "workflow[2] (name 'bad').offer = None: required",
    ),
    (
        "parser_counts_missing_design",
        {
            "type": "TunnelCountAnalysis",
            "name": "bad",
            "demand_set": "load",
            "counts": [1],
            "offer": 1,
        },
        "workflow[2] (name 'bad').design_demand = None: required",
    ),
    (
        "parser_bad_seed",
        {"type": "BuildGraph", "name": "bad", "seed": True},
        "workflow[2] (name 'bad').seed = True: expected an integer, got True",
    ),
    (
        "parser_bad_flag",
        {"type": "BuildGraph", "name": "bad", "add_reverse": "false"},
        "workflow[2] (name 'bad').add_reverse = 'false': expected bool, got 'false'",
    ),
    (
        "parser_bad_name",
        {"type": "BuildGraph", "name": 3},
        "workflow[2].name = 3: expected text, got 3",
    ),
    (
        "parser_msd_growth",
        {
            "type": "MaximumSupportedDemand",
            "name": "bad",
            "demand_set": "load",
            "growth_factor": 1,
        },
        "workflow[2] (name 'bad').growth_factor = 1: must exceed 1, got 1",
    ),
    (
        "parser_tmp_exclusive",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "alpha": 1,
            "alpha_from_step": "prior",
        },
        "workflow[2] (name 'bad') = {'type': 'TrafficMatrixPlacement', 'name': 'bad', 'demand...: alpha "
        "and alpha_from_step are exclusive, got (1, 'prior')",
    ),
    (
        "parser_tmp_states",
        {
            "type": "TrafficMatrixPlacement",
            "name": "bad",
            "demand_set": "load",
            "failure_states": "converged",
        },
        "workflow[2] (name 'bad').failure_states = 'converged': expected a list of failure states, got "
        "'converged'",
    ),
]


@pytest.mark.timeout(10)
@pytest.mark.parametrize("case, entry, expected", CASES, ids=[r[0] for r in CASES])
def test_parser_refusal_identifies_the_declaration(case, entry, expected):
    first = {"type": "BuildGraph", "name": "g"}
    second = {"type": "BuildGraph", "name": "g2"}
    with pytest.raises(ValueError) as error:
        build_workflow_steps([first, second, deepcopy(entry)], lambda name: None)
    assert str(error.value) == expected


@pytest.mark.timeout(10)
@pytest.mark.parametrize("case, entry, expected", CASES, ids=[r[0] for r in CASES])
def test_parser_refusal_has_a_corrected_control(case, entry, expected):
    fixed = deepcopy(entry)
    if case == "parser_missing_type":
        fixed["type"] = "BuildGraph"
    elif case == "parser_unknown_field":
        fixed.pop("bogus")
    elif case in {
        "parser_missing_source",
        "parser_bad_source",
        "parser_bad_selector_match",
        "parser_source_condition",
    }:
        fixed["source"] = {
            "path": "^A$",
            "match": {"conditions": [{"attr": "x", "op": "exists"}]},
        }
    elif case in {"parser_missing_target", "parser_bad_target"}:
        fixed["target"] = "^B$"
    elif case == "parser_unknown_preset":
        fixed["preset"] = "SHORTEST_PATHS_ECMP"
    elif case == "parser_exclusive_model":
        fixed.pop("model")
    elif (
        case.startswith("parser_model_")
        or case.startswith("parser_route_")
        or case
        in {
            "parser_tunnel_count",
            "parser_cost_ceiling",
            "parser_missing_ceiling",
            "parser_bad_ceiling_value",
        }
    ):
        if case == "parser_route_names":
            fixed["model"] = {"routing": {"type": "pinned", "routes": ["r"]}}
        elif "ceiling" in case or case == "parser_tunnel_count":
            fixed["model"] = {
                "routing": {
                    "type": "distributed_te",
                    "tunnel_count": {"per_head": 1},
                    "cost_ceiling": {"type": "stretch", "value": "3/2"},
                }
            }
        else:
            fixed["model"] = {
                "admission": "lossless",
                "routing": {
                    "type": "shortest_paths",
                    "allocation": "weighted",
                    "weight_basis": "explicit",
                    "edge_weights": "known",
                },
            }
    elif case in {
        "parser_output_mapping",
        "parser_output_extra",
        "parser_output_flag",
        "parser_old_details",
        "parser_old_cost",
        "parser_msd_old_details",
        "parser_msd_output_extra",
        "parser_msd_output_flag",
        "parser_counts_old_details",
        "parser_counts_output_extra",
        "parser_counts_output_flag",
    }:
        fixed.pop("export_details", None)
        fixed.pop("export_cost_distribution", None)
        fixed["outputs"] = {"details": True}
    elif case in {
        "parser_counts_not_list",
        "parser_counts_duplicate",
        "parser_counts_invalid",
    }:
        fixed["counts"] = [1]
    elif case == "parser_counts_missing_offer":
        fixed["offer"] = 1
    elif case == "parser_counts_missing_design":
        fixed["design_demand"] = 1
    elif case == "parser_bad_seed":
        fixed["seed"] = 3
    elif case == "parser_bad_flag":
        fixed["add_reverse"] = False
    elif case == "parser_bad_name":
        fixed["name"] = "bad"
    elif case == "parser_msd_growth":
        fixed["growth_factor"] = 2
    elif case == "parser_tmp_exclusive":
        fixed.pop("alpha_from_step")
    elif case == "parser_tmp_states":
        fixed["failure_states"] = ["converged"]
    else:
        pytest.fail(f"missing control for {case}")
    steps = build_workflow_steps([fixed], lambda name: None)
    assert len(steps) == 1


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "kind, field, value, valid, shown, reason",
    [
        (
            "MaxFlow",
            "offer",
            "wrong",
            1,
            "'wrong'",
            "expected a finite real number, got 'wrong'",
        ),
        (
            "MaxFlow",
            "offer",
            -1,
            1,
            "-1",
            "expected a finite nonnegative amount, got -1",
        ),
        (
            "MaxFlow",
            "offer",
            10**400,
            1,
            "1" + "0" * 56 + "...",
            "physical value is outside binary64 range, got " + "1" + "0" * 56 + "...",
        ),
        (
            "MaxFlow",
            "offer",
            float("nan"),
            1,
            "nan",
            "expected a finite nonnegative amount, got nan",
        ),
        (
            "MaxFlow",
            "mode",
            "missing",
            "combine",
            "'missing'",
            "expected combine or pairwise, got 'missing'",
        ),
        ("MaxFlow", "workers", 0, 1, "0", "integer outside [1, inf), got 0"),
        (
            "CostPower",
            "aggregation_level",
            1.5,
            1,
            "1.5",
            "expected an integer, got 1.5",
        ),
        (
            "NetworkStats",
            "excluded_nodes",
            3,
            ["A"],
            "3",
            "expected a collection, got 3",
        ),
        (
            "NetworkStats",
            "excluded_nodes",
            "A",
            ["A"],
            "'A'",
            "expected a sequence of names, got 'A'",
        ),
        (
            "TrafficMatrixPlacement",
            "interaction",
            "missing",
            "ordered",
            "'missing'",
            "expected ordered or simultaneous, got 'missing'",
        ),
    ],
)
def test_shared_validator_refusals_keep_the_raw_field(
    kind, field, value, valid, shown, reason
):
    entry = {"type": kind, "name": "bad", field: value}
    if kind == "MaxFlow":
        entry.update(source="^A$", target="^B$")
    if kind == "TrafficMatrixPlacement":
        entry["demand_set"] = "load"
    prefix = [{"type": "BuildGraph", "name": "g"}, {"type": "BuildGraph", "name": "g2"}]
    with pytest.raises(ValueError) as error:
        build_workflow_steps([*prefix, deepcopy(entry)], lambda name: None)
    assert str(error.value) == f"workflow[2] (name 'bad').{field} = {shown}: {reason}"
    entry[field] = valid
    assert len(build_workflow_steps([*prefix, entry], lambda name: None)) == 3


@pytest.mark.timeout(10)
def test_a_registered_constructor_key_error_keeps_the_declaration():
    from dataclasses import dataclass

    from ngraph import StepOutput, WorkflowStep, register_workflow_step

    @register_workflow_step("KeyRefusal")
    @dataclass
    class KeyRefusal(WorkflowStep):
        value: int = 4

        def __post_init__(self):
            super().__post_init__()
            if self.value == 3:
                raise KeyError("value = 3: reserved")

        def run(self, context):
            return StepOutput({}, None)

    prefix = [{"type": "BuildGraph", "name": "g"}, {"type": "BuildGraph", "name": "g2"}]
    entry = {"type": "KeyRefusal", "name": "bad", "value": 3}
    with pytest.raises(ValueError) as error:
        build_workflow_steps([*prefix, entry], lambda name: None)
    assert str(error.value) == (
        "workflow[2] (name 'bad') = {'type': 'KeyRefusal', 'name': 'bad', 'value': 3}: 'value = 3: reserved'"
    )
    entry["value"] = 4
    assert len(build_workflow_steps([*prefix, entry], lambda name: None)) == 3


@pytest.mark.timeout(10)
@pytest.mark.parametrize("endpoint", ["source", "target"])
@pytest.mark.parametrize(
    "condition, field, shown, reason",
    [
        (
            {"attr": "role", "op": "in", "value": 3},
            "value",
            "3",
            "'in' requires a list, got 3",
        ),
        ({"attr": 3, "op": "==", "value": 1}, "attr", "3", "expected text, got 3"),
    ],
)
def test_selector_constructor_fields_keep_the_nested_location(
    endpoint, condition, field, shown, reason
):
    entry = {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "^B$"}
    entry[endpoint] = {
        "path": "^A$" if endpoint == "source" else "^B$",
        "match": {"conditions": [condition]},
    }
    prefix = [{"type": "BuildGraph", "name": "g"}, {"type": "BuildGraph", "name": "g2"}]
    with pytest.raises(ValueError) as error:
        build_workflow_steps([*prefix, deepcopy(entry)], lambda name: None)
    assert (
        str(error.value)
        == f"workflow[2] (name 'bad').{endpoint}.match.conditions[0].{field} = {shown}: {reason}"
    )
    entry[endpoint]["match"]["conditions"][0] = {
        "attr": "role",
        "op": "in",
        "value": [1],
    }
    assert len(build_workflow_steps([*prefix, entry], lambda name: None)) == 3
