"""YAML construction, omission, schema and error boundaries stay in agreement."""

import copy
import json
from importlib import resources

import jsonschema
import pytest
import yaml

from ngraph import Scenario
from ngraph.dsl.loader import load_scenario_yaml
from ngraph.model.selectors import normalize_selector
from tests.dsl.test_input_parity import BASE, STEP

# Both forms keep the sibling representation present when the optional field is null.
CHILD_BASE = copy.deepcopy(BASE)
CHILD_BASE["forwarding_groups"] = {
    "tree": {
        "router": "A",
        "groups": [
            {
                "children": [
                    {"children": [{"edge": {"link": "A|T|0", "direction": "forward"}}]}
                ]
            }
        ],
    },
    "leaf": {
        "router": "A",
        "groups": [{"children": [{"edge": {"link": "A|T|0", "direction": "forward"}}]}],
    },
}

CHILD_BASE["routing"] = {"igp_domain": ".*", "bgp_edge": ".*"}
CHILD_BASE["wcmp_controller"] = {}

SCHEMA = json.loads(
    resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
)
VALIDATOR = jsonschema.validators.validator_for(SCHEMA)(SCHEMA)


def document(path, value, base=BASE):
    if path[0] == "forwarding_groups" and len(path) > 1:
        base = CHILD_BASE
    data = copy.deepcopy(base)
    node = data
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value
    return data


def load(data):
    return Scenario.from_yaml(yaml.safe_dump(data, sort_keys=False))


NULL_CASES = [
    (
        ["workflow", STEP["MaxFlow"], "preset"],
        lambda s: s.workflow[STEP["MaxFlow"]].preset,
    ),
    (
        ["workflow", STEP["MaxFlow"], "model"],
        lambda s: s.workflow[STEP["MaxFlow"]].model,
    ),
    (
        ["forwarding_groups", "tree", "groups", 0, "children", 0, "edge"],
        lambda s: s.forwarding_groups["tree"].groups[0].children[0],
    ),
    (
        ["forwarding_groups", "leaf", "groups", 0, "children", 0, "children"],
        lambda s: s.forwarding_groups["leaf"].groups[0].children[0],
    ),
    (["seed"], lambda s: s.seed),
    (["units"], lambda s: s.units),
    (["components"], lambda s: dict(s.components_library.components)),
    (["routes"], lambda s: s.routes),
    (["supports"], lambda s: s.supports),
    (["weights"], lambda s: s.weights),
    (["forwarding_groups"], lambda s: s.forwarding_groups),
    (["routing"], lambda s: s.routing),
    (["wcmp_controller"], lambda s: s.wcmp_controller),
    (["demands"], lambda s: s.demand_sets),
    (["failures"], lambda s: s.failure_policies),
    (
        ["failures", "fp", "modes", 0, "rules", 0, "path"],
        lambda s: s.failure_policies["fp"].modes[0].rules[0].path,
    ),
    (
        ["failures", "fp", "modes", 0, "rules", 0, "weight_by"],
        lambda s: s.failure_policies["fp"].modes[0].rules[0].weight_by,
    ),
    (
        ["failures", "fp", "modes", 0, "rules", 0, "match"],
        lambda s: s.failure_policies["fp"].modes[0].rules[0].conditions,
    ),
    (["demands", "d", 0, "id"], lambda s: s.demand_sets["d"].demands[0].id),
    (["routes", "r", "support"], lambda s: s.routes["r"]),
    (["routes", "r", "edges"], lambda s: s.routes["r"]),
    (
        ["workflow", STEP["MaxFlow"], "offer"],
        lambda s: s.workflow[STEP["MaxFlow"]].offer,
    ),
    (
        ["workflow", STEP["MaxFlow"], "design_demand"],
        lambda s: s.workflow[STEP["MaxFlow"]].design_demand,
    ),
    (
        ["workflow", STEP["MaxFlow"], "failure_policy"],
        lambda s: s.workflow[STEP["MaxFlow"]].failure_policy,
    ),
    (
        ["workflow", STEP["TrafficMatrixPlacement"], "alpha"],
        lambda s: s.workflow[STEP["TrafficMatrixPlacement"]].alpha,
    ),
    (
        ["workflow", STEP["TrafficMatrixPlacement"], "alpha_from_step"],
        lambda s: s.workflow[STEP["TrafficMatrixPlacement"]].alpha_from_step,
    ),
    (
        ["workflow", STEP["TrafficMatrixPlacement"], "failure_policy"],
        lambda s: s.workflow[STEP["TrafficMatrixPlacement"]].failure_policy,
    ),
    *[
        (["workflow", i, "seed"], lambda s, i=i: s.workflow[i].seed)
        for i in range(len(BASE["workflow"]))
    ],
]


@pytest.mark.parametrize("path,read", NULL_CASES)
def test_explicit_null_means_omitted_for_optional_fields(path, read):
    explicit = document(path, None)
    omitted = copy.deepcopy(explicit)
    node = omitted
    for part in path[:-1]:
        node = node[part]
    del node[path[-1]]
    VALIDATOR.validate(explicit)
    left, right = read(load(explicit)), read(load(omitted))
    assert left == right and type(left) is type(right)


@pytest.mark.parametrize("field", ["path", "group_by", "match", "active_only"])
def test_selector_optional_null_uses_the_context_default(field):
    raw = {"path": "^A$", "group_by": "role"}
    raw[field] = None
    data = document(["demands", "d", 0, "source"], raw)
    explicit = load(data).demand_sets["d"].demands[0].source
    del raw[field]
    omitted = (
        load(document(["demands", "d", 0, "source"], raw))
        .demand_sets["d"]
        .demands[0]
        .source
    )
    assert explicit == omitted == normalize_selector(raw, "demand")
    assert explicit.active_only is True


def test_tunnel_count_optional_null_is_omission():
    data = {
        "workflow": [
            {
                "type": "TunnelCountAnalysis",
                "demand_set": "d",
                "counts": [1],
                "offer": 1,
                "design_demand": 1,
            }
        ]
    }
    omitted = load(data).workflow[0]
    data["workflow"][0]["up_to"] = None
    assert load(data).workflow[0].up_to is omitted.up_to is None
    assert load(data).workflow[0].counts == omitted.counts == (1,)


@pytest.mark.parametrize(
    "kind,fields",
    [
        ("shortest_paths", ["source_allocation", "weight_basis", "edge_weights"]),
        ("pinned", ["allocation", "weight_basis", "edge_weights"]),
        ("centralized_te", ["tunnel_count"]),
    ],
)
def test_optional_routing_inputs_accept_null(kind, fields):
    routing = {"type": kind}
    if kind == "pinned":
        routing["routes"] = ["r"]
    if kind == "centralized_te":
        routing["source_allocation"] = "equal"
    raw = {"source": "A", "target": "T", "volume": 1, "model": {"routing": routing}}
    data = {"demands": {"d": [raw]}}
    expected = load(data).demand_sets["d"].demands[0].policy
    for field in fields:
        routing[field] = None
    assert load(data).demand_sets["d"].demands[0].policy == expected


@pytest.mark.parametrize(
    "path,bad,good",
    [
        (["network", "link_rules", 0, "cost"], 1.5, 2.0),
        (["network", "link_rules", 0, "cost"], 0, 1),
        (["network", "link_rules", 0, "cost"], 2**62, 2**62 - 1),
        (["network", "link_rules", 0, "capacity"], -1, 0),
        (["network", "nodes", "A", "risk_groups"], [""], ["rg"]),
        (["network", "links", 0, "risk_groups"], [""], ["rg"]),
        (["network", "link_rules", 0, "risk_groups"], [""], ["rg"]),
        (["network", "node_rules", 0, "risk_groups"], [""], ["rg"]),
        (["workflow", STEP["MaxFlow"], "failure_policy"], "", "fp"),
        (["workflow", STEP["TrafficMatrixPlacement"], "failure_policy"], "", "fp"),
        (["workflow", STEP["MaximumSupportedDemand"], "growth_factor"], 1, 1.5),
        (["units", "resolution"], 2**-33, 2**-32),
        (["units", "resolution"], 2**33, 2**32),
        (["components", "chassis", "count"], 0, 1),
        (["supports", "r", "edges"], [], [{"link": "A|T|0", "direction": "forward"}]),
    ],
)
def test_schema_alone_refuses_local_bad_values(path, bad, good):
    base = copy.deepcopy(BASE)
    base["network"]["link_rules"] = [{"source": "A", "target": "T"}]
    base["network"]["node_rules"] = [{"path": "A"}]
    base["supports"] = {"r": {"edges": [{"link": "A|T|0", "direction": "forward"}]}}
    with pytest.raises(jsonschema.ValidationError):
        VALIDATOR.validate(document(path, bad, base))
    with pytest.raises(ValueError):
        load(document(path, bad, base))
    VALIDATOR.validate(document(path, good, base))
    assert load(document(path, good, base))


@pytest.mark.parametrize("op", ["in", "not_in"])
def test_schema_and_constructor_require_membership_lists(op):
    path = ["demands", "d", 0, "source"]

    def selector(value):
        return {
            "path": "A",
            "match": {"conditions": [{"attr": "role", "op": op, "value": value}]},
        }

    for bad in (1, None, "edge"):
        data = document(path, selector(bad))
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(data)
        with pytest.raises(ValueError) as error:
            load(data)
        assert (
            str(error.value)
            == f"demands.d[0].source.match.conditions[0].value = {bad!r}: {bad!r} is not of type 'array'"
        )
    assert load(document(path, selector(["edge"])))


@pytest.mark.parametrize("section", ["links", "link_rules", "node_rules"])
@pytest.mark.parametrize(
    "field,value,rule",
    [
        ("attrs", {"x": float("nan")}, "expected finite JSON data, got float = nan"),
        ("disabled", "off", "expected bool, got 'off'"),
        ("capacity", float("nan"), "expected a finite nonnegative amount, got nan"),
        ("cost", float("nan"), "expected an integer, got nan"),
    ],
)
def test_declared_properties_are_checked_even_if_they_create_no_objects(
    section, field, value, rule
):
    if section == "node_rules" and field in ("capacity", "cost"):
        return
    entry = (
        {"path": "Z"}
        if section == "node_rules"
        else {"source": "A", "target": "A" if section == "links" else "Z"}
    )
    entry[field] = value
    data = {"network": {"nodes": {"A": {}}, section: [entry]}}
    with pytest.raises(ValueError) as error:
        load(data)
    message = str(error.value)
    assert f"network.{section}[0]" in message and f".{field}" in message
    if not isinstance(error.value.__cause__, jsonschema.ValidationError):
        assert message.endswith(rule)
    entry[field] = {"x": 1} if field == "attrs" else False if field == "disabled" else 1
    assert load(data)


def test_network_metadata_is_checked_when_assembled():
    with pytest.raises(ValueError) as error:
        load({"network": {"version": float("nan")}})
    assert (
        str(error.value)
        == "network.version: expected finite JSON data, got float = nan"
    )
    assert load({"network": {"version": 3}}).network.attrs == {"version": 3}


@pytest.mark.parametrize(
    "field,value,expected",
    [
        (
            "offer",
            float("inf"),
            "workflow[1] (name 'bad').offer = inf: expected a finite nonnegative amount, got inf",
        ),
        (
            "source",
            "[",
            "workflow[1] (name 'bad').source.path = '[': invalid pattern '[': unterminated character set at position 0",
        ),
    ],
)
def test_workflow_constructor_refusal_has_position_name_field_and_raw_value(
    field, value, expected
):
    data = {
        "workflow": [
            {"type": "BuildGraph"},
            {
                "type": "MaxFlow",
                "name": "bad",
                "source": "A",
                "target": "T",
                field: value,
            },
        ]
    }
    with pytest.raises(ValueError) as error:
        load(data)
    assert str(error.value) == expected
    data["workflow"][1][field] = 1 if field == "offer" else "A"
    assert load(data)


def test_link_patterns_and_empty_endpoints_have_positions_and_raw_values():
    data = {
        "network": {
            "nodes": {"A": {}, "T": {}},
            "links": [{"source": "A", "target": "T"}] * 3
            + [{"source": "A", "target": "Z"}],
        }
    }
    with pytest.raises(ValueError) as error:
        load(data)
    assert (
        str(error.value)
        == "network.links[3] (A->Z): link 'A' -> 'Z': target 'Z' matches no node"
    )
    data["network"]["links"][3] = {"source": "[", "target": "T"}
    with pytest.raises(ValueError) as error:
        load(data)
    assert (
        str(error.value)
        == "network.links[3] ([->T).source.path: invalid pattern '[': unterminated character set at position 0"
    )
    data["network"]["links"][3] = {"source": "A", "target": "T"}
    assert len(load(data).network.links) == 4


@pytest.mark.parametrize(
    "text,path,value,reason",
    [
        (
            "network: {nodes: {A: {}, T: {}}, links: [{source: A, target: T, cost: 0}]}",
            "network.links[0] (A->T).cost",
            0,
            "0 is less than the minimum of 1",
        ),
        ("seed: true", "seed", True, "True is not of type 'integer', 'null'"),
    ],
)
def test_all_schema_load_refusals_are_value_errors_with_original_cause(
    text, path, value, reason
):
    for loader in (load_scenario_yaml, Scenario.from_yaml):
        with pytest.raises(ValueError) as error:
            loader(text)
        assert type(error.value) is ValueError
        assert str(error.value) == f"{path} = {value!r}: {reason}"
        cause = error.value.__cause__
        assert isinstance(cause, jsonschema.ValidationError)
        assert cause.instance == value and cause.message == reason
    assert Scenario.from_yaml("seed: 2")


@pytest.mark.parametrize("shared", [False, True])
def test_generate_refusal_names_its_list_position_and_raw_pattern(shared):
    data = {
        "risk_groups": [
            {"name": "existing"},
            {
                "generate": {
                    "scope": "node",
                    "group_by": "role",
                    "name": "rg-${value}",
                    "path": "[",
                }
            },
        ]
    }
    if shared:
        data["risk_groups"].append({"generate": data["risk_groups"][1]["generate"]})
    with pytest.raises(ValueError) as error:
        load(data)
    assert (
        str(error.value)
        == "risk_groups[1].generate.path: invalid pattern '[': unterminated character set at position 0"
    )
    data["risk_groups"][1]["generate"]["path"] = ".*"
    assert load(data)
