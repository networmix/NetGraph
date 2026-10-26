"""Preparation identifies the current workflow entry, including composite questions."""

from dataclasses import replace

import netgraph_core as ngc
import pytest

from ngraph import (
    ControllerGroup,
    DemandSet,
    DemandSpec,
    DirectedLink,
    FailureMode,
    FailurePolicy,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    Link,
    Network,
    Node,
    PinnedRoutes,
    RouteSpec,
    RoutingDomain,
    Scenario,
    Selector,
    UnitsSettings,
    WCMPController,
    prepare,
)
from ngraph.workflow import (
    BuildGraph,
    MaxFlow,
    MaximumSupportedDemand,
    TrafficMatrixPlacement,
)


def network():
    net = Network(nodes={k: Node(k) for k in ("A", "B", "C")})
    net.add_link(Link("A", "B", 8, 3))
    net.add_link(Link("B", "C", 8, 5))
    return net


def scenario(step, **kw):
    return Scenario(
        network(),
        (BuildGraph(name="g"), BuildGraph(name="g2"), step),
        units=UnitsSettings(1),
        **kw,
    )


def pinned(*, split=False, many=False):
    model = PinnedRoutes(
        ("r",), **({"allocation": ngc.RouteAllocation.EQUAL} if split else {})
    )
    step = MaxFlow(
        name="bad",
        source=Selector("^(A|B)$" if many else "^A$", group_by="name"),
        target=Selector("^C$"),
        mode="pairwise",
        model=model,
    )
    return scenario(step, routes={"r": RouteSpec("A", nodes=("A", "B", "C"))})


def pooled(*, unknown_alpha):
    demands = DemandSet(
        "load",
        (
            DemandSpec(
                Selector("^(A|B)$"),
                Selector("^C$"),
                1,
                FlowPolicyPreset.TE_ECMP_16_LSP,
                id="pool",
            ),
        ),
    )
    fields = {"alpha_from_step": "msd"} if unknown_alpha else {"alpha": 1}
    steps = (
        BuildGraph(name="g"),
        MaximumSupportedDemand(name="msd", demand_set="load"),
        TrafficMatrixPlacement(
            name="bad", demand_set="load", interaction="simultaneous", **fields
        ),
    )
    return Scenario(
        network(), steps, units=UnitsSettings(1), demand_sets={"load": demands}
    )


def controller(*, states):
    trees = {
        name: ForwardingGroup(
            router, (ControllerGroup((GroupChild(1, DirectedLink(link, "forward")),)),)
        )
        for name, router, link in [("a", "A", "A|B|0"), ("b", "B", "B|C|0")]
    }
    demands = DemandSet(
        "load",
        tuple(
            DemandSpec(
                Selector(source),
                Selector("^C$"),
                1,
                FlowPolicyPreset.SHORTEST_PATHS_WCMP,
            )
            for source in ("^A$", "^B$")
        ),
    )
    return scenario(
        TrafficMatrixPlacement(
            name="bad", demand_set="load", failure_policy="f", failure_states=states
        ),
        demand_sets={"load": demands},
        failure_policies={"f": FailurePolicy(modes=[FailureMode(1, [])])},
        routing=RoutingDomain(Selector("^B$"), Selector("^(A|C)$")),
        wcmp_controller=WCMPController("group"),
        forwarding_groups=trees,
    )


@pytest.mark.timeout(10)
@pytest.mark.parametrize(
    "many, split, expected",
    [
        (
            True,
            False,
            "workflow[2] (name 'bad'): pinned model requires one endpoint pair",
        ),
        (
            False,
            True,
            "workflow[2] (name 'bad').model: split fields require a DAG route",
        ),
    ],
)
def test_pinned_question_refusals(many, split, expected):
    with pytest.raises(ValueError) as error:
        prepare(pinned(many=many, split=split))
    assert str(error.value) == expected
    prepare(pinned())


@pytest.mark.timeout(10)
def test_simultaneous_scale_refusal():
    with pytest.raises(ValueError) as error:
        prepare(pooled(unknown_alpha=True))
    assert str(error.value) == (
        "workflow[2] (name 'bad').interaction = 'simultaneous': demand pool|0: its scale comes "
        "from MSD step msd, unknown at preparation, so TE ingress pool pool|0 has no lossy offer budget"
    )
    prepare(pooled(unknown_alpha=False))


@pytest.mark.timeout(10)
def test_controller_failure_state_refusal():
    with pytest.raises(ValueError) as error:
        prepare(controller(states=("converged",)))
    assert str(error.value) == (
        "workflow[2] (name 'bad').failure_states: forwarding_groups.b: "
        "router B is inside routing.igp_domain; converged and repair need programmed routers at the BGP edge"
    )
    assert type(error.value.__cause__) is ValueError
    assert str(error.value.__cause__).startswith(
        "workflow.bad.failure_states: forwarding_groups.b:"
    )
    prepare(controller(states=("stale",)))


@pytest.mark.timeout(10)
def test_duplicate_python_entry():
    with pytest.raises(ValueError) as error:
        prepare(scenario(BuildGraph(name="g")))
    assert (
        str(error.value)
        == "workflow[2] (name 'g').name = 'g': Duplicate workflow step name: g"
    )
    prepare(scenario(BuildGraph(name="g3")))


@pytest.mark.timeout(10)
def test_wrong_python_entry():
    with pytest.raises(TypeError) as error:
        scenario(3)
    assert str(error.value) == "workflow[2] = 3: expected WorkflowStep values"
    prepare(scenario(BuildGraph(name="g3")))


@pytest.mark.timeout(10)
def test_a_reordered_yaml_step_uses_its_current_index_and_raw_declaration():
    text = """
network:
  nodes: {A: {}, B: {}}
  links: [{source: A, target: B, capacity: 8}]
workflow:
  - {type: BuildGraph, name: g}
  - {type: BuildGraph, name: g2}
  - {type: MaxFlow, name: bad, source: '^A$', target: '^B$', failure_policy: missing}
"""
    loaded = Scenario.from_yaml(text)
    last = loaded.workflow[2]
    reordered = replace(loaded, workflow=(last, *loaded.workflow[:2]))
    with pytest.raises(ValueError) as error:
        prepare(reordered)
    assert (
        str(error.value)
        == "workflow[0] (name 'bad').failure_policy = 'missing': unknown failure policy"
    )
    fixed = replace(last, failure_policy=None)
    prepare(replace(loaded, workflow=(fixed, *loaded.workflow[:2])))


@pytest.mark.timeout(10)
def test_names_with_path_punctuation_and_unnamed_python_steps():
    name = "a.b]: 'x"
    for given, clause in [(name, ' (name "a.b]: \'x")'), ("", "")]:
        step = TrafficMatrixPlacement(name=given, demand_set="missing")
        with pytest.raises(ValueError) as error:
            prepare(scenario(step))
        assert (
            str(error.value)
            == f"workflow[2]{clause}.demand_set = 'missing': unknown demand set"
        )
        demands = DemandSet("missing", ())
        prepare(scenario(step, demand_sets={"missing": demands}))


@pytest.mark.timeout(10)
def test_native_model_refusal_names_the_entry_without_a_value():
    text = """
network:
  nodes: {A: {}, B: {}}
  links: [{source: A, target: B, capacity: 8}]
workflow:
  - {type: BuildGraph, name: g}
  - {type: BuildGraph, name: g2}
  - type: MaxFlow
    name: bad
    source: '^A$'
    target: '^B$'
    model:
      routing: {type: centralized_te, source_allocation: optimized}
      admission: lossy
"""
    with pytest.raises(ValueError) as error:
        prepare(Scenario.from_yaml(text))
    assert str(error.value) == (
        "workflow[2] (name 'bad'): "
        "CentralizedTE without tunnel_count requires admission=LOSSLESS"
    )
    prepare(Scenario.from_yaml(text.replace("admission: lossy", "admission: lossless")))


@pytest.mark.timeout(10)
def test_a_python_capacity_question_keeps_its_exception_type():
    from dataclasses import dataclass

    from ngraph import CapacityQuery, StepOutput, WorkflowStep
    from ngraph.analysis.preparation import StepNeeds

    @dataclass
    class Question(WorkflowStep):
        refused: bool = True

        def needs(self):
            return StepNeeds(numerical=True, capacity=self.query)

        def query(self, prepared):
            if self.refused:
                raise TypeError("question.count = 3: expected text")
            return CapacityQuery(Selector("^A$"), Selector("^B$"))

        def run(self, context):
            return StepOutput({}, None)

    with pytest.raises(TypeError) as error:
        prepare(scenario(Question(name="bad")))
    assert type(error.value) is TypeError
    assert str(error.value) == (
        "workflow[2] (name 'bad'): question.count = 3: expected text"
    )
    prepare(scenario(Question(name="bad", refused=False)))


@pytest.mark.timeout(10)
def test_the_standalone_sequence_check_locates_a_wrong_entry():
    from ngraph.workflow.base import validate_unique_step_names

    with pytest.raises(TypeError) as error:
        validate_unique_step_names([BuildGraph(name="g"), BuildGraph(name="g2"), 3])
    assert str(error.value) == "workflow[2] = 3: expected WorkflowStep values"
    validate_unique_step_names(
        [BuildGraph(name="g"), BuildGraph(name="g2"), BuildGraph(name="g3")]
    )


@pytest.mark.timeout(10)
def test_a_pinned_model_locates_its_unknown_weight_vector():
    from ngraph import EdgeWeight, SupportSpec, WeightSpec

    step = MaxFlow(
        name="bad",
        source=Selector("^A$"),
        target=Selector("^B$"),
        model=PinnedRoutes(
            ("r",),
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights="missing",
        ),
    )
    edge = DirectedLink("A|B|0", "forward")
    value = scenario(
        step,
        routes={"r": RouteSpec("A", support="s")},
        supports={"s": SupportSpec((edge,))},
    )
    with pytest.raises(ValueError) as error:
        prepare(value)
    assert (
        str(error.value)
        == "workflow[2] (name 'bad').model.routing.edge_weights = 'missing': unknown weights"
    )
    prepare(replace(value, weights={"missing": WeightSpec((EdgeWeight(edge, 1),))}))
