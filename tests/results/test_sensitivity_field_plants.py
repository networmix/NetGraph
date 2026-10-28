"""A signed improvement survives the exact sensitivity projection."""

import netgraph_core as ngc

from ngraph import (
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    SensitivityQuery,
    UnitsSettings,
    edge_sensitivity,
    prepare,
)
from tests.results.test_analysis_wire import project
from tests.results.test_report_field_plants import exact


def oracle():
    network = Network(nodes={name: Node(name) for name in ("a", "b", "t")})
    network.add_link(Link("a", "t", 1, 1))
    network.add_link(Link("b", "t", 10, 3))
    prepared = prepare(Scenario(network, units=UnitsSettings(1)))
    analysis = edge_sensitivity(
        prepared,
        SensitivityQuery(
            Selector("^[ab]$"),
            Selector("^t$"),
            ngc.FlowPolicyConfig(
                routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.EQUAL)
            ),
            workers=2,
            export_details=True,
        ),
    )
    # Equal sources carry1+1 at cost1+3. Removing a's outgoing edge removes
    # that source from the reachable roster, giving10 at b: delta2-10=-8.
    # Removing b leaves only a's1: delta2-1=1. Reverse edges give exact zero.
    expected = {
        "kind": "sensitivity",
        "metadata": {"workers": 2, "sampling": None},
        "outputs": {
            "native": {
                key: False
                for key in (
                    "edge_flows",
                    "residual",
                    "edge_reservations",
                    "saturated_boundary_edges",
                    "min_cut",
                )
            },
            "cost_distribution": False,
            "details": True,
        },
        "endpoints": {"sources": ["a", "b"], "destinations": ["t"]},
        "question": "lossless_bound",
        "offer_source": "unlimited",
        "baseline": {
            "request_kind": "unlimited",
            "requested_units": None,
            "call_delivered_units": 2,
            "call_undelivered_units": None,
            "delivery_delta_units": 2,
            "call_edge_drops": [],
            "call_source_drop_units": 0,
            "termination": "exhausted",
            "offered_units": None,
            "admitted_units": 2,
            "delivered_units": 2,
            "unadmitted_units": None,
            "source_drop_units": 0,
            "edge_drops": [],
            "edge_drop_units": 0,
            "by_source": [
                {
                    "source": name,
                    "offered_units": None,
                    "admitted_units": 1,
                    "delivered_units": 1,
                    "source_drop_units": 0,
                    "total_edge_drop_units": 0,
                }
                for name in ("a", "b")
            ],
            "by_tunnel": [
                {
                    "entry_id": index,
                    "head": name,
                    "status": "up",
                    "assigned_units": 1,
                    "delivered_units": 1,
                    "total_edge_drop_units": 0,
                }
                for index, name in enumerate(("a", "b"))
            ],
            "plan": None,
            "total_cost": 4,
        },
        "entries": [
            {
                "edge": {"link": link, "direction": "forward"},
                "delivery_reduction_units": delta,
            }
            for link, delta in (("a|t|0", -8), ("b|t|0", 1))
        ],
    }
    wire = project(analysis)["analysis"]
    del wire["query"]
    exact(wire, expected)


def test_signed_sensitivity_fields_are_exact():
    oracle()
