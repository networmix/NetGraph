"""Every input field is checked where it is given, by one rule per kind of field.

A field accepts its built-in type or the NumPy scalar of the same kind, stored as the
built-in value; integers also accept exactly integral floats; booleans are never
numbers. Each refusal names the field and the value. What only the whole network can
check (names that must exist, sums) stays at preparation.
"""

from fractions import Fraction

import netgraph_core as ngc
import numpy as np
import pytest

from ngraph import (
    Component,
    ComponentsLibrary,
    Condition,
    ControllerGroup,
    DemandSpec,
    DirectedLink,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    ForwardingGroup,
    GroupChild,
    Link,
    MatchSpec,
    Network,
    Node,
    PinnedRoutes,
    RiskGroup,
    RouteSpec,
    Selector,
    UnitsSettings,
)
from ngraph.workflow.base import step_type

EDGE = DirectedLink("A|B|0", "forward")


# --- one rule per kind ------------------------------------------------------------

TEXT = [
    (lambda v: Node(v), "name", "node.name"),
    (lambda v: Link(v, "B"), "source", "link.source"),
    (lambda v: Link("A", v), "target", "link.target"),
    (lambda v: RiskGroup(v), "name", "risk group.name"),
    (lambda v: Component(v), "name", "component.name"),
    (lambda v: Condition(v, "=="), "attr", "condition.attr"),
    (lambda v: RouteSpec(v, support="s"), "head", "route.head"),
]


@pytest.mark.parametrize(("build", "field", "label"), TEXT)
def test_a_text_field_is_a_nonempty_str_and_whitespace_is_part_of_a_name(
    build, field, label
):
    assert getattr(build(np.str_("A")), field) == "A"
    assert type(getattr(build(np.str_("A")), field)) is str
    assert getattr(build(" "), field) == " "  # a name, as preparation's rule had it
    for bad, shown in (
        (b"A", "b'A'"),
        (1, "1"),
        (True, "True"),
        (None, "None"),
        (np.int64(1), "np.int64(1)"),
    ):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert str(error.value) == f"{label}: expected text, got {shown}"
    with pytest.raises(ValueError) as error:
        build("")
    assert str(error.value) == f"{label}: expected a nonempty name, got ''"


FLAGS = [
    (lambda v: Node("A", disabled=v), "disabled", "node A.disabled"),
    (lambda v: Link("A", "B", disabled=v), "disabled", "link A->B.disabled"),
    (lambda v: RiskGroup("r", disabled=v), "disabled", "risk group r.disabled"),
    (lambda v: Selector("^A$", active_only=v), "active_only", "selector.active_only"),
    (
        lambda v: FailurePolicy(expand_groups=v, modes=(FailureMode(1),)),
        "expand_groups",
        "failure policy expand_groups",
    ),
    (lambda v: FailureRequest(None, failure_trace=v), "failure_trace", "failure_trace"),
    (
        lambda v: step_type("BuildGraph")(add_reverse=v),
        "add_reverse",
        "BuildGraph.add_reverse",
    ),
]


@pytest.mark.parametrize(("build", "field", "label"), FLAGS)
def test_a_flag_is_a_bool_or_a_numpy_bool(build, field, label):
    for given, stored in ((True, True), (np.False_, False)):
        value = getattr(build(given), field)
        assert value is stored
    for bad in ("false", 1, 0.0, np.int64(1)):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert str(error.value) == f"{label}: expected bool, got {bad!r}"


INTEGERS = [
    (lambda v: Link("A", "B", cost=v), "cost", "link A->B.cost", 1),
    (lambda v: Component("c", count=v), "count", "component c.count", 1),
    (lambda v: Component("c", ports=v), "ports", "component c.ports", 0),
    (lambda v: FailureRule("link", count=v), "count", "failure rule count", 1),
    (
        lambda v: FailureRequest(None, iterations=v),
        "iterations",
        "failure iterations",
        0,
    ),
    (lambda v: RouteSpec("A", support="s", weight=v), "weight", "route.weight", 0),
]


@pytest.mark.parametrize(("build", "field", "label", "minimum"), INTEGERS)
def test_an_integer_is_an_int_a_numpy_integer_or_an_integral_float(
    build, field, label, minimum
):
    for given in (3, np.int64(3), 3.0, np.float32(3.0)):
        value = getattr(build(given), field)
        assert value == 3 and type(value) is int
    for bad in (True, np.True_, 2.5, np.float64(2.5), "3", Fraction(3), float("nan")):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert str(error.value) == f"{label}: expected an integer, got {bad!r}"
    with pytest.raises(ValueError) as error:
        build(minimum - 1)
    assert str(error.value).startswith(f"{label}: integer outside [{minimum}, ")
    assert str(error.value).endswith(f"got {minimum - 1}")


def test_a_cost_is_below_2_to_the_62():
    assert Link("A", "B", cost=(1 << 62) - 1).cost == (1 << 62) - 1
    with pytest.raises(ValueError) as error:
        Link("A", "B", cost=1 << 62)
    assert str(error.value) == (
        f"link A->B.cost: integer outside [1, 2^62), got {1 << 62}"
    )


REALS = [
    (lambda v: Link("A", "B", capacity=v), "capacity", "link A->B.capacity"),
    (lambda v: Component("c", capex=v), "capex", "component c.capex"),
    (lambda v: Component("c", power_watts=v), "power_watts", "component c.power_watts"),
    (
        lambda v: Component("c", power_watts_max=v),
        "power_watts_max",
        "component c.power_watts_max",
    ),
    (lambda v: Component("c", capacity=v), "capacity", "component c.capacity"),
    (lambda v: FailureMode(v), "weight", "failure mode weight"),
    (
        lambda v: DemandSpec(Selector("^A$"), Selector("^B$"), v),
        "volume",
        "demand.volume",
    ),
]


@pytest.mark.parametrize(("build", "field", "label"), REALS)
def test_a_real_is_any_real_number_but_a_boolean_stored_as_binary64(
    build, field, label
):
    for given in (2, 2.5, np.float32(2.5), np.int64(2), Fraction(5, 2)):
        value = getattr(build(given), field)
        assert value == float(given) and type(value) is float
    for bad in (True, np.True_, "1", None):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert (
            str(error.value) == f"{label}: expected a finite real number, got {bad!r}"
        )
    for bad in (-1, float("nan"), float("inf")):
        with pytest.raises(ValueError) as error:
            build(bad)
        assert str(error.value) == (
            f"{label}: expected a finite nonnegative amount, got {bad!r}"
        )


# --- checks that moved to construction ---------------------------------------------


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (lambda: Selector("(["), "selector.path: invalid pattern '(['"),
        (
            lambda: FailureRule("link", path="(["),
            "failure rule path: invalid pattern '(['",
        ),
        (
            lambda: MatchSpec((Condition("x", "==", 1),), "xor"),
            "match.logic: expected and or or, got 'xor'",
        ),
        (lambda: PinnedRoutes(()), "pinned.routes: expected a nonempty ordered list"),
        (
            lambda: PinnedRoutes(("r",), admission="lossy"),
            "pinned.admission: expected lossless or lossy, got 'lossy'",
        ),
        (
            lambda: PinnedRoutes(("r",), allocation="weighted"),
            "pinned.allocation: expected equal or weighted, got 'weighted'",
        ),
        (
            lambda: PinnedRoutes(("r",), weight_basis=ngc.WeightBasis.EXPLICIT),
            "pinned: weights require weighted allocation",
        ),
        (
            lambda: PinnedRoutes(
                ("r",),
                allocation=ngc.RouteAllocation.WEIGHTED,
                weight_basis=ngc.WeightBasis.EXPLICIT,
            ),
            "pinned: explicit basis requires named edge_weights and conversely",
        ),
        (
            lambda: RouteSpec("A", nodes=("A",)),
            "route.nodes: a node route needs at least two nodes, got ('A',)",
        ),
        (
            lambda: RouteSpec("A", edges=()),
            "route.edges: an edge route needs at least one edge",
        ),
        (
            lambda: GroupChild(-1, EDGE),
            "group_child.share: expected a nonnegative share, got -1",
        ),
        (
            lambda: GroupChild(1),
            "group_child: expected exactly one of edge and children",
        ),
        (
            lambda: GroupChild(1, children=()),
            "group_child.children: expected at least one child",
        ),
        (
            lambda: ControllerGroup((GroupChild(1, EDGE),), -1),
            "controller_group.share: expected a nonnegative share, got -1",
        ),
        (
            lambda: ControllerGroup(()),
            "controller_group.children: expected at least one child",
        ),
        (
            lambda: ForwardingGroup("S", ()),
            "forwarding_group.groups: expected at least one group",
        ),
        (
            lambda: FailurePolicy(modes=(FailureMode(0),)),
            "failure policy modes: at least one mode must have positive weight",
        ),
        (
            lambda: FailureRule("link", count=0),
            "failure rule count: integer outside [1, inf), got 0",
        ),
        (
            lambda: FailureRule("link", weight_by=""),
            "failure rule weight_by: expected a nonempty name, got ''",
        ),
        (
            lambda: step_type("MaxFlow")(
                source=Selector("^A$"), target=Selector("^B$"), failure_policy=1
            ),
            "MaxFlow.failure_policy: expected text, got 1",
        ),
        (
            lambda: step_type("TrafficMatrixPlacement")(
                demand_set="d", alpha_from_step=1
            ),
            "TrafficMatrixPlacement.alpha_from_step: expected text, got 1",
        ),
        (
            lambda: step_type("TrafficMatrixPlacement")(demand_set=1),
            "TrafficMatrixPlacement.demand_set: expected text, got 1",
        ),
    ],
)
def test_a_local_rule_refuses_where_the_object_is_built(build, message):
    with pytest.raises(ValueError) as error:
        build()
    assert str(error.value).startswith(message)


@pytest.mark.parametrize(
    ("build", "message"),
    [
        (
            lambda: Network(nodes=1),
            "network.nodes: expected a mapping of names to Node values, got 1",
        ),
        (
            lambda: Network(links={"x": 1}),
            "network.links: expected a mapping of names to Link values, got {'x': 1}",
        ),
        (
            lambda: Network(risk_groups="x"),
            "network.risk_groups: expected a mapping of names to RiskGroup values, got 'x'",
        ),
        (
            lambda: ComponentsLibrary(components=1),
            "components: expected Component values by name, got 1",
        ),
        (
            lambda: Component("c", children=[1]),
            "component c.children: expected Component values by name, got [1]",
        ),
        (
            lambda: step_type("MaxFlow")(
                source=Selector("^A$"), target=Selector("^B$"), model=1
            ),
            "MaxFlow.model: expected a declared model or native FlowPolicyConfig, got 1",
        ),
    ],
)
def test_a_container_or_model_of_the_wrong_type_refuses_where_it_is_given(
    build, message
):
    with pytest.raises(TypeError) as error:
        build()
    assert str(error.value) == message


def test_network_attrs_are_json_at_construction():
    with pytest.raises(ValueError, match="network.attrs: expected a mapping"):
        Network(attrs=1)
    assert Network(attrs={"region": "west"}).attrs == {"region": "west"}


def test_valid_controls_build():
    # Each object of the refusals above with valid fields builds.
    assert Selector("^A$").path == "^A$" and Selector("").path == ""
    assert PinnedRoutes(("r",), admission=ngc.Admission.LOSSY).routes == ("r",)
    assert RouteSpec("A", nodes=("A", "B")).nodes == ("A", "B")
    assert RouteSpec("A", edges=(EDGE,)).edges == (EDGE,)
    assert ForwardingGroup("S", (ControllerGroup((GroupChild(0, EDGE),), 0),)).groups
    assert FailurePolicy(modes=(FailureMode(0), FailureMode(1))).modes
    assert FailureRule("link", count=1, weight_by="w", path="^a").path == "^a"
    assert FailureRequest(None, policy_name=None).policy_name is None
    named = FailureRequest(
        FailurePolicy(modes=(FailureMode(1),)), policy_name=np.str_("p")
    )
    assert type(named.policy_name) is str
    assert UnitsSettings(np.str_("auto")).resolution == "auto"
    assert type(UnitsSettings(np.str_("auto")).resolution) is str


def test_an_int_subclass_is_read_as_its_stored_value_not_its_conversions():
    class Shifted(int):
        def __int__(self):
            return 99

        def __index__(self):
            return 99

    cost = Link("A", "B", cost=Shifted(3)).cost
    assert cost == 3 and type(cost) is int


def test_exported_costs_are_the_links_integers():
    from ngraph import Scenario, prepare, run

    network = Network()
    for name in ("A", "B"):
        network.add_node(Node(name))
    network.add_link(Link("A", "B", cost=3.0))
    network.add_link(Link("B", "A", cost=7))
    steps = (step_type("BuildGraph")(name="g"), step_type("NetworkStats")(name="s"))
    graph, stats = (s.result for s in run(prepare(Scenario(network, steps))).steps)
    costs = [edge["cost"] for edge in graph.graph["edges"]]
    assert sorted(costs) == [3, 3, 7, 7] and {type(c) for c in costs} == {int}
    assert graph.edge_count == 4 and stats.link_count == 2
    assert (stats.min_cost, stats.max_cost) == (3, 7)
    assert type(stats.min_cost) is int and type(stats.max_cost) is int
    assert stats.mean_cost == 5.0 and type(stats.mean_cost) is float
