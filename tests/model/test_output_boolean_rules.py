"""Output selectors use the same boolean input rule as domain records."""

import pytest

from ngraph.dsl.inputs import outputs
from ngraph.workflow import MaximumSupportedDemand, TunnelCountAnalysis


@pytest.mark.parametrize("raw", [False, True, 0, "false", None])
@pytest.mark.parametrize("adapter", [MaximumSupportedDemand, TunnelCountAnalysis])
def test_workflow_output_details_use_the_boolean_rule(adapter, raw):
    if type(raw) is bool:
        answer = adapter.yaml_arguments({"outputs": {"details": raw}}, "ask")
        assert answer["export_details"] is raw
    else:
        with pytest.raises(ValueError, match="workflow step ask.outputs.details"):
            adapter.yaml_arguments({"outputs": {"details": raw}}, "ask")


@pytest.mark.parametrize(
    "field",
    [
        "edge_flows",
        "residual",
        "edge_reservations",
        "saturated_boundary_edges",
        "min_cut",
    ],
)
def test_native_output_fields_use_the_boolean_rule(field):
    assert getattr(outputs({field: True}, "answer")[0], field) is True
    assert getattr(outputs({field: False}, "answer")[0], field) is False
    with pytest.raises(ValueError, match="answer." + field):
        outputs({field: 0}, "answer")


@pytest.mark.parametrize(
    "kind,field",
    [
        ("shortest_paths", "multipath"),
        ("shortest_paths", "parallel_edges"),
        ("distributed_te", "parallel_edges"),
        ("centralized_te", "prefer_headroom"),
    ],
)
@pytest.mark.parametrize("raw", [False, True, 0, "false"])
def test_routing_boolean_fields_are_checked_directly(kind, field, raw):
    from ngraph.dsl.inputs import policy

    routing = {"type": kind, field: raw}
    if kind == "distributed_te":
        routing["tunnel_count"] = {"per_head": 1}
    elif kind == "centralized_te":
        routing["source_allocation"] = "equal"
    if type(raw) is bool:
        assert (
            getattr(policy({"model": {"routing": routing}}, "ask").routing, field)
            is raw
        )
    else:
        with pytest.raises(ValueError, match=field):
            policy({"model": {"routing": routing}}, "ask")


@pytest.mark.parametrize("raw", [False, True, 0, "false"])
def test_tunnel_count_up_to_uses_the_shared_flag_rule(raw):
    from ngraph.dsl.inputs import tunnel_count

    if type(raw) is bool:
        answer = tunnel_count({"per_head": 2, "up_to": raw}, "count")
        assert answer.per_head == 2 and answer.up_to is raw
    else:
        with pytest.raises(ValueError, match="count.up_to"):
            tunnel_count({"per_head": 2, "up_to": raw}, "count")
