"""Records are immutable from construction; prepare keeps read-only views of the rest.

Nothing a caller or a step does after ``prepare`` changes a prepared answer:
records cannot be edited at all, the caller's collections stay editable but
do not reach the prepared scenario, and a custom step's own data is its own.
"""

import copy
import dataclasses
import pickle
from dataclasses import FrozenInstanceError, dataclass, field, replace
from enum import Enum, IntEnum
from pathlib import Path
from types import MappingProxyType

import numpy as np
import pytest

from ngraph import (
    CapacityQuery,
    Condition,
    DemandSet,
    DemandSpec,
    DirectedLink,
    EdgeWeight,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    FlowPolicyPreset,
    Link,
    MatchSpec,
    Network,
    Node,
    PinnedRoutes,
    RiskGroup,
    RouteSpec,
    Scenario,
    Selector,
    StepOutput,
    SupportSpec,
    UnitsSettings,
    WeightSpec,
    WorkflowStep,
    capacity,
    prepare,
    run,
)
from ngraph.model.components import Component, ComponentsLibrary
from ngraph.utils.values import _FrozenDict, _FrozenList
from ngraph.workflow.build_graph import BuildGraph
from ngraph.workflow.cost_power import CostPower
from ngraph.workflow.max_flow_step import MaxFlow
from ngraph.workflow.maximum_supported_demand_step import MaximumSupportedDemand
from ngraph.workflow.network_stats import NetworkStats
from ngraph.workflow.traffic_matrix_placement_step import TrafficMatrixPlacement

READ_ONLY = "read-only: records are immutable"


class MutableFloat(float):
    """A float subclass whose own state can change after construction."""

    def __new__(cls, value):
        result = super().__new__(cls, value)
        result.current = value
        return result

    def __float__(self):
        return float(self.current)


class Text(str):
    def __str__(self):
        raise ValueError("do not convert text")


def selection(role):
    return Selector(match=MatchSpec([Condition("role", "==", role)]))


def source():
    """Two sources s1/2 and s2/7; the step selects s1 by an attribute condition."""
    network = Network(
        nodes={
            name: Node(
                name,
                risk_groups={"r"} if name == "s1" else (),
                attrs={"role": name, "nested": {"tags": [1]}},
            )
            for name in ("s1", "s2", "t")
        }
    )
    network.add_link(Link("s1", "t", 2, 1))
    network.add_link(Link("s2", "t", 7, 1))
    network.risk_groups["r"] = RiskGroup("r", attrs={"tags": [1]})
    step = MaxFlow(
        name="cap", source=selection("s1"), target=Selector("^t$"), workers=1
    )
    return Scenario(network, (step,), units=UnitsSettings(1))


def answer(prepared):
    row = run(prepared).steps[-1].result.cases[0].states["converged"].rows[0]
    return row.endpoints.sources, row.result.delivered


def records():
    condition = Condition("role", "==", "s1")
    rule = FailureRule("node", [condition])
    mode = FailureMode(1, [rule], {"cause": ["fiber"]})
    edge = DirectedLink("s1|t|0", "forward")
    return [
        Node("a", attrs={"x": [1]}),
        Link("a", "b", attrs={"x": {"y": 1}}),
        RiskGroup("r", (RiskGroup("child"),), attrs={"x": [1]}),
        condition,
        MatchSpec([condition]),
        selection("s1"),
        rule,
        mode,
        FailurePolicy({"x": [1]}, modes=[mode]),
        Component("hw", attrs={"x": [1]}, children={"c": Component("c")}),
        DemandSpec(selection("s1"), Selector("^t$"), 1, attrs={"x": [1]}),
        DemandSet("d", (DemandSpec(Selector("^s"), Selector("^t$"), 1),)),
        RouteSpec("s1", nodes=("s1", "t")),
        SupportSpec((edge,)),
        EdgeWeight(edge, 1),
        WeightSpec((EdgeWeight(edge, 1),)),
        PinnedRoutes(("r1",)),
        edge,
        Scenario(Network()),
        Network(),
        ComponentsLibrary(),
        BuildGraph(name="graph"),
        CostPower(name="cost"),
        MaxFlow(name="cap"),
        MaximumSupportedDemand(name="msd", demand_set="d"),
        NetworkStats(name="stats"),
        TrafficMatrixPlacement(name="tmp", demand_set="d"),
    ]


@pytest.mark.parametrize("record", records(), ids=lambda r: type(r).__name__)
def test_every_record_is_immutable_from_construction(record):
    name = dataclasses.fields(record)[0].name
    value = getattr(record, name)
    with pytest.raises(FrozenInstanceError):
        setattr(record, name, value)
    with pytest.raises(FrozenInstanceError):
        delattr(record, name)
    assert getattr(record, name) is value
    # Editing builds a new, validated record (a link copy gets a new id).
    edited = replace(record)
    assert edited == record or isinstance(record, (Scenario, Link))
    collections = isinstance(record, (Network, ComponentsLibrary))
    for item in vars(record).values():
        assert collections or type(item) not in (dict, list, set)


def walk(value, path="prepared", seen=None, custom=()):
    """Yield every mutable container, assignable object or scalar subclass reachable."""
    seen = set() if seen is None else seen
    if isinstance(value, (bool, int, float, str)) and not isinstance(value, Enum):
        if type(value) not in (bool, int, float, str):
            yield f"{path}: {type(value).__name__}"
        return
    if value is None or isinstance(value, (type, Enum)):
        return
    if id(value) in seen or type(value).__module__ == "_netgraph_core":
        return
    seen.add(id(value))
    if type(value) in (dict, list, set):
        yield path
    if isinstance(value, (dict, MappingProxyType)):
        for key, item in value.items():
            yield from walk(key, f"{path} key {key!r}", seen, custom)
            yield from walk(item, f"{path}[{key!r}]", seen, custom)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from walk(item, f"{path}[]", seen, custom)
    elif hasattr(value, "__dict__"):
        if isinstance(value, custom):
            return
        if dataclasses.is_dataclass(value) and not (
            type(value).__dataclass_params__.frozen
            or getattr(value, "_immutable", False)
        ):
            yield path
        for name, item in vars(value).items():
            yield from walk(item, f"{path}.{name}", seen, custom)


@dataclass
class Stateful(WorkflowStep):
    payload: list = field(default_factory=lambda: [1])
    counter: int = 0

    def run(self, context):
        self.counter += 1
        self.payload.append(self.counter)
        return StepOutput(
            {},
            {"counter": self.counter, "values": list(self.payload)},
        )


def rich_scenario():
    """Every kind of shared input, including a custom step with its own data."""
    s = source()
    policy = FailurePolicy(
        {"tags": [1]},
        modes=[FailureMode(1, [FailureRule("node", [Condition("role", "==", "s1")])])],
    )
    demands = DemandSet(
        "d", (DemandSpec(selection("s1"), Selector("^t$"), 1, attrs={"x": [1]}),)
    )
    library = ComponentsLibrary(
        {"hw": Component("hw", attrs={"x": [1]}, children={"c": Component("c")})}
    )
    return replace(
        s,
        workflow=(*s.workflow, Stateful(name="custom")),
        demand_sets={"d": demands},
        failure_policies={"p": policy},
        components_library=library,
        routes={"r1": RouteSpec("s1", nodes=("s1", "t"))},
    )


@pytest.mark.parametrize(
    "scenario",
    [
        rich_scenario,
        *(
            lambda path=path: Scenario.from_yaml(path.read_text())
            for path in sorted(Path("scenarios").glob("*.y*ml"))
        ),
    ],
)
def test_nothing_mutable_is_reachable_from_a_prepared_scenario(scenario):
    s = scenario()
    p = prepare(s, demand_sets=tuple(s.demand_sets))
    assert list(walk(p, custom=(Stateful,))) == []
    # Control: the caller's own scenario holds exactly its editable collections.
    editable = list(walk(s, "scenario", custom=(Stateful,)))
    assert "scenario.network.nodes" in editable
    assert "scenario.components_library.components" in editable
    assert all(
        not path.startswith(("scenario.workflow", "scenario.demand_sets"))
        for path in editable
    )


class Name(str):
    """A name whose own state can change after construction."""

    def __new__(cls, value):
        result = super().__new__(cls, value)
        result.current = value
        result.descending = False
        return result

    def __hash__(self):
        return hash(self.current)

    def __eq__(self, other):
        return self.current == str.__str__(other)

    def __lt__(self, other):
        if self.descending:
            return str.__gt__(self, other)
        return str.__lt__(self, other)


def named_network(names):
    network = Network(
        nodes={
            names[n]: Node(names[n], risk_groups={names["r"]}, attrs={names["k"]: 1})
            for n in ("s1", "s2", "t")
        }
    )
    network.add_link(Link(names["s1"], names["t"], 2, 1))
    network.add_link(Link(names["s2"], names["t"], 7, 1))
    network.risk_groups[names["r"]] = RiskGroup(names["r"])
    network.attrs[names["k"]] = names["k"]
    return network


def test_caller_string_subclasses_become_plain_in_a_prepared_scenario():
    names = {n: Name(n) for n in ("s1", "s2", "t", "r", "k", "hw", "c", "stats")}
    library = ComponentsLibrary(
        {names["hw"]: Component("hw", children={names["c"]: Component("c")})}
    )
    stats = NetworkStats(
        name=names["stats"], excluded_nodes=(names["s1"],), excluded_links=("s2|t|0",)
    )
    scenario = Scenario(
        named_network(names),
        (stats,),
        components_library=library,
        units=UnitsSettings(1),
    )
    prepared = prepare(scenario)
    assert list(walk(prepared)) == []
    assert list(walk(run(prepared))) == []
    # Control: the caller's own scenario keeps its subclass keys.
    assert "scenario.network.nodes key 's1': Name" in walk(scenario, "scenario")


def test_caller_key_and_exclusion_edits_never_reach_prepared_answers():
    keys = {n: Name(n) for n in ("s1", "s2", "t", "r", "k")}
    excluded = Name("s1")
    stats = NetworkStats(name="stats", excluded_nodes=(excluded,))
    prepared = prepare(Scenario(named_network(keys), (stats,), units=UnitsSettings(1)))
    policy = FailurePolicy(
        modes=(
            FailureMode(1, (FailureRule("node", path="^s", mode="choice", count=1),)),
        )
    )
    query = CapacityQuery(
        Selector("^s"),
        Selector("^t$"),
        failures=FailureRequest(policy, 1, seed=1),
        workers=1,
    )

    def answers():
        case = capacity(prepared, query).cases[1]
        delivered = case.states["converged"].rows[0].result.delivered
        stats = run(prepared).steps[0].result.total_capacity
        return case.case.pattern.excluded_nodes, delivered, stats

    assert answers() == (("s1",), 7, 7)
    for key in keys.values():
        key.descending = True
    excluded.current = "s2"
    assert answers() == (("s1",), 7, 7)


@pytest.mark.parametrize("editable", ["nodes", "links", "risk_groups", "attrs"])
def test_each_network_collection_is_owned_on_its_own(editable):
    """A network mixing a prepared view's dicts with an editable one owns each."""
    base = Network(nodes={n: Node(n, risk_groups={"r"}) for n in ("s", "t")})
    base.add_link(Link("s", "t", 10))
    base.risk_groups["r"] = RiskGroup("r")
    view = prepare(Scenario(base)).scenario.network
    caller = replace(view, **{editable: dict(getattr(view, editable))})
    steps = (BuildGraph(name="graph"), NetworkStats(name="stats"))
    prepared = prepare(Scenario(caller, steps, units=UnitsSettings(1)))
    assert prepared.scenario.network is not caller
    for name in ("nodes", "links", "risk_groups", "attrs"):
        assert type(getattr(prepared.scenario.network, name)) is _FrozenDict

    def answer():
        result = run(prepared)
        graph = result.steps[0].result.graph
        return (
            [edge["disabled"] for edge in graph["edges"]],
            sorted(node["id"] for node in graph["nodes"]),
            result.steps[1].result.total_capacity,
        )

    assert answer() == ([False, False], ["s", "t"], 10)
    edit = {
        "nodes": lambda: caller.add_node(Node("x")),
        "links": lambda: caller.disable_link("s|t|0"),
        "risk_groups": lambda: caller.risk_groups.pop("r"),
        "attrs": lambda: caller.attrs.__setitem__("x", 1),
    }[editable]
    edit()
    assert answer() == ([False, False], ["s", "t"], 10)
    assert dict(prepared.scenario.network.risk_groups) == {"r": RiskGroup("r")}
    assert dict(prepared.scenario.network.attrs) == {}


@pytest.mark.parametrize(
    "build,label",
    [
        (lambda v: Node("A", attrs={"x": v}), "node A.attrs.x"),
        (lambda v: Link("a", "b", attrs={"x": v}), "link a->b.attrs.x"),
        (lambda v: RiskGroup("r", attrs={"x": v}), "risk group r.attrs.x"),
        (lambda v: Component("hw", attrs={"x": v}), "component hw.attrs.x"),
        (lambda v: FailureMode(1, attrs={"x": v}), "failure mode attrs.x"),
        (
            lambda v: FailurePolicy({"x": v}, modes=(FailureMode(1),)),
            "failure policy attrs.x",
        ),
        (
            lambda v: DemandSpec(Selector("a"), Selector("b"), 1, attrs={"x": v}),
            "attrs.x",
        ),
        (lambda v: Condition("x", "==", {"x": v}), "condition x.value.x"),
    ],
)
def test_json_values_are_checked_and_frozen_at_construction(build, label):
    class Rank(IntEnum):
        ONE = 1

    for bad, kind in (
        (np.array(1.5), "numpy.ndarray"),
        (np.float64("nan"), "numpy.float64"),
        ({1, 2}, "set"),
        (MutableFloat(float("nan")), f"{__name__}.MutableFloat"),
    ):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert (
            str(error.value)
            == f"{label}: expected finite JSON data, got {kind} = {bad!r}"
        )
    caller = [Rank.ONE, np.float64(2), MutableFloat(3), {Text("key"): [4]}]
    record = build(caller)
    stored = record.value["x"] if isinstance(record, Condition) else record.attrs["x"]
    assert stored == [1, 2.0, 3.0, {"key": [4]}]
    assert [type(v) for v in stored[:3]] == [int, float, float]
    assert type(next(iter(stored[3]))) is str
    caller.append(5)
    caller[2].current = 9
    assert stored == [1, 2.0, 3.0, {"key": [4]}]
    assert type(stored) is _FrozenList and type(stored[3]) is _FrozenDict
    for edit in (
        lambda: stored.append(5),
        lambda: stored[3].__setitem__("key", 1),
        lambda: stored[3]["key"].extend([5]),
        lambda: stored[3].update(other=1),
    ):
        with pytest.raises(TypeError, match=READ_ONLY):
            edit()
    assert stored == [1, 2.0, 3.0, {"key": [4]}]


@pytest.mark.parametrize(
    "build,field,stored",
    [
        (lambda: Node("A", disabled=np.True_), "disabled", True),
        (lambda: RiskGroup("r", disabled=np.True_), "disabled", True),
        (lambda: Link("a", "b", cost=np.int64(2)), "cost", 2),
        (lambda: Link("a", "b", cost=np.float64(2.0)), "cost", 2),
        (lambda: Component("hw", count=np.int64(2)), "count", 2),
        (lambda: Component("hw", capex=np.float32(1)), "capex", 1.0),
        (lambda: Node(np.str_("A")), "name", "A"),
    ],
)
def test_a_numpy_scalar_of_the_fields_kind_is_stored_as_its_built_in_value(
    build, field, stored
):
    value = getattr(build(), field)
    assert value == stored and type(value) is type(stored)


@pytest.mark.parametrize(
    "build,message",
    [
        (
            lambda: Node("A", disabled=np.int64(1)),
            "node A.disabled: expected bool, got np.int64(1)",
        ),
        (
            lambda: Link("a", "b", cost=np.float64(2.5)),
            "link a->b.cost: expected an integer, got np.float64(2.5)",
        ),
        (
            lambda: Link("a", "b", cost=np.True_),
            "link a->b.cost: expected an integer, got np.True_",
        ),
        (
            lambda: Component("hw", capex=np.True_),
            "component hw.capex: expected a finite real number, got np.True_",
        ),
        (lambda: Node(np.int64(1)), "node.name: expected text, got np.int64(1)"),
    ],
)
def test_a_numpy_scalar_of_another_kind_is_refused(build, message):
    with pytest.raises(ValueError) as error:
        build()
    assert str(error.value) == message


def test_scalar_subclasses_are_stored_as_their_plain_values():
    score = MutableFloat(5)
    component = Component("hw", capex=score)
    condition = Condition(Text("role"), "==", MutableFloat(1.5))
    node = Node(Text("a"), risk_groups={Text("g")})
    score.current = 99
    assert type(component.capex) is float and component.total_capex() == 5
    assert type(condition.attr) is str and type(condition.value) is float
    assert type(node.name) is str and {type(g) for g in node.risk_groups} == {str}
    assert Component("hw", capex=np.float64(2)).capex == 2.0


def test_caller_cannot_edit_a_selector_and_an_edited_copy_answers_separately():
    s = source()
    p = prepare(s)
    condition = s.workflow[0].source.match.conditions[0]
    with pytest.raises(FrozenInstanceError):
        condition.value = "s2"
    with pytest.raises(AttributeError):
        s.workflow[0].source.match.conditions.append(Condition("role", "==", "s2"))
    with pytest.raises(FrozenInstanceError):
        s.workflow[0].workers = 9
    with pytest.raises(FrozenInstanceError):
        p.scenario.network = s.network
    assert answer(p) == (("s1",), 2)
    edited = replace(s, workflow=(replace(s.workflow[0], source=selection("s2")),))
    assert answer(prepare(edited)) == (("s2",), 7)
    assert answer(p) == (("s1",), 2)


@pytest.mark.parametrize(
    "operation",
    [
        lambda n: n.add_node(Node("new")),
        lambda n: n.add_link(Link("s1", "t", 1)),
        lambda n: n.disable_node("s1"),
        lambda n: n.enable_node("s1"),
        lambda n: n.disable_link("s1|t|0"),
        lambda n: n.enable_link("s1|t|0"),
        lambda n: n.disable_all(),
        lambda n: n.enable_all(),
        lambda n: n.disable_risk_group("r"),
        lambda n: n.enable_risk_group("r"),
        lambda n: n.replace_node("s1", attrs={"role": "s2"}),
        lambda n: n.nodes.__setitem__("s1", Node("s1", attrs={"role": "s2"})),
        lambda n: n.links.pop("s1|t|0"),
        lambda n: n.risk_groups.clear(),
        lambda n: n.attrs.update(x=1),
    ],
)
def test_caller_network_edits_succeed_and_never_reach_the_prepared_view(operation):
    s = source()
    p = prepare(s)
    with pytest.raises(TypeError, match=READ_ONLY):
        operation(p.scenario.network)
    operation(s.network)
    assert answer(p) == (("s1",), 2)
    assert p.scenario.network.nodes["s1"].attrs["role"] == "s1"
    assert p.scenario.network.nodes.keys() == {"s1", "s2", "t"}


def test_a_caller_attribute_edit_changes_only_a_fresh_preparation():
    s = source()
    p = prepare(s)
    s.network.replace_node("s1", attrs={"role": "x"})
    s.network.replace_node("s2", attrs={"role": "s1"})
    assert answer(p) == (("s1",), 2)
    assert answer(prepare(s)) == (("s2",), 7)


@dataclass
class AttemptEdit(WorkflowStep):
    operation: str = "disable"

    def run(self, context):
        network = context.prepared.scenario.network
        with pytest.raises(TypeError, match=READ_ONLY):
            if self.operation == "disable":
                network.disable_node("A2")
            else:
                network.add_node(Node("D"))
        return StepOutput({}, {})


@pytest.mark.parametrize("operation", ["disable", "add"])
def test_custom_step_edits_refuse_and_later_steps_and_runs_stay_17(operation):
    network = Network(nodes={name: Node(name) for name in ("A1", "A2", "B")})
    network.add_link(Link("A1", "B", 10))
    network.add_link(Link("A2", "B", 7))
    capacity = MaxFlow(
        name="cap",
        source=Selector("^A"),
        target=Selector("^B$"),
        preset=FlowPolicyPreset.TE_MAXFLOW_UNLIM,
        workers=1,
    )
    p = prepare(
        Scenario(
            network,
            (AttemptEdit(name="attempt", operation=operation), capacity),
            units=UnitsSettings(1),
        )
    )
    assert answer(p)[1] == answer(p)[1] == 17


def test_custom_step_data_is_its_own_and_its_prepared_identity_is_fixed():
    step = Stateful(name="custom", seed=3)
    s = Scenario(Network(), [step])
    p = prepare(s)
    step.payload.append(9)
    step.name, step.seed = "renamed", 4
    first, second = run(p).steps[0], run(p).steps[0]
    assert first.result == {"counter": 1, "values": [1, 9, 1]}
    assert second.result == {"counter": 2, "values": [1, 9, 1, 2]}
    assert (first.name, first.step_seed) == (second.name, second.step_seed)
    assert (first.name, first.step_seed) == ("custom", 3)
    assert p.scenario.workflow[0] is step and step.counter == 2


def snapshot_of(s):
    network = s.network
    return (
        id(network.nodes),
        id(network.links),
        id(network.risk_groups),
        id(network.attrs),
        tuple((name, id(node)) for name, node in network.nodes.items()),
        tuple((name, id(link)) for name, link in network.links.items()),
        tuple((name, id(group)) for name, group in network.risk_groups.items()),
        repr(network),
        id(s.components_library.components),
        tuple(map(id, s.components_library.components.values())),
        tuple(map(id, s.workflow)),
        repr(s),
    )


def test_prepare_changes_nothing_in_the_caller_even_when_it_fails():
    s = rich_scenario()
    before = snapshot_of(s)
    p = prepare(s, demand_sets=("d",))
    assert snapshot_of(s) == before
    assert p.scenario is not s and p.scenario.network is not s.network
    assert all(p.scenario.network.nodes[k] is v for k, v in s.network.nodes.items())
    broken = copy.deepcopy(s)
    broken.network.add_link(Link("s2", "t", 1e300))
    before = snapshot_of(broken)
    with pytest.raises(ValueError, match="no legal resolution"):
        prepare(broken)
    assert snapshot_of(broken) == before
    s.network.add_node(Node("later"))
    assert "later" not in p.scenario.network.nodes


def test_records_copy_and_pickle_as_equal_immutable_values():
    node = Node("a", attrs={"x": [1, {"y": 2}]}, risk_groups={"g"})
    for duplicate in (copy.deepcopy(node), pickle.loads(pickle.dumps(node))):
        assert duplicate == node
        assert type(duplicate.attrs["x"]) is _FrozenList
        with pytest.raises(TypeError, match=READ_ONLY):
            duplicate.attrs["x"].append(3)
    s = source()
    copied = copy.deepcopy(s)
    copied.network.disable_node("s1")
    assert not s.network.nodes["s1"].disabled
    # Native values cannot be pickled; a scenario of plain records can.
    restored = pickle.loads(pickle.dumps(Scenario(s.network)))
    assert restored.network == s.network and restored.network is not s.network
    assert copy.deepcopy(s).workflow[0] is s.workflow[0]


def test_link_ids_are_assigned_once_by_their_network():
    first, second = Network(), Network()
    for network in (first, second):
        network.add_node(Node("a"))
        network.add_node(Node("b"))
    link = Link("a", "b")
    first.add_link(link)
    assert link.id == "a|b|0" and first.links["a|b|0"] is link
    with pytest.raises(ValueError, match="already been added to a network"):
        second.add_link(link)
    second.add_link(replace(link))
    assert link.id == "a|b|0" and second.links["a|b|0"] is not link
    changed = first.replace_link("a|b|0", capacity=5)
    assert changed.id == "a|b|0" and first.links["a|b|0"] is changed
    assert link.capacity == 1.0
    first.add_node(Node("c"))
    for changes, named in (
        ({"target": "c"}, "target"),
        ({"source": "nowhere"}, "source"),
        ({"source": "b", "target": "a"}, "source and target"),
    ):
        with pytest.raises(ValueError) as error:
            first.replace_link("a|b|0", **changes)
        assert str(error.value) == (
            f"Link 'a|b|0': {named} cannot change; add a new link instead."
        )
    assert first.links["a|b|0"] is changed


LIST_MUTATORS = {
    "__setitem__": (0, 9),
    "__delitem__": (0,),
    "__iadd__": ([9],),
    "__imul__": (2,),
    "__init__": ([9],),
    "append": (9,),
    "clear": (),
    "extend": ([9],),
    "insert": (0, 9),
    "pop": (),
    "remove": ("s1",),
    "reverse": (),
    "sort": (),
}
DICT_MUTATORS = {
    "__setitem__": ("x", 9),
    "__delitem__": ("role",),
    "__ior__": ({"x": 9},),
    "__init__": ({"x": 9},),
    "clear": (),
    "pop": ("role",),
    "popitem": (),
    "setdefault": ("x", 9),
    "update": ({"x": 9},),
}


@pytest.mark.parametrize(
    "kind,name",
    [("list", name) for name in LIST_MUTATORS]
    + [("dict", name) for name in DICT_MUTATORS],
)
def test_every_frozen_container_mutator_refuses_and_changes_nothing(kind, name):
    network = Network(nodes={s: Node(s, attrs={"role": s}) for s in ("s1", "s2", "t")})
    network.add_link(Link("s1", "t", 2))
    network.add_link(Link("s2", "t", 7))
    both = Selector(match=MatchSpec((Condition("role", "in", ["s1", "s2"]),)))
    step = MaxFlow(name="cap", source=both, target=Selector("^t$"), workers=1)
    prepared = prepare(Scenario(network, (step,), units=UnitsSettings(1)))

    def delivered():
        row = run(prepared).steps[0].result.cases[0].states["converged"].rows[0]
        return row.result.delivered

    assert delivered() == 9
    if kind == "list":
        value = prepared.scenario.workflow[0].source.match.conditions[0].value
        arguments, before = LIST_MUTATORS[name], ["s1", "s2"]
        assert type(value) is _FrozenList
    else:
        value = prepared.scenario.network.nodes["s1"].attrs
        arguments, before = DICT_MUTATORS[name], {"role": "s1"}
        assert type(value) is _FrozenDict
    with pytest.raises(TypeError) as error:
        getattr(value, name)(*arguments)
    assert str(error.value) == (
        "read-only: records are immutable; edit through Network methods or "
        "dataclasses.replace, then prepare again"
    )
    assert value == before
    assert delivered() == 9
