"""Pool labels are row-local; compact losses include every native edge domain."""

from types import SimpleNamespace

import jsonschema
import netgraph_core as ngc
import pytest

from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    PlacementQuery,
    Scenario,
    Selector,
    UnitsSettings,
    place,
    prepare,
)
from ngraph.export import _native
from ngraph.model.network import DirectedLink
from ngraph.results import OutputSelection, SyntheticIngress
from tests.results.test_analysis_wire import VALIDATOR, project


def mixed():
    n = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    n.add_link(Link("a", "t", 32, 1))
    n.add_link(Link("b", "t", 32, 1))
    specs = DemandSet(
        "d",
        (
            DemandSpec(
                Selector("^a$"), Selector("^t$"), 16, FlowPolicyPreset.TE_ECMP_16_LSP
            ),
            DemandSpec(
                Selector("^b$"),
                Selector("^t$"),
                16,
                FlowPolicyPreset.SHORTEST_PATHS_ECMP,
            ),
        ),
    )
    return prepare(
        Scenario(n, units=UnitsSettings(1), demand_sets={"d": specs}),
        demand_sets=("d",),
    )


@pytest.mark.parametrize("details", [False, True])
@pytest.mark.parametrize("edge_output", [False, True])
def test_mixed_rows_emit_synthetic_ingress_only_for_their_own_pool(
    details, edge_output
):
    p = mixed()
    value = place(
        p,
        PlacementQuery(
            p.demand_sets["d"],
            workers=1,
            outputs=ngc.OutputOptions(edge_flows=edge_output),
            export_details=details,
        ),
    )
    rows = project(value)["analysis"]["cases"][0]["states"]["converged"]["rows"]
    pooled, plain = rows
    assert pooled["pool"]["head"] == {"pool_id": "d|0|0", "physical_sources": ["a"]}
    assert plain["pool"] is None
    assert (
        pooled["result"]["delivered_units"] == plain["result"]["delivered_units"] == 16
    )
    assert "synthetic_ingress" not in plain["result"]
    assert ("synthetic_ingress" in pooled["result"]) is edge_output
    for row in rows:
        assert ("edge_flows" in row["result"]) is edge_output
        assert ("edge_drops" in row["result"]) is details
        assert row["result"]["edge_drop_units"] == 0
    if edge_output:
        assert pooled["result"]["synthetic_ingress"]["edge_flows"] == [
            {"edge": {"pool_id": "d|0|0", "source": "a"}, "units": 16}
        ]
        assert set(pooled["result"]["synthetic_ingress"]) == (
            {"edge_flows", "call_edge_drops", "edge_drops"}
            if details
            else {"edge_flows"}
        )


@pytest.mark.parametrize("details", [False, True])
def test_positive_synthetic_drop_is_in_compact_total_and_details_are_optional(details):
    p = mixed()
    topology = p.topology
    value = place(p, PlacementQuery(p.demand_sets["d"], workers=1))
    pooled = value.cases[0].states["converged"].rows[0]
    synthetic = next(
        i for i, edge in enumerate(topology.edge_refs) if type(edge) is SyntheticIngress
    )
    physical = next(
        i for i, edge in enumerate(topology.edge_refs) if type(edge) is DirectedLink
    )
    # Native-shaped exporter fixture:10 offered =4 delivered +4 synthetic loss
    # +2 physical loss. This isolates projection, without an extra solver path.
    snapshot = SimpleNamespace(
        requested=10,
        offered=10,
        delivered=4,
        unadmitted=0,
        source_drops=0,
        edge_drops=((synthetic, 4), (physical, 2)),
        termination=pooled.result.termination,
        total_cost=None,
        call_delivered=4,
        call_undelivered=6,
        delivery_delta=4,
        call_edge_drops=((synthetic, 4), (physical, 2)),
        call_source_drops=0,
        admitted=10,
        by_source=(),
        by_tunnel=(),
        plan=None,
    )
    data = _native(
        snapshot,
        topology,
        OutputSelection(ngc.OutputOptions(), False, details),
        pooled.pool,
    )
    assert data["edge_drop_units"] == 6
    assert data["offered_units"] == data["delivered_units"] + data["edge_drop_units"]
    assert ("synthetic_ingress" in data) is details
    if details:
        assert data["synthetic_ingress"] == {
            key: [{"edge": {"pool_id": "d|0|0", "source": "a"}, "units": 4}]
            for key in ("call_edge_drops", "edge_drops")
        }
        assert data["edge_drops"] == [
            {"edge": {"link": "a|t|0", "direction": "forward"}, "units": 2}
        ]
    else:
        assert "edge_drops" not in data
    jsonschema.Draft202012Validator(
        {"$defs": VALIDATOR.schema["$defs"], "$ref": "#/$defs/NativePlacementJSON"}
    ).validate(data)
