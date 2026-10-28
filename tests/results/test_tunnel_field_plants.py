"""Hand-derived physical T1 and pooled T2 result projections."""

import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
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
    capacity,
    place,
    prepare,
)
from tests.results.test_analysis_wire import project


def edge(link, direction="forward"):
    return {"link": link, "direction": direction}


def amounts(references, values):
    return [
        {"edge": ref, "units": value}
        for ref, value in zip(references, values, strict=True)
    ]


def oracle(kind):
    network = Network()
    if kind == "physical-t1":
        network.nodes.update({name: Node(name) for name in ("a", "t")})
        network.add_link(Link("a", "t", 5, 1))
        network.add_link(Link("a", "t", 5, 2))
        prepared = prepare(Scenario(network, units=UnitsSettings(1)))
        analysis = capacity(
            prepared,
            CapacityQuery(
                Selector("^a$"),
                Selector("^t$"),
                ngc.FlowPolicyConfig(
                    routing=ngc.DistributedTE(ngc.TunnelCount(2)),
                    admission=ngc.Admission.LOSSY,
                ),
                offer=10,
                design_demand=8,
                outputs=ngc.OutputOptions(edge_flows=True, edge_reservations=True),
                workers=1,
                export_details=True,
            ),
        )
        head, offer, count = "a", 10, 2
        references = [
            edge("a|t|0"),
            edge("a|t|1"),
            edge("a|t|0", "reverse"),
            edge("a|t|1", "reverse"),
        ]
        flows, reservations = (5, 5, 0, 0), (4, 4, 0, 0)
        plan = {
            "tunnels_per_head": 2,
            "design_kind": "finite",
            "design_demand_units": 8,
            "design_by_head": [{"head": "a", "units": 8}],
            "total_reserved_bandwidth_units": 8,
            "heads_with_capacity": None,
            "insufficient_resolution": None,
            "max_fractional_bandwidth_per_tunnel": None,
            "max_bandwidth_per_tunnel_units": None,
            "planned_bandwidth_per_tunnel_units": None,
            "total_planned_bandwidth_units": None,
            "total_tunnel_cost": None,
            "headroom_penalty": None,
            "max_lossless_offer_units": None,
        }
    else:
        assert kind == "pooled-t2"
        network.nodes.update({name: Node(name) for name in ("s1", "s2", "t")})
        network.add_link(Link("s1", "t", 16, 1))
        network.add_link(Link("s2", "t", 32, 3))
        demand_set = DemandSet(
            "load",
            (
                DemandSpec(
                    Selector("^s"),
                    Selector("^t$"),
                    32,
                    FlowPolicyPreset.TE_ECMP_16_LSP,
                    id="service",
                ),
            ),
        )
        prepared = prepare(
            Scenario(network, demand_sets={"load": demand_set}, units=UnitsSettings(1)),
            demand_sets=("load",),
        )
        analysis = place(
            prepared,
            PlacementQuery(
                prepared.demand_sets["load"],
                workers=1,
                outputs=ngc.OutputOptions(edge_flows=True, edge_reservations=True),
                export_details=True,
                states=("converged",),
            ),
        )
        head = {"pool_id": "service|0", "physical_sources": ["s1", "s2"]}
        offer, count = 32, 16
        references = [
            edge("s1|t|0"),
            edge("s2|t|0"),
            edge("s1|t|0", "reverse"),
            edge("s2|t|0", "reverse"),
        ]
        flows, reservations = (16, 16, 0, 0), (0, 0, 0, 0)
        # s*=max min(16/n,32/(16-n))=32/11; U=floor(s*)=2.
        # u=ceil(32/16)=2. Eight slots on each route minimize headroom,
        # J=8*2+8*4=48. Offer33 overloads the first cheap RR entry, so F=32.
        penalty = 2 * sum(
            (2**32 * slot * 2) // baseline
            for baseline in (16, 32)
            for slot in range(1, 9)
        )
        plan = {
            "tunnels_per_head": 16,
            "design_kind": "finite",
            "design_demand_units": 32,
            "design_by_head": [{"head": head, "units": 32}],
            "total_reserved_bandwidth_units": 0,
            "heads_with_capacity": [head],
            "insufficient_resolution": False,
            "max_fractional_bandwidth_per_tunnel": {"numerator": 32, "denominator": 11},
            "max_bandwidth_per_tunnel_units": 2,
            "planned_bandwidth_per_tunnel_units": 2,
            "total_planned_bandwidth_units": 32,
            "total_tunnel_cost": 48,
            "headroom_penalty": penalty,
            "max_lossless_offer_units": 32,
        }
    # LOSSLESS records no sent offer, even for a finite request.
    offered = None if kind == "pooled-t2" else offer
    expected = {
        "request_kind": "finite",
        "requested_units": offer,
        "call_delivered_units": offer,
        "call_undelivered_units": 0,
        "delivery_delta_units": offer,
        "call_edge_drops": [],
        "call_source_drop_units": 0,
        "termination": "complete",
        "offered_units": offered,
        "admitted_units": offer,
        "delivered_units": offer,
        "unadmitted_units": 0,
        "source_drop_units": 0,
        "edge_drops": [],
        "edge_drop_units": 0,
        "by_source": [
            {
                "source": head,
                "offered_units": offered,
                "admitted_units": offer,
                "delivered_units": offer,
                "source_drop_units": 0,
                "total_edge_drop_units": 0,
            }
        ],
        "by_tunnel": [
            {
                "entry_id": i,
                "head": head,
                "status": "up",
                "assigned_units": offer // count,
                "delivered_units": offer // count,
                "total_edge_drop_units": 0,
            }
            for i in range(count)
        ],
        "plan": plan,
        "total_cost": None,
        "edge_flows": amounts(references, flows),
        "edge_reservations": amounts(references, reservations),
    }
    if kind == "pooled-t2":
        ingresses = [
            {"pool_id": "service|0", "source": source} for source in ("s1", "s2")
        ]
        expected["synthetic_ingress"] = {
            "call_edge_drops": [],
            "edge_drops": [],
            "edge_flows": amounts(ingresses, (16, 16)),
            "edge_reservations": amounts(ingresses, (0, 0)),
        }
    row = project(analysis)["analysis"]["cases"][0]["states"]["converged"]["rows"][0]
    assert row["result"] == expected
    if kind == "pooled-t2":
        assert row["pool"] == {
            "head": head,
            "offer_limit_units": 0,
            "synthetic_ingress_cost": 1,
        }
    else:
        assert row["pool"] is None


@pytest.mark.parametrize("kind", ["physical-t1", "pooled-t2"])
def test_tunnel_fields_follow_hand_derivation(kind):
    oracle(kind)
