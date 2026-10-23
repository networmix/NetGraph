"""Direct native records retain all declared values and ownership after teardown."""

import netgraph_core as ngc
import pytest

from ngraph import DemandSet, DemandSpec, Link, Network, Node, Selector
from ngraph.analysis.demands import resolve_demands
from ngraph.analysis.placement import policy_roster, remove_policies, replace_matrix
from tests.prepared import prepare_network


def fixture(kind):
    network = Network(nodes={name: Node(name) for name in ("s", "t")})
    network.add_link(Link("s", "t", 4, 3))
    network.add_link(Link("s", "t", 4, 5))
    prepared = prepare_network(network)
    topology = prepared.topology
    if kind in ("t1", "t1-lossy"):
        model = ngc.DistributedTE(ngc.TunnelCount(2))
    elif kind == "t2":
        model = ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(2),
        )
    elif kind == "pinned":
        program = ngc.ForwardingProgram.from_routes(
            topology.graph,
            [0],
            [1],
            [
                ngc.RouteDefinition(0, ngc.Path(topology.graph, [[edge]]))
                for edge in (0, 1)
            ],
        )
        model = ngc.Pinned(program)
    elif kind == "controller":
        model = ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    else:
        assert kind == "spf"
        model = ngc.ShortestPaths()
    demands = resolve_demands(
        prepared,
        DemandSet(
            "load",
            (
                DemandSpec(
                    Selector("^s$"),
                    Selector("^t$"),
                    3,
                    ngc.FlowPolicyConfig(
                        routing=model,
                        admission=ngc.Admission.LOSSY
                        if kind == "t1-lossy"
                        else ngc.Admission.LOSSLESS,
                    ),
                ),
            ),
        ),
    )
    ledger, policies = policy_roster(topology, demands.demands, topology.disabled)
    return topology, ledger, policies


def values(record):
    return {
        "admission": record.admission,
        "delivered": record.delivered,
        "destinations": record.destinations,
        "edge_drops": record.edge_drops,
        "edge_flows": record.edge_flows,
        "edge_reservations": record.edge_reservations,
        "entry_id": record.entry_id,
        "min_route_cost": record.min_route_cost,
        "offered": record.offered,
        "sources": record.sources,
    }


def oracle(kind):
    topology, ledger, policies = fixture(kind)
    try:
        (result,) = replace_matrix(ledger, policies, (3,))
        records = tuple(policies[0].records())
        if kind in ("spf", "controller"):
            entries = [(None, 3, 0)]
        else:
            entries = [(0, 2, 0), (1, 1, 1 if kind == "pinned" else 0)]
        expected = [
            {
                "admission": ngc.Admission.LOSSY
                if kind == "t1-lossy"
                else ngc.Admission.LOSSLESS,
                "delivered": amount,
                "destinations": [1],
                "edge_drops": [],
                "edge_flows": [(edge, amount)],
                "edge_reservations": [(edge, amount)]
                if kind in ("t1", "t1-lossy")
                else [],
                "entry_id": entry,
                "min_route_cost": 3 if edge == 0 else 5,
                "offered": amount if kind == "t1-lossy" else None,
                "sources": [0],
            }
            for entry, amount, edge in entries
        ]
        assert [values(record) for record in records] == expected
        assert len({record.flow_id for record in records}) == len(records)
        assert len({record.policy_id for record in records}) == 1
        policy_id = records[0].policy_id
        for record, (_, _, edge) in zip(records, entries, strict=True):
            assert type(record.policy_id) is int
            assert type(record.flow_id) is tuple and len(record.flow_id) == 2
            assert all(type(part) is int for part in record.flow_id)
            assert record.flow_id[0] == ledger.uid()
            assert ledger.record(record.flow_id).flow_id == record.flow_id
            assert policies[0].record(record.flow_id).policy_id == record.policy_id
            foreign = ngc.FlowLedger(topology.graph)
            with pytest.raises(ValueError):
                foreign.record(record.flow_id)
            assert isinstance(record.route, ngc.PredecessorDAG)
            assert record.route.graph_uid() == topology.graph.uid()
            assert [int(value) for value in record.route.via_edges()] == [edge]
            with pytest.raises(AttributeError):
                record.delivered = 99
            assert record.delivered in (1, 2, 3)
        for flag in (
            result.routes_changed,
            result.weights_changed,
            result.reservations_changed,
        ):
            assert type(flag) is bool
        # Native identical Replace preserves flags. NetGraph's matrix helper
        # deliberately removes first, so it starts a new program instead.
        identical = policies[0].replace(3)
        assert (
            not identical.routes_changed
            and not identical.weights_changed
            and not identical.reservations_changed
        )
        fresh = tuple(policies[0].records())
        assert all(record.policy_id == policy_id for record in fresh)
        assert {record.flow_id for record in fresh}.isdisjoint(
            record.flow_id for record in records
        )
        assert [values(record) for record in fresh] == expected
        assert [values(record) for record in records] == expected
    finally:
        remove_policies(policies)
    assert not ledger.carried().any() and not ledger.reserved().any()
    assert policies[0].records() == []
    assert [values(record) for record in records] == expected
    assert result.delivered == 3


@pytest.mark.parametrize(
    "kind", ["spf", "controller", "t1", "t1-lossy", "t2", "pinned"]
)
def test_complete_native_record_fields_and_teardown_lifetime(kind):
    oracle(kind)


@pytest.mark.parametrize(
    "field",
    [
        "admission",
        "delivered",
        "destinations",
        "edge_drops",
        "edge_flows",
        "edge_reservations",
        "entry_id",
        "min_route_cost",
        "offered",
        "sources",
        "route",
    ],
)
@pytest.mark.parametrize("mode", ["missing", "null", "wrong"])
def test_native_record_getter_plant_is_rejected_and_restored(monkeypatch, field, mode):
    original = getattr(ngc.FlowRecord, field)
    kind = (
        "t1-lossy"
        if mode == "null" and field == "offered"
        else "t1"
        if mode == "null" and field == "entry_id"
        else "spf"
    )

    def wrong(record):
        if mode == "null":
            return None
        value = original.__get__(record, type(record))
        if field == "admission":
            return ngc.Admission.LOSSY
        if field in ("entry_id", "offered"):
            return 0
        if field == "route":
            return None
        if isinstance(value, list):
            return (
                value + [(0, 1)]
                if field.startswith("edge_")
                else [1]
                if field == "sources"
                else [0]
            )
        return value + 1

    with monkeypatch.context() as patch:
        if mode == "missing":
            patch.delattr(ngc.FlowRecord, field)
        else:
            patch.setattr(ngc.FlowRecord, field, property(wrong))
        with pytest.raises((AssertionError, AttributeError)):
            oracle(kind)
    oracle(kind)
