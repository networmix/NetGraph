"""Native vectors over a graph augmented by a pooled demand set export under public names.

A finite TE ingress pool adds a private head node (and its attachment edges) to the prepared
graph. Every exporter path that maps a node or edge vector of that graph to names is checked
here: declared source weights, explicit edge weights (ShortestPaths and named pinned
weights), excluded nodes and edges of sensitivity, path and tunnel-count questions, and the
sources, tunnels and plan heads of a pooled placement. Each export validates against
results.json, and no declared positive entry is dropped.
"""

import json
from importlib.resources import files
from io import StringIO

import jsonschema
import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    DirectedLink,
    EdgeWeight,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    PathQuery,
    PinnedRoutes,
    PlacementQuery,
    RouteSpec,
    Scenario,
    Selector,
    SensitivityQuery,
    SupportSpec,
    TunnelCountQuery,
    UnitsSettings,
    WeightSpec,
    capacity,
    edge_sensitivity,
    paths,
    place,
    prepare,
    tunnel_counts,
    write_json,
)

SCHEMA = json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def augmented():
    # A-T 5 and B-T 8; the pooled set over ^(A|B)$ adds the private head node 3.
    network = Network(nodes={name: Node(name) for name in ("A", "B", "T")})
    network.add_link(Link("A", "T", 5, 1))
    network.add_link(Link("B", "T", 8, 1))
    pooled = DemandSet(
        "pool",
        (
            DemandSpec(
                Selector("^(A|B)$"),
                Selector("^T$"),
                4,
                FlowPolicyPreset.TE_ECMP_16_LSP,
                id="p",
            ),
        ),
    )
    pinned = DemandSet(
        "pinned",
        (
            DemandSpec(
                Selector("^A$"),
                Selector("^T$"),
                2,
                PinnedRoutes(
                    ("direct",),
                    allocation=ngc.RouteAllocation.WEIGHTED,
                    weight_basis=ngc.WeightBasis.EXPLICIT,
                    edge_weights="w",
                ),
                id="q",
            ),
        ),
    )
    scenario = Scenario(
        network,
        demand_sets={"pool": pooled, "pinned": pinned},
        routes={"direct": RouteSpec("A", support="dag")},
        supports={"dag": SupportSpec((DirectedLink("A|T|0", "forward"),))},
        weights={"w": WeightSpec((EdgeWeight(DirectedLink("A|T|0", "forward"), 3),))},
        units=UnitsSettings(1),
    )
    prep = prepare(scenario, demand_sets=("pool", "pinned"))
    topology = prep.topology
    assert len(topology.node_names) == 3 and topology.graph.num_nodes() == 4
    ((pool_id, head),) = topology.pool_heads.items()
    assert head == 3
    return prep, pool_id


def wire_of(analysis):
    output = StringIO()
    write_json(analysis, output)
    wire = json.loads(output.getvalue())
    VALIDATOR.validate(wire)
    return wire


def weighted(weights):
    return ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.WEIGHTED, source_weights=weights
        )
    )


def test_a_weight_on_the_pool_head_is_named_by_its_pool():
    prep, pool_id = augmented()
    analysis = capacity(
        prep,
        CapacityQuery(
            Selector("^A$"), Selector("^T$"), weighted([2, 0, 0, 5]), offer=4
        ),
    )
    assert analysis.cases[0].states["converged"].rows[0].result.delivered == 4
    wire = wire_of(analysis)
    model = wire["analysis"]["query"]["model"]
    assert model["source_weights"] == [
        {"source": "A", "weight": 2},
        {"pool_id": pool_id, "weight": 5},
    ]
    # Each record names exactly one of a physical source and a pool.
    for broken in (
        [{"weight": 5}],
        [{"source": "A", "pool_id": pool_id, "weight": 5}],
    ):
        model["source_weights"] = broken
        assert not VALIDATOR.is_valid(wire), broken


@pytest.mark.parametrize("graph", ["plain", "augmented"])
def test_all_zero_weights_export_an_empty_list(graph):
    if graph == "plain":
        network = Network(nodes={name: Node(name) for name in ("A", "B", "T")})
        network.add_link(Link("A", "T", 5, 1))
        network.add_link(Link("B", "T", 8, 1))
        prep = prepare(Scenario(network, units=UnitsSettings(1)))
    else:
        prep, _ = augmented()
    zeros = [0] * prep.topology.graph.num_nodes()
    analysis = capacity(
        prep, CapacityQuery(Selector("^A$"), Selector("^T$"), weighted(zeros), offer=4)
    )
    row = analysis.cases[0].states["converged"].rows[0].result
    assert row.delivered == 0 and row.termination == ngc.Termination.NO_ACTIVE_WEIGHT
    assert wire_of(analysis)["analysis"]["query"]["model"]["source_weights"] == []


def test_explicit_edge_weights_name_every_edge_attachments_included():
    prep, pool_id = augmented()
    topology = prep.topology
    count = topology.graph.num_edges()
    assert count > len([ref for ref in topology.edge_refs if type(ref) is DirectedLink])
    given = list(range(1, count + 1))
    config = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights=given,
        )
    )
    analysis = capacity(prep, CapacityQuery(Selector("^A$"), Selector("^T$"), config))
    rows = wire_of(analysis)["analysis"]["query"]["model"]["edge_weights"]
    assert [row["value"] for row in rows] == given
    assert {"pool_id": pool_id} in [
        {"pool_id": row["edge"]["pool_id"]} for row in rows if "pool_id" in row["edge"]
    ]


def test_named_pinned_weights_name_every_edge_attachments_included():
    prep, _ = augmented()
    analysis = place(prep, PlacementQuery(prep.demand_sets["pinned"]))
    (demand,) = wire_of(analysis)["analysis"]["query"]["demands"]
    weights = demand["model"]["edge_weights"]
    assert len(weights) == prep.topology.graph.num_edges()
    assert [
        w["value"]
        for w in weights
        if w["edge"] == {"link": "A|T|0", "direction": "forward"}
    ] == [3]


def test_an_excluded_pool_head_is_named_in_every_query_that_records_a_mask():
    prep, pool_id = augmented()
    topology = prep.topology
    attachments = [
        i for i, ref in enumerate(topology.edge_refs) if type(ref) is not DirectedLink
    ]
    mask = topology.graph.eligibility(excluded_nodes=[3], excluded_edges=attachments)
    analyses = [
        edge_sensitivity(
            prep,
            SensitivityQuery(
                Selector("^A$"),
                Selector("^T$"),
                ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
                eligibility=mask,
            ),
        ),
        paths(
            prep,
            PathQuery(
                Selector("^A$"),
                Selector("^T$"),
                options=ngc.SpfOptions(ngc.Direction.FORWARD, eligibility=mask),
            ),
        ),
        tunnel_counts(
            prep,
            TunnelCountQuery(
                prep.demand_sets["pool"],
                counts=(2,),
                design_demand=4,
                offer=0,  # the pool's lossy offer budget
                eligibility=mask,
            ),
        ),
    ]
    for analysis in analyses:
        query = wire_of(analysis)["analysis"]["query"]
        assert query["excluded_nodes"] == [{"pool_id": pool_id}], query["kind"]
        assert len(query["excluded_edges"]) == len(attachments), query["kind"]


def test_a_pooled_placement_names_its_pool_head_in_sources_tunnels_and_plan():
    prep, pool_id = augmented()
    every = ngc.OutputOptions(
        edge_flows=True,
        residual=True,
        edge_reservations=True,
        saturated_boundary_edges=True,
    )
    analysis = place(
        prep,
        PlacementQuery(prep.demand_sets["pool"], outputs=every, export_details=True),
    )
    (row,) = wire_of(analysis)["analysis"]["cases"][0]["states"]["converged"]["rows"]
    result = row["result"]
    heads = [s["source"] for s in result["by_source"]] + [
        t["head"] for t in result["by_tunnel"]
    ]
    assert heads and all(h["pool_id"] == pool_id for h in heads)
    assert result["plan"]["heads_with_capacity"][0]["pool_id"] == pool_id
    assert "synthetic_ingress" in result


def test_paths_on_the_augmented_graph_name_physical_nodes():
    prep, _ = augmented()
    for options in (ngc.SpfOptions(ngc.Direction.FORWARD), ngc.KspOptions(2)):
        wire = wire_of(
            paths(prep, PathQuery(Selector("^A$"), Selector("^T$"), options=options))
        )
        (path,) = wire["analysis"]["rows"][0]["paths"][:1]
        assert (path["source"], path["destination"]) == ("A", "T")
