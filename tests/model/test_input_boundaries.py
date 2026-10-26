"""Raw declarations obey the constructor rules on every loading path."""

import json
import signal
from fractions import Fraction

import netgraph_core as ngc
import numpy as np
import pytest
import yaml

from ngraph import (
    Component,
    ComponentsLibrary,
    Condition,
    ControllerGroup,
    DemandSet,
    DemandSpec,
    DirectedLink,
    EdgeWeight,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    ForwardingGroup,
    GroupChild,
    Link,
    MatchSpec,
    Network,
    NetworkExplorer,
    Node,
    PinnedRoutes,
    RiskGroup,
    RouteSpec,
    RoutingDomain,
    Scenario,
    Selector,
    SupportSpec,
    UnitsSettings,
    WeightSpec,
    prepare,
    run,
)
from ngraph.analysis.capacity import CapacityQuery
from ngraph.analysis.counts import TunnelCountQuery
from ngraph.analysis.msd import MSDQuery
from ngraph.analysis.paths import PathQuery
from ngraph.analysis.placement import PlacementQuery
from ngraph.analysis.sensitivity import SensitivityQuery
from ngraph.model.risk import GenerateSpec, MembershipSpec
from ngraph.results import ResolvedDemandSet
from ngraph.utils.values import json_copy
from ngraph.workflow.base import step_type

LOADERS = ("dict", "yaml", "nested_dict", "nested_yaml", "scenario", "nested_scenario")


def component_load(loader, fields):
    nested = loader.startswith("nested")
    data = {"rack": {"children": {"card": fields}}} if nested else {"card": fields}
    if "scenario" in loader:
        library = Scenario.from_yaml(
            yaml.safe_dump({"components": data})
        ).components_library
    elif "yaml" in loader:
        library = ComponentsLibrary.from_yaml(yaml.safe_dump(data))
    else:
        library = ComponentsLibrary.from_dict(data)
    return (
        library.components["rack"].children["card"]
        if nested
        else library.components["card"]
    )


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize(
    "field,bad,good",
    [
        *(
            (field, bad, 3.0)
            for field in ("capex", "power_watts", "power_watts_max", "capacity")
            for bad in (True, "3", None, -1, float("nan"), float("inf"))
        ),
        *(
            (field, bad, 3.0)
            for field in ("ports", "count")
            for bad in (True, "3", None, -1, 3.5, float("nan"), float("inf"))
        ),
        ("count", 0, 1),
        ("component_type", b"card", "card"),
        ("description", b"text", "text"),
    ],
)
def test_component_loaders_keep_raw_values_until_the_constructor(
    loader, field, bad, good
):
    with pytest.raises(ValueError) as direct:
        Component("card", **{field: bad})
    with pytest.raises(ValueError) as loaded:
        component_load(loader, {field: bad})
    location = (
        "components.rack.children.card"
        if loader.startswith("nested")
        else "components.card"
    )
    message = str(loaded.value)
    if loaded.value.__cause__ is not None and hasattr(
        loaded.value.__cause__, "validator"
    ):
        assert (
            message == f"{location}.{field} = {bad!r}: {loaded.value.__cause__.message}"
        )
    else:
        assert message == str(direct.value).replace("component card", location, 1)
    expected = getattr(Component("card", **{field: good}), field)
    result = getattr(component_load(loader, {field: good}), field)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize("op", ["in", "not_in"])
@pytest.mark.parametrize("bad", [3, "abc", None, {"a": 1}, (1, 2)])
def test_membership_operands_are_lists_at_construction(op, bad):
    with pytest.raises(ValueError) as error:
        Condition("role", op, bad)
    assert (
        str(error.value) == f"condition role.value: {op!r} requires a list, got {bad!r}"
    )
    assert Condition("role", op, ["edge"]).value == ["edge"]


@pytest.mark.parametrize(
    "value,expected",
    [
        (np.bool_(True), True),
        (np.int64(-2), -2),
        (np.uint64(2**63), 2**63),
        (np.float32(1.5), 1.5),
        (np.float64(2.5), 2.5),
        (np.str_("x"), "x"),
    ],
)
def test_json_numpy_scalars_are_builtin_on_all_paths(value, expected):
    for obj in (
        Node("n", attrs={"nested": [value]}),
        Component("c", attrs={"nested": [value]}),
        Network(attrs={"nested": [value]}),
    ):
        stored = obj.attrs["nested"][0]
        assert stored == expected and type(stored) is type(expected)
        assert json.loads(json.dumps(obj.attrs)) == {"nested": [expected]}
    stored = Condition("x", "==", value).value
    assert stored == expected and type(stored) is type(expected)
    stored = json_copy({np.str_("x"): [value]})
    assert type(next(iter(stored))) is str
    assert stored["x"][0] == expected and type(stored["x"][0]) is type(expected)


@pytest.mark.parametrize(
    "value", [np.float32("nan"), np.float32("inf"), np.float64("-inf")]
)
def test_json_numpy_nonfinite_is_refused(value):
    for build in (
        lambda: Node("n", attrs={"x": value}),
        lambda: Condition("x", "==", value),
        lambda: json_copy(value),
    ):
        with pytest.raises(ValueError, match="expected finite JSON data"):
            build()


@pytest.mark.parametrize("value", ["false", "off", 0, 1, None])
@pytest.mark.parametrize("group", ["single", "counted", "nested", "blueprint"])
def test_blueprint_disabled_overrides_are_flags_even_under_a_disabled_parent(
    value, group
):
    definitions = {
        "single": {},
        "counted": {"count": 2},
        "nested": {"nodes": {"child": {}}},
        "blueprint": {"blueprint": "inner"},
    }
    data = {
        "blueprints": {
            "b": {"nodes": {"srv": definitions[group]}},
            "inner": {"nodes": {"child": {}}},
        },
        "network": {
            "nodes": {
                "p": {
                    "blueprint": "b",
                    "disabled": True,
                    "params": {"srv.disabled": value},
                }
            }
        },
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value)
        == f"network.nodes.p.params.srv.disabled: expected bool, got {value!r}"
    )
    for valid in (False, True):
        data["network"]["nodes"]["p"]["params"]["srv.disabled"] = valid
        nodes = Scenario.from_yaml(yaml.safe_dump(data)).network.nodes
        assert nodes and all(node.disabled is True for node in nodes.values())


def test_parameter_template_is_text_and_attrs_disabled_is_json():
    data = {
        "blueprints": {"b": {"nodes": {"srv": {"count": 1}}}},
        "network": {"nodes": {"p": {"blueprint": "b", "params": {"srv.template": 5}}}},
    }
    with pytest.raises(ValueError) as error:
        Scenario.from_yaml(yaml.safe_dump(data))
    assert (
        str(error.value) == "network.nodes.p.params.srv.template: expected text, got 5"
    )
    data["network"]["nodes"]["p"]["params"] = {
        "srv.template": "s-{n}",
        "srv.attrs.disabled": "off",
    }
    assert (
        Scenario.from_yaml(yaml.safe_dump(data))
        .network.nodes["p/srv/s-1"]
        .attrs["disabled"]
        == "off"
    )


@pytest.mark.parametrize("value", ["false", 0, None, b"yes"])
def test_explorer_checks_flag_and_types(value):
    with pytest.raises(ValueError) as error:
        NetworkExplorer(Network(), strict_validation=value)
    assert (
        str(error.value)
        == f"NetworkExplorer.strict_validation: expected bool, got {value!r}"
    )
    assert (
        NetworkExplorer(Network(), strict_validation=np.bool_(False)).strict_validation
        is False
    )
    for field in ("network", "components_library"):
        with pytest.raises(TypeError) as error:
            NetworkExplorer(**{**{"network": Network()}, field: 1})
        suffix = "Network" if field == "network" else "ComponentsLibrary or None"
        assert str(error.value) == f"NetworkExplorer.{field}: expected {suffix}, got 1"
    assert isinstance(
        NetworkExplorer(Network(), None).components_library, ComponentsLibrary
    )


@pytest.mark.parametrize("kind", [GenerateSpec, MembershipSpec])
def test_public_risk_specs_check_patterns_and_text(kind):
    args = (
        {"scope": "node", "group_by": "role", "name": "rg-${value}"}
        if kind is GenerateSpec
        else {"scope": "node"}
    )
    prefix = "generate" if kind is GenerateSpec else "membership"
    with pytest.raises(ValueError) as error:
        kind(**args, path="[")
    assert (
        str(error.value)
        == f"{prefix}.path: invalid pattern '[': unterminated character set at position 0"
    )
    assert kind(**args, path=np.str_(".*")).path == ".*"
    with pytest.raises(ValueError) as error:
        kind(**{**args, "scope": "bogus"})
    assert f"{prefix}.scope:" in str(error.value) and "'bogus'" in str(error.value)
    if kind is GenerateSpec:
        for field in ("group_by", "name"):
            with pytest.raises(ValueError) as error:
                kind(**{**args, field: b"x"})
            assert str(error.value) == f"generate.{field}: expected text, got b'x'"
        with pytest.raises(ValueError) as error:
            kind(**{**args, "name": "constant"})
        assert (
            str(error.value) == "generate.name: must contain '${value}', got 'constant'"
        )


COLLECTIONS = [
    (lambda v: Node("n", risk_groups=v), "node n.risk_groups"),
    (lambda v: Link("s", "t", risk_groups=v), "link s->t.risk_groups"),
    (lambda v: RiskGroup("r", children=v), "risk group r.children"),
    (lambda v: MatchSpec(conditions=v), "match.conditions"),
    (lambda v: FailureRule("node", conditions=v), "failure rule conditions"),
    (lambda v: FailureMode(1, rules=v), "failure mode rules"),
    (lambda v: FailurePolicy(modes=v), "failure policy modes"),
    (lambda v: DemandSet("d", v), "demand set d.demands"),
    (lambda v: WeightSpec(v), "weights.entries"),
    (lambda v: SupportSpec(v), "support.edges"),
    (lambda v: RouteSpec("s", nodes=v), "route.nodes"),
    (lambda v: RouteSpec("s", edges=v), "route.edges"),
    (lambda v: PinnedRoutes(v), "pinned.routes"),
    (lambda v: ControllerGroup(v), "controller_group.children"),
    (lambda v: GroupChild(children=v), "group_child.children"),
    (lambda v: ForwardingGroup("s", v), "forwarding_group.groups"),
    (lambda v: Scenario(Network(), workflow=v), "Scenario.workflow"),
    (
        lambda v: step_type("NetworkStats")(excluded_nodes=v),
        "NetworkStats.excluded_nodes",
    ),
    (
        lambda v: step_type("NetworkStats")(excluded_links=v),
        "NetworkStats.excluded_links",
    ),
]


@pytest.mark.parametrize("build,label", COLLECTIONS)
@pytest.mark.parametrize("value", [1, None])
def test_collection_type_refusals_name_the_field_and_raw_value(build, label, value):
    if value is None and label in (
        "route.nodes",
        "route.edges",
        "group_child.children",
    ):
        with pytest.raises(ValueError) as error:
            build(value)
        expected = (
            "route: specify exactly one of nodes, edges or support"
            if label.startswith("route")
            else "group_child: expected exactly one of edge and children"
        )
        assert str(error.value) == expected
        return
    with pytest.raises(TypeError) as error:
        build(value)
    assert str(error.value) == f"{label}: expected a collection, got {value!r}"


def test_support_nonempty_children_iterators_and_exact_integral_shares():
    with pytest.raises(ValueError) as error:
        SupportSpec(())
    assert str(error.value) == "support.edges: expected at least one edge, got ()"
    edge = DirectedLink("s|t|0", "forward")
    assert SupportSpec((edge,)).edges == (edge,)
    for share in (2, 2.0, np.float32(2), np.int64(2)):
        child = GroupChild(share, edge)
        assert child.share == Fraction(2) and type(child.share) is Fraction
        assert ControllerGroup((c for c in [child]), share).children == (child,)
    for share in (1.5, True):
        with pytest.raises(ValueError):
            GroupChild(share, edge)


@pytest.mark.parametrize(
    "key,name,message",
    [
        ("", "c", "components key: expected a nonempty name, got ''"),
        ("x", "y", "components.x: name/key disagreement, got 'y'"),
    ],
)
def test_component_library_identity(key, name, message):
    with pytest.raises(ValueError) as error:
        ComponentsLibrary({key: Component(name)})
    assert str(error.value) == message
    assert ComponentsLibrary({name: Component(name)}).get(name).name == name


def test_range_refusals_include_raw_values():
    with pytest.raises(ValueError) as error:
        UnitsSettings(3)
    assert (
        str(error.value)
        == "units.resolution: expected a power of two from 2^-32 through 2^32, got 3"
    )
    demands = ResolvedDemandSet("d", (), (), ())
    with pytest.raises(ValueError) as error:
        MSDQuery(demands, growth_factor=1)
    assert str(error.value) == "msd.growth_factor: must exceed 1, got 1"
    with pytest.raises(ValueError) as error:
        MSDQuery(demands, alpha_min=2)
    assert (
        str(error.value)
        == "msd: require alpha_min <= alpha_start <= alpha_max, got (2, 1.0, 1000000000.0)"
    )
    assert MSDQuery(demands, growth_factor=2).growth_factor == 2.0
    with pytest.raises(TypeError) as error:
        Network(nodes={"A": 1})
    assert (
        str(error.value)
        == "network.nodes: expected a mapping of names to Node values, got {'A': 1}"
    )


def test_recorded_discriminants_are_checked_at_construction():
    with pytest.raises(ValueError) as error:
        FailureRequest(None, seed_source="policy")
    assert (
        str(error.value)
        == "failure seed_source: expected query, step or scenario, got 'policy'"
    )
    assert FailureRequest(None, seed_source="scenario").seed_source == "scenario"
    with pytest.raises(ValueError) as error:
        DirectedLink("l", "backward")
    assert (
        str(error.value)
        == "link l: direction must be forward or reverse, got 'backward'"
    )
    assert DirectedLink("l", "reverse").direction == "reverse"
    with pytest.raises(ValueError) as error:
        step_type("TrafficMatrixPlacement")(demand_set="d", alpha_from_step="")
    assert (
        str(error.value)
        == "TrafficMatrixPlacement.alpha_from_step: expected a nonempty name, got ''"
    )
    assert (
        step_type("TrafficMatrixPlacement")(
            demand_set="d", alpha_from_step="msd"
        ).alpha_from_step
        == "msd"
    )


def test_empty_network_cost_bounds_are_integers():
    result = run(
        prepare(Scenario(Network(), (step_type("NetworkStats")(name="stats"),)))
    )
    stats = result.steps[0].result
    assert stats.min_cost == stats.max_cost == 0
    assert type(stats.min_cost) is type(stats.max_cost) is int


def test_cost_levels_end_at_deepest_node_name(monkeypatch):
    import ngraph.workflow.cost_power as module

    constructed = []
    original_row = module.HardwareRow

    def record_row(*args):
        constructed.append(args)
        return original_row(*args)

    monkeypatch.setattr(module, "HardwareRow", record_row)
    network = Network(
        nodes={"dc/rack/s": Node("dc/rack/s", attrs={"hardware": {"component": "c"}})}
    )
    library = ComponentsLibrary({"c": Component("c", capex=7, power_watts=2)})

    def fail_timeout(signum, frame):
        raise AssertionError("aggregation exceeded the node-name depth")

    previous = signal.signal(signal.SIGALRM, fail_timeout)
    try:
        signal.alarm(3)
        result = run(
            prepare(
                Scenario(
                    network,
                    (step_type("CostPower")(name="cost", aggregation_level=2**62),),
                    components_library=library,
                )
            )
        )
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    cost = result.steps[0].result
    assert cost.aggregation_level == 2**62
    assert len(cost.levels) == 2**62 + 1
    assert len(constructed) == 4
    assert cost.levels[2**62] is cost.levels[3]
    for level, path in enumerate(("", "dc", "dc/rack", "dc/rack/s")):
        rows = cost.levels[level]
        assert len(rows) == 1 and rows[0].path == path
        assert rows[0].capex_total == 7 and rows[0].power_total_watts == 2


def test_other_public_input_constructors_use_the_same_kind_rules():
    from ngraph.dsl.expansion import ExpansionSpec
    from ngraph.utils.seed_manager import SeedManager

    for bad in (True, 1.5, "3", b"3"):
        with pytest.raises(ValueError) as error:
            SeedManager(bad)
        assert (
            str(error.value)
            == f"SeedManager.master_seed: expected an integer, got {bad!r}"
        )
    assert SeedManager(np.int64(3)).master_seed == 3
    assert type(SeedManager(3.0).master_seed) is int
    assert SeedManager(None).derive_seed("a") is None
    for bad in ("bad", 1, b"zip"):
        with pytest.raises(ValueError) as error:
            ExpansionSpec(mode=bad)
        assert "expand.mode:" in str(error.value) and repr(bad) in str(error.value)
    with pytest.raises(ValueError) as error:
        ExpansionSpec(vars={"v": 1})
    assert str(error.value) == "expand.vars.v: expected a list, got 1"
    spec = ExpansionSpec(vars={"v": [np.int64(3)]}, mode=np.str_("zip"))
    assert spec.vars == {"v": [3]} and type(spec.vars["v"][0]) is int
    assert type(spec.mode) is str


@pytest.mark.parametrize("end", ["node", "link"])
@pytest.mark.parametrize("bad", ["false", 0])
def test_rule_updates_apply_the_flag_rule_without_schema(end, bad):
    from ngraph.dsl.blueprints.expand import _update_links, _update_nodes

    network = Network(nodes={name: Node(name) for name in ("s", "t")})
    network.add_link(Link("s", "t"))
    with pytest.raises(ValueError) as error:
        if end == "node":
            _update_nodes(network, "s", None, {}, disabled_val=bad)
        else:
            _update_links(network, "s", "t", {"disabled": bad})
    assert str(error.value) == f"{end} rule.disabled: expected bool, got {bad!r}"
    assert not network.nodes["s"].disabled and not network.links["s|t|0"].disabled
    if end == "node":
        _update_nodes(network, "s", None, {}, disabled_val=True)
        assert network.nodes["s"].disabled is True
    else:
        _update_links(network, "s", "t", {"disabled": True})
        assert network.links["s|t|0"].disabled is True


def test_validated_inputs_are_not_checked_again_in_consumers(monkeypatch):
    import importlib

    module = importlib.import_module("ngraph.analysis.capacity")
    original = module.physical
    calls = []

    def counted(value, label, **kwargs):
        calls.append(label)
        return original(value, label, **kwargs)

    monkeypatch.setattr(module, "physical", counted)
    module.CapacityQuery(
        Selector("s"),
        Selector("t"),
        ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
        offer=2,
        design_demand=3,
    )
    assert calls == ["capacity.offer", "capacity.design_demand"]
    failures = importlib.import_module("ngraph.analysis.failures")

    def unexpected(*args, **kwargs):
        raise AssertionError("a validated field was checked again")

    monkeypatch.setattr(failures, "integer", unexpected)
    assert failures.resolve_workers(2) == 2
    assert failures.resolve_workers("auto") >= 1
    topology = importlib.import_module("ngraph.analysis.topology")
    monkeypatch.setattr(topology, "physical", unexpected, raising=False)
    network = Network(nodes={n: Node(n) for n in ("s", "t")})
    network.add_link(Link("s", "t"))
    assert topology.compile_topology(network, 1).graph.num_edges() == 2


def test_parent_flag_is_checked_before_inheritance():
    from ngraph.dsl.blueprints.expand import (
        _merge_parent_into_child,
        _parent_merge_context,
    )

    with pytest.raises(ValueError) as error:
        _parent_merge_context({"disabled": "off"}, "network.nodes.g", {}, set())
    assert str(error.value) == "network.nodes.g.disabled: expected bool, got 'off'"
    with pytest.raises(ValueError) as error:
        _merge_parent_into_child(
            {"disabled": "off"}, "network.nodes.g", {}, {}, True, set()
        )
    assert str(error.value) == "network.nodes.g.disabled: expected bool, got 'off'"
    assert (
        _parent_merge_context({"disabled": False}, "network.nodes.g", {}, set())[2]
        is False
    )


@pytest.mark.parametrize("bad", ["one", b"one", {"one": 1}])
def test_collection_refusals_keep_the_field_for_scalar_and_mapping_inputs(bad):
    with pytest.raises(TypeError) as error:
        Node("n", risk_groups=bad)
    assert str(error.value) == f"node n.risk_groups: expected a collection, got {bad!r}"
    assert Node("n", risk_groups=["one"]).risk_groups == frozenset({"one"})


@pytest.mark.parametrize(
    "build,message",
    [
        (
            lambda: FailureRule("node", conditions=[1]),
            "failure rule conditions: expected Condition values, got [1]",
        ),
        (
            lambda: FailureMode(1, rules=[1]),
            "failure mode rules: expected FailureRule values, got [1]",
        ),
        (
            lambda: FailurePolicy(modes=[1]),
            "failure policy modes: expected FailureMode values, got [1]",
        ),
        (
            lambda: RiskGroup("r", children=[1]),
            "risk group r.children: expected RiskGroup values, got [1]",
        ),
        (
            lambda: DemandSet("d", [1]),
            "demand set d.demands: expected DemandSpec values, got [1]",
        ),
        (
            lambda: SupportSpec([1]),
            "support.edges: expected DirectedLink values, got [1]",
        ),
        (
            lambda: WeightSpec([1]),
            "weights.entries: expected EdgeWeight values, got [1]",
        ),
        (
            lambda: RouteSpec("s", edges=[1]),
            "route.edges: expected DirectedLink values, got [1]",
        ),
        (
            lambda: ControllerGroup([1]),
            "controller_group.children: expected GroupChild values, got [1]",
        ),
        (
            lambda: ForwardingGroup("s", [1]),
            "forwarding_group.groups: expected ControllerGroup values, got [1]",
        ),
        (
            lambda: Scenario(Network(), workflow=[1]),
            "workflow[0] = 1: expected WorkflowStep values",
        ),
    ],
)
def test_record_collection_member_refusals_keep_the_value(build, message):
    with pytest.raises(TypeError) as error:
        build()
    assert str(error.value) == message


@pytest.mark.parametrize(
    "build,message",
    [
        (lambda: Scenario(1), "Scenario.network: expected Network, got 1"),
        (lambda: MSDQuery(1), "msd.demands: expected ResolvedDemandSet, got 1"),
        (
            lambda: step_type("MaxFlow")(model=1),
            "MaxFlow.model: expected a declared model or native FlowPolicyConfig, got 1",
        ),
    ],
)
def test_object_type_refusals_keep_the_raw_value(build, message):
    with pytest.raises(TypeError) as error:
        build()
    assert str(error.value) == message


@pytest.mark.parametrize(
    "kind,field,expected",
    [
        ("scenario", "units", "UnitsSettings"),
        ("scenario", "components_library", "ComponentsLibrary"),
        ("scenario", "routing", "RoutingDomain or None"),
        ("scenario", "wcmp_controller", "WCMPController or None"),
        ("tunnel_counts", "demands", "ResolvedDemandSet"),
        ("tunnel_counts", "counts", "a sequence of integers"),
        ("tunnel_counts", "eligibility", "native Eligibility"),
        ("tunnel_counts", "outputs", "native OutputOptions"),
        ("capacity", "config", "native FlowPolicyConfig"),
        ("capacity", "outputs", "native OutputOptions"),
        ("capacity", "failures", "FailureRequest"),
        ("paths", "options", "native SpfOptions or KspOptions"),
        ("placement", "demands", "ResolvedDemandSet"),
        ("placement", "failures", "FailureRequest"),
        ("placement", "outputs", "native OutputOptions"),
        ("sensitivity", "eligibility", "native Eligibility"),
        ("MaxFlow", "preset", "FlowPolicyPreset"),
        ("MaxFlow", "outputs", "native OutputOptions"),
        ("TrafficMatrixPlacement", "outputs", "native OutputOptions"),
    ],
)
def test_object_field_type_refusals_keep_the_raw_value(kind, field, expected):
    demands = ResolvedDemandSet("empty", (), (), ())
    factories = {
        "scenario": lambda **kw: Scenario(Network(), **kw),
        "tunnel_counts": lambda **kw: TunnelCountQuery(
            **(
                {"demands": demands, "counts": (1,), "design_demand": 1, "offer": 1}
                | kw
            )
        ),
        "capacity": lambda **kw: CapacityQuery(Selector("s"), Selector("t"), **kw),
        "paths": lambda **kw: PathQuery(Selector("s"), Selector("t"), **kw),
        "placement": lambda **kw: PlacementQuery(**({"demands": demands} | kw)),
        "sensitivity": lambda **kw: SensitivityQuery(
            Selector("s"),
            Selector("t"),
            CapacityQuery(Selector("s"), Selector("t")).config,
            **kw,
        ),
        "MaxFlow": step_type("MaxFlow"),
        "TrafficMatrixPlacement": step_type("TrafficMatrixPlacement"),
    }
    with pytest.raises(TypeError) as error:
        factories[kind](**{field: 1})
    label = "Scenario" if kind == "scenario" else kind
    assert str(error.value) == f"{label}.{field}: expected {expected}, got 1"


@pytest.mark.parametrize(
    "build,message",
    [
        (lambda: EdgeWeight(1, 1), "weight.edge: expected DirectedLink, got 1"),
        (lambda: GroupChild(edge=1), "group_child.edge: expected DirectedLink, got 1"),
        (
            lambda: FailureRequest(1),
            "failure policy: expected FailurePolicy or None, got 1",
        ),
        (
            lambda: Selector("s", match=1),
            "Selector 'match' must be MatchSpec or None, got 1",
        ),
        (
            lambda: DemandSpec(1, 2, 3),
            "demand endpoints require Selector values, got (1, 2)",
        ),
        (
            lambda: RoutingDomain(1, 2),
            "routing: expected Selector populations, got (1, 2)",
        ),
        (lambda: PathQuery(1, 2), "paths endpoints: expected Selectors, got (1, 2)"),
        (
            lambda: CapacityQuery(1, 2),
            "capacity endpoints: expected Selectors, got (1, 2)",
        ),
        (
            lambda: step_type("MaxFlow")(source=1, target=2),
            "MaxFlow endpoints: expected Selectors, got (1, 2)",
        ),
        (
            lambda: DemandSpec(Selector("s"), Selector("t"), 1, policy=1),
            "demand.policy: expected a native configuration, preset or declared routing model, got 1",
        ),
        (
            lambda: Scenario(Network(), demand_sets=1),
            "demand_sets: expected mapping, got 1",
        ),
        (
            lambda: Scenario(Network(), demand_sets={1: DemandSet("d", ())}),
            "demand_sets: expected nonempty string names, got 1",
        ),
        (
            lambda: Scenario(Network(), demand_sets={"d": 1}),
            "demand_sets.d: expected DemandSet, got 1",
        ),
    ],
)
def test_record_field_type_refusals_keep_the_raw_value(build, message):
    with pytest.raises((TypeError, ValueError)) as error:
        build()
    assert str(error.value) == message


@pytest.mark.parametrize("bad", [[], ()])
def test_empty_support_refusal_preserves_the_supplied_container(bad):
    with pytest.raises(ValueError) as error:
        SupportSpec(bad)
    assert str(error.value) == f"support.edges: expected at least one edge, got {bad!r}"
