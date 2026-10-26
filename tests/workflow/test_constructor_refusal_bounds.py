"""Direct step construction uses the same bounded value format as YAML."""

import pytest

from ngraph import Selector
from ngraph.workflow import (
    MaxFlow,
    NetworkStats,
    TrafficMatrixPlacement,
    TunnelCountAnalysis,
)


@pytest.mark.parametrize("length", [3, 58, 100000])
@pytest.mark.parametrize(
    "kind, field, prefix, error_class",
    [
        (
            MaxFlow,
            "mode",
            "MaxFlow.mode: expected combine or pairwise, got ",
            ValueError,
        ),
        (
            MaxFlow,
            "preset",
            "MaxFlow.preset: expected FlowPolicyPreset, got ",
            TypeError,
        ),
        (
            MaxFlow,
            "model",
            "MaxFlow.model: expected a declared model or native FlowPolicyConfig, got ",
            TypeError,
        ),
        (
            MaxFlow,
            "outputs",
            "MaxFlow.outputs: expected native OutputOptions, got ",
            TypeError,
        ),
        (
            TrafficMatrixPlacement,
            "interaction",
            "workflow.bad.interaction: expected ordered or simultaneous, got ",
            ValueError,
        ),
        (
            TrafficMatrixPlacement,
            "outputs",
            "TrafficMatrixPlacement.outputs: expected native OutputOptions, got ",
            TypeError,
        ),
        (
            NetworkStats,
            "excluded_nodes",
            "NetworkStats.excluded_nodes: expected a sequence of names, got ",
            ValueError,
        ),
        (
            NetworkStats,
            "excluded_links",
            "NetworkStats.excluded_links: expected a sequence of names, got ",
            ValueError,
        ),
    ],
)
def test_scalar_constructor_refusals_are_bounded(
    kind, field, prefix, error_class, length
):
    raw = "x" * length
    rendered = repr(raw)
    shown = rendered if len(rendered) <= 60 else rendered[:57] + "..."
    valid = {"demand_set": "load"} if kind is TrafficMatrixPlacement else {}
    with pytest.raises(error_class) as error:
        kind(name="bad", **valid, **{field: raw})
    assert str(error.value) == prefix + shown
    assert len(str(error.value)) < 500
    kind(name="bad", **valid)


@pytest.mark.parametrize("endpoint", ["source", "target"])
def test_bad_python_endpoint_uses_a_bounded_pair_value(endpoint):
    raw = "x" * 100000
    pair = (raw, Selector(".*")) if endpoint == "source" else (Selector(".*"), raw)
    with pytest.raises(TypeError) as error:
        MaxFlow(**{endpoint: raw})
    assert (
        str(error.value)
        == "MaxFlow endpoints: expected Selectors, got " + repr(pair)[:57] + "..."
    )
    MaxFlow()


@pytest.mark.parametrize("length", [3, 100000])
def test_failure_state_element_is_bounded(length):
    raw = ["x" * length]
    rendered = repr(raw)
    shown = rendered if len(rendered) <= 60 else rendered[:57] + "..."
    with pytest.raises(ValueError) as error:
        TrafficMatrixPlacement(name="bad", demand_set="load", failure_states=raw)
    assert (
        str(error.value)
        == "workflow.bad.failure_states: expected distinct states from ['converged', 'stale', 'repair'], got "
        + shown
    )
    TrafficMatrixPlacement(name="bad", demand_set="load", failure_states=("converged",))


def test_count_query_output_value_is_bounded_during_construction():
    raw = "x" * 100000
    with pytest.raises(TypeError) as error:
        TunnelCountAnalysis(
            name="bad",
            demand_set="load",
            counts=(1,),
            offer=1,
            design_demand=1,
            outputs=raw,
        )
    assert (
        str(error.value)
        == "workflow step bad: tunnel_counts.outputs: expected native OutputOptions, got '"
        + "x" * 56
        + "..."
    )
    TunnelCountAnalysis(
        name="bad", demand_set="load", counts=(1,), offer=1, design_demand=1
    )


def test_msd_shared_query_values_are_bounded():
    from ngraph import ResolvedDemandSet
    from ngraph.analysis.msd import MSDQuery
    from ngraph.workflow import MaximumSupportedDemand

    class Loud(float):
        def __repr__(self):
            return "x" * 100000

    for factory, prefix in [
        (
            lambda value: MaximumSupportedDemand(
                demand_set="load", growth_factor=value
            ),
            "MaximumSupportedDemand.growth_factor: must exceed 1, got ",
        ),
        (
            lambda value: MSDQuery(
                ResolvedDemandSet("load", (), (), ()), growth_factor=value
            ),
            "msd.growth_factor: must exceed 1, got ",
        ),
    ]:
        with pytest.raises(ValueError) as error:
            factory(Loud(0.5))
        assert str(error.value) == prefix + "x" * 57 + "..."
        factory(2)


def test_shared_selector_refusals_render_values():
    from ngraph.model.selectors import Condition, MatchSpec

    raw = "x" * 100000
    shown = "'" + "x" * 56 + "..."
    operators = "['!=', '<', '<=', '==', '>', '>=', 'contains', 'exists', 'in', 'not_contains', 'not_exists', 'not_in']"
    cases = [
        (
            lambda: Condition("role", raw),
            f"condition.op: expected one of {operators}, got {shown}",
            ValueError,
        ),
        (
            lambda: Condition("role", "in", raw),
            "condition role.value: 'in' requires a list, got " + shown,
            ValueError,
        ),
        (
            lambda: MatchSpec(conditions=(raw,)),
            "match.conditions: expected Condition values, got ('" + "x" * 55 + "...",
            TypeError,
        ),
        (
            lambda: MatchSpec(logic=raw),
            "match.logic: expected and or or, got " + shown,
            ValueError,
        ),
        (
            lambda: Selector(path="A", match=raw),
            "Selector 'match' must be MatchSpec or None, got " + shown,
            TypeError,
        ),
    ]
    for factory, expected, kind in cases:
        with pytest.raises(kind) as error:
            factory()
        assert str(error.value) == expected
        assert len(str(error.value)) < 500
    MatchSpec(conditions=(Condition("role", "exists"),), logic="or")
    Selector(path="A", match=MatchSpec())


@pytest.mark.parametrize("site", ["preset", "allocation", "routing"])
def test_shared_model_parser_values_are_bounded(site):
    from ngraph.workflow.parse import build_workflow_steps

    raw = "x" * 100000
    shown = "'" + "x" * 56 + "..."
    entry = {"type": "MaxFlow", "name": "bad", "source": "^A$", "target": "^B$"}
    if site == "preset":
        entry["preset"] = raw
        field, reason = "preset", "unknown preset"
    else:
        routing = {"type": "shortest_paths"}
        routing["allocation" if site == "allocation" else "type"] = raw
        entry["model"] = {"routing": routing}
        field = (
            "model.routing.allocation" if site == "allocation" else "model.routing.type"
        )
        reason = "unknown value" if site == "allocation" else "unknown routing type"
    with pytest.raises(ValueError) as error:
        build_workflow_steps([entry], lambda name: None)
    assert (
        str(error.value)
        == f"workflow[0] (name 'bad').{field} = {shown}: {reason} {shown}"
    )
    if site == "preset":
        entry["preset"] = "SHORTEST_PATHS_ECMP"
    else:
        entry["model"] = {"routing": {"type": "shortest_paths", "allocation": "equal"}}
    build_workflow_steps([entry], lambda name: None)


def test_msd_range_tuple_uses_the_shared_value_bound():
    from ngraph.workflow import MaximumSupportedDemand

    values = (1.2345678901234568e-123, 2.3456789012345678e-123, 1.1234567890123457e-123)
    rendered = repr(values)
    assert len(rendered) > 60
    with pytest.raises(ValueError) as error:
        MaximumSupportedDemand(
            demand_set="load",
            alpha_min=values[0],
            alpha_start=values[1],
            alpha_max=values[2],
        )
    assert (
        str(error.value)
        == "MaximumSupportedDemand: require alpha_min <= alpha_start <= alpha_max, got "
        + rendered[:57]
        + "..."
    )
    MaximumSupportedDemand(demand_set="load")


def test_shared_required_condition_value_uses_the_renderer():
    from ngraph.model.selectors import parse_match_spec

    class Empty(list):
        def __repr__(self):
            return "x" * 100000

    with pytest.raises(ValueError) as error:
        parse_match_spec({"conditions": Empty()}, require_conditions=True)
    assert (
        str(error.value)
        == "match.conditions: expected at least one condition, got " + "x" * 57 + "..."
    )
    parse_match_spec(
        {"conditions": [{"attr": "x", "op": "exists"}]}, require_conditions=True
    )


def test_network_amount_refusal_keeps_its_nonstep_label():
    from ngraph import Link, Network, Node, Scenario, UnitsSettings, prepare

    def scenario(capacity):
        network = Network(nodes={n: Node(n) for n in ("A", "B")})
        network.add_link(Link("A", "B", capacity, 3))
        return Scenario(
            network,
            (MaxFlow(name="bad", source=Selector("^A$"), target=Selector("^B$")),),
            units=UnitsSettings(1),
        )

    with pytest.raises(ValueError) as error:
        prepare(scenario(1e40))
    assert (
        str(error.value)
        == "link.A|B|0.capacity: no legal resolution represents the complete prepared input/augmented graph"
    )
    prepare(scenario(8))
