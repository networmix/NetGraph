"""Discover optional constructor fields; require a YAML binding or an explicit boundary."""

import ast
import copy
import dataclasses
import importlib
import inspect
import json
import re
import signal
from importlib import resources
from types import NoneType
from typing import get_args

import jsonschema
import netgraph_core as core
import pytest
import yaml

from ngraph import Scenario
from ngraph.model.risk import GenerateSpec, MembershipSpec
from ngraph.workflow import WorkflowStep
from tests.dsl.test_input_parity import BASE

MODULES = [
    importlib.import_module(n)
    for n in ("ngraph", "ngraph.workflow", "ngraph.hardware", "ngraph.logging")
]
SCHEMA = json.loads(
    resources.files("ngraph.schemas").joinpath("scenario.json").read_text()
)
VALIDATOR = jsonschema.validators.validator_for(SCHEMA)(SCHEMA)
NATIVE = {
    "ShortestPaths": core.ShortestPaths,
    "DistributedTE": core.DistributedTE,
    "CentralizedTE": core.CentralizedTE,
}


def admits_none(annotation):
    if annotation is None or annotation is NoneType or NoneType in get_args(annotation):
        return True
    if not isinstance(annotation, str):
        return False

    def optional(node):
        if isinstance(node, ast.Constant):
            return node.value is None
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return optional(node.left) or optional(node.right)
        if isinstance(node, ast.Subscript):
            return isinstance(node.value, ast.Name) and node.value.id == "Optional"
        return False

    return optional(ast.parse(annotation, mode="eval").body)


def inventory():
    classes = {
        getattr(m, name)
        for m in MODULES
        for name in m.__all__
        if isinstance(getattr(m, name), type)
    }
    classes.update((GenerateSpec, MembershipSpec))
    found = []
    for cls in sorted(classes, key=lambda c: (c.__module__, c.__name__)):
        if dataclasses.is_dataclass(cls):
            fields = [f for f in dataclasses.fields(cls) if f.init]
        elif cls.__module__.startswith("ngraph"):
            try:
                fields = list(inspect.signature(cls).parameters.values())
            except (TypeError, ValueError):
                continue
        else:
            continue
        for field in fields:
            annotation = (
                field.type if isinstance(field, dataclasses.Field) else field.annotation
            )
            default = field.default
            if admits_none(annotation) or default is None:
                found.append((cls, field.name))
    for cls in NATIVE.values():
        # pybind exposes this signature in the first doc line, not inspect.signature.
        signature = cls.__init__.__doc__.splitlines()[0]
        for name in re.findall(r"(\w+):[^,()]*? = None", signature):
            found.append((cls, name))
    return found


def boundary(cls, field):
    if field.startswith("_") or field in (
        "yaml_label",
        "declaration_ordinal",
        "expand_leaf_index",
        "derived_seed",
    ):
        return "Loader provenance/internal state has no YAML declaration key."
    if cls.__module__ == "ngraph.results" or cls.__module__ == "ngraph.hardware":
        return "Produced result/inventory field, not a YAML input declaration."
    if cls.__name__.endswith("Query") or cls.__name__ in (
        "FailureRequest",
        "PreparedScenario",
        "StepNeeds",
    ):
        return "Runtime question/preparation record; no YAML constructor or direct field spelling."
    if cls is WorkflowStep:
        return (
            "Abstract workflow base; seed is exercised on each concrete exported step."
        )
    if cls.__name__ == "FailurePolicy" and field == "seed":
        return (
            "Policy seed is derived from scenario seed; a YAML policy has no seed key."
        )
    if cls.__name__ == "TunnelCountAnalysis" and field in ("offer", "design_demand"):
        return (
            "Annotation admits None, but construction expressly requires a real value."
        )
    if cls.__name__ == "CentralizedTE" and field in ("source_weights", "support"):
        return "Graph-bound Core inputs not exposed by the closed YAML model schema."
    return None


def binding(cls, field):
    """Bind a constructor family; field selection comes only from inventory()."""
    name = cls.__name__
    data = copy.deepcopy(BASE)
    python = None
    if issubclass(cls, WorkflowStep):
        entry = next((v for v in data["workflow"] if v["type"] == name), None)
        if entry is None:
            entry = {
                "type": name,
                "name": "tca",
                "demand_set": "d",
                "counts": [1],
                "offer": 1,
                "design_demand": 1,
            }
            data["workflow"].append(entry)
        index = data["workflow"].index(entry)
        path = ["workflow", index, field]

        def read(s):
            return s.workflow[index]
    elif name == "Scenario":
        data = {}
        path = [field]

        def read(s):
            return getattr(s, field)
    elif name == "NetworkExplorer":
        data = {}
        path = ["components"]

        def read(s):
            return dict(s.components_library.components)

        from ngraph import Network

        def python():
            return cls(Network(), **{field: None})
    elif name == "DemandSpec":
        path = ["demands", "d", 0, field]

        def read(s):
            return s.demand_sets["d"].demands[0]
    elif name == "FailureRule":
        path = ["failures", "fp", "modes", 0, "rules", 0, field]

        def read(s):
            return s.failure_policies["fp"].modes[0].rules[0]
    elif name == "Selector":
        path = ["demands", "d", 0, "source", field]

        def read(s):
            return s.demand_sets["d"].demands[0].source
    elif name == "Condition":
        data["demands"]["d"][0]["source"]["match"] = {
            "conditions": [{"attr": "role", "op": "exists"}]
        }
        path = ["demands", "d", 0, "source", "match", "conditions", 0, field]

        def read(s):
            return s.demand_sets["d"].demands[0].source.match.conditions[0]
    elif name == "RouteSpec":
        if field == "nodes":
            data["routes"]["r"] = {
                "head": "A",
                "edges": [{"link": "A|T|0", "direction": "forward"}],
            }
        path = ["routes", "r", field]

        def read(s):
            return s.routes["r"]
    elif name == "PinnedRoutes":
        data["workflow"][3]["model"] = {"routing": {"type": "pinned", "routes": ["r"]}}
        path = ["workflow", 3, "model", "routing", field]

        def read(s):
            return s.workflow[3].model
    elif name == "GroupChild":
        child = {"edge": {"link": "A|T|0", "direction": "forward"}}
        if field == "edge":
            child = {"children": [child]}
        data.update(
            routing={"igp_domain": ".*", "bgp_edge": ".*"},
            wcmp_controller={},
            forwarding_groups={"f": {"router": "A", "groups": [{"children": [child]}]}},
        )
        path = ["forwarding_groups", "f", "groups", 0, "children", 0, field]

        def read(s):
            return s.forwarding_groups["f"].groups[0].children[0]
    elif name in ("GenerateSpec", "MembershipSpec"):
        if name == "GenerateSpec":
            raw = {"scope": "node", "group_by": "role", "name": "rg-${value}"}
            key = "generate"

            def python():
                return cls(**dict(raw, **{field: None}))
        else:
            raw = {
                "scope": "node",
                "path": ".*",
                "match": {"conditions": [{"attr": "role", "op": "exists"}]},
            }
            key = "membership"
            from ngraph import Condition, MatchSpec

            def python():
                return cls(
                    "node",
                    **{
                        "path": ".*",
                        "match": MatchSpec((Condition("role", "exists"),)),
                        field: None,
                    },
                )

        data["risk_groups"] = (
            [dict(name="R", **{key: raw})] if key == "membership" else [{key: raw}]
        )
        path = ["risk_groups", 0, key, field]

        def read(s):
            return s
    else:
        raise AssertionError(
            f"Unbound nullable public field: {cls.__module__}.{name}.{field}"
        )
    return data, path, read, python


def frozen(value):
    if dataclasses.is_dataclass(value):
        return type(value), tuple(
            (f.name, frozen(getattr(value, f.name)))
            for f in dataclasses.fields(value)
            if not f.name.startswith("_")
        )
    if isinstance(value, dict):
        return tuple((k, frozen(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return tuple(map(frozen, value))
    if hasattr(type(value), "__members__"):
        return type(value), value.name
    if type(value).__module__ == "_netgraph_core":
        return type(value), tuple(
            (name, frozen(getattr(value, name)))
            for name, descriptor in vars(type(value)).items()
            if isinstance(descriptor, property)
        )
    return value


def variants(data, path):
    explicit = copy.deepcopy(data)
    node = explicit
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = None
    omitted = copy.deepcopy(explicit)
    node = omitted
    for part in path[:-1]:
        node = node[part]
    del node[path[-1]]
    return explicit, omitted


INVENTORY = inventory()


@pytest.fixture(autouse=True)
def bounded_case():
    previous = signal.signal(
        signal.SIGALRM, lambda *a: pytest.fail("optional field exceeded 4 seconds")
    )
    signal.alarm(4)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


@pytest.mark.parametrize(
    "cls,field", INVENTORY, ids=[f"{c.__name__}.{f}" for c, f in INVENTORY]
)
def test_every_discovered_optional_public_field_has_null_parity_or_a_named_boundary(
    cls, field
):
    reason = boundary(cls, field)
    if reason:
        assert reason and len(reason) > 20
        if cls.__name__ == "TunnelCountAnalysis" and field in (
            "offer",
            "design_demand",
        ):
            with pytest.raises(ValueError, match=field + ": required"):
                cls(
                    demand_set="d",
                    counts=(1,),
                    offer=1 if field != "offer" else None,
                    design_demand=1 if field != "design_demand" else None,
                )
        return
    if cls.__name__ in NATIVE:
        # These are checked in both YAML consumers, below, from the same discovery.
        return
    data, path, read, python = binding(cls, field)
    explicit, omitted = variants(data, path)
    VALIDATOR.validate(explicit)
    VALIDATOR.validate(omitted)
    left, right = (
        Scenario.from_yaml(yaml.safe_dump(d, sort_keys=False))
        for d in (explicit, omitted)
    )
    assert frozen(read(left)) == frozen(read(right)), (cls.__name__, field, path)
    if python:
        python()
    elif cls.__name__ == "Scenario":
        dataclasses.replace(right, **{field: None})
    else:
        dataclasses.replace(read(right), **{field: None})


NATIVE_FIELDS = [
    (c, f) for c, f in INVENTORY if c.__name__ in NATIVE and boundary(c, f) is None
]


@pytest.mark.parametrize(
    "cls,field", NATIVE_FIELDS, ids=[f"{c.__name__}.{f}" for c, f in NATIVE_FIELDS]
)
@pytest.mark.parametrize("owner", ["demand", "MaxFlow"])
def test_every_discovered_native_optional_model_field_agrees_in_every_yaml_consumer(
    cls, field, owner
):
    routing = {
        "type": {
            "ShortestPaths": "shortest_paths",
            "DistributedTE": "distributed_te",
            "CentralizedTE": "centralized_te",
        }[cls.__name__]
    }
    kwargs = {}
    args = ()
    if cls is core.DistributedTE:
        routing["tunnel_count"] = {"per_head": 1}
        args = (core.TunnelCount(1),)
    if cls is core.CentralizedTE:
        routing["source_allocation"] = "equal"
        kwargs["source_allocation"] = core.SourceAllocation.EQUAL
    assert frozen(cls(*args, **dict(kwargs, **{field: None}))) == frozen(
        cls(*args, **kwargs)
    )
    data = copy.deepcopy(BASE)
    if owner == "demand":
        data["demands"]["d"][0]["model"] = {"routing": routing}
        path = ["demands", "d", 0, "model", "routing", field]

        def read(s):
            return s.demand_sets["d"].demands[0].policy
    else:
        data["workflow"][3]["model"] = {"routing": routing}
        path = ["workflow", 3, "model", "routing", field]

        def read(s):
            return s.workflow[3].model

    explicit, omitted = variants(data, path)
    VALIDATOR.validate(explicit)
    VALIDATOR.validate(omitted)
    left, right = (
        Scenario.from_yaml(yaml.safe_dump(d, sort_keys=False))
        for d in (explicit, omitted)
    )
    assert frozen(read(left)) == frozen(read(right))
