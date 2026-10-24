"""The tunnel-count analysis as JSON, its failures and its class names.

The expected JSON is projected here from the native fields and the topology's
labels, independently of the exporter, and checked against the schema.
"""

import io
import json
import logging
from importlib import resources

import jsonschema
import netgraph_core as ngc
import pytest

import ngraph
import ngraph.workflow
from ngraph import (
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    TunnelCountQuery,
    UnitsSettings,
    prepare,
    run,
    tunnel_counts,
    write_json,
)
from ngraph.analysis import counts
from ngraph.model.network import DirectedLink
from ngraph.workflow import TunnelCountAnalysis

TE16 = FlowPolicyPreset.TE_ECMP_16_LSP
SCHEMA = json.loads(
    resources.files("ngraph.schemas").joinpath("results.json").read_text()
)


def pooled(steps=True):
    net = Network(nodes={n: Node(n) for n in ("S", "T", "a", "b")})
    net.add_link(Link("S", "T", 1, 1))
    net.add_link(Link("S", "T", 100, 2))
    net.add_link(Link("a", "T", 1, 1))
    net.add_link(Link("b", "T", 100, 1))
    tiny = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.EQUAL,
            tunnel_count=ngc.TunnelCount(16),
        )
    )
    specs = (
        DemandSpec(Selector("^S$"), Selector("^T$"), 0, TE16, id="pooled"),
        DemandSpec(Selector("^(a|b)$"), Selector("^T$"), 0, tiny, id="tiny"),
    )
    counted = (
        TunnelCountAnalysis(
            "counts", demand_set="d", counts=(2,), up_to=3, design_demand=2, offer=1000
        ),
    )
    return prepare(
        Scenario(
            net,
            counted if steps else (),
            demand_sets={"d": DemandSet("d", specs)},
            units=UnitsSettings(1),
        ),
        demand_sets=("d",),
    )


def label(topology, edge):
    ref = topology.edge_refs[edge]
    if type(ref) is DirectedLink:
        return {"link": ref.link, "direction": ref.direction}
    return {"pool_id": ref.pool_id, "source": ref.source}


def source(topology, node, pool):
    if node < len(topology.node_names):
        return topology.node_names[node]
    return {
        "pool_id": pool.head.pool_id,
        "physical_sources": list(pool.head.physical_sources),
    }


def expected_row(topology, row, details, edge_flows):
    r, p, pool = row.result, row.result.plan, row.pool
    physical = lambda pairs: [  # noqa: E731
        {"edge": label(topology, e), "units": int(u)}
        for e, u in pairs
        if type(topology.edge_refs[e]) is DirectedLink
    ]
    synthetic = lambda pairs: [  # noqa: E731
        {"edge": label(topology, e), "units": int(u)}
        for e, u in pairs
        if type(topology.edge_refs[e]) is not DirectedLink
    ]
    result = {
        "request_kind": "finite",
        "requested_units": r.requested,
        "offered_units": r.offered,
        "delivered_units": r.delivered,
        "unadmitted_units": r.unadmitted,
        "source_drop_units": r.source_drops,
        "edge_drop_units": sum(u for _, u in r.edge_drops),
        "termination": r.termination.name.lower(),
        "total_cost": r.total_cost,
    }
    if details:
        result.update(
            call_delivered_units=r.call_delivered,
            call_undelivered_units=r.call_undelivered,
            delivery_delta_units=r.delivery_delta,
            call_edge_drops=physical(r.call_edge_drops),
            call_source_drop_units=r.call_source_drops,
            admitted_units=r.admitted,
            edge_drops=physical(r.edge_drops),
            by_source=[
                {
                    "source": source(topology, s.source, pool),
                    "offered_units": s.offered,
                    "admitted_units": s.admitted,
                    "delivered_units": s.delivered,
                    "source_drop_units": s.source_drops,
                    "total_edge_drop_units": s.total_edge_drops,
                }
                for s in r.by_source
            ],
            by_tunnel=[
                {
                    "entry_id": t.entry_id,
                    "head": source(topology, t.head, pool),
                    "status": t.status.name.lower(),
                    "assigned_units": t.assigned,
                    "delivered_units": t.delivered,
                    "total_edge_drop_units": t.total_edge_drops,
                }
                for t in r.by_tunnel
            ],
        )
    synthetic_section = {}
    if details:
        synthetic_section.update(
            call_edge_drops=synthetic(r.call_edge_drops),
            edge_drops=synthetic(r.edge_drops),
        )
    if edge_flows:
        flows = list(enumerate(r.edge_flows))
        result["edge_flows"] = physical(flows)
        synthetic_section["edge_flows"] = synthetic(flows)
    if pool is not None and (edge_flows or any(synthetic_section.values())):
        result["synthetic_ingress"] = synthetic_section
    return {
        "id": row.id,
        "base_id": row.base_id,
        "endpoints": {
            "sources": list(row.endpoints.sources),
            "destinations": list(row.endpoints.destinations),
        },
        "count": row.count,
        "up_to": row.up_to,
        "pool": None
        if pool is None
        else {
            "head": {
                "pool_id": pool.head.pool_id,
                "physical_sources": list(pool.head.physical_sources),
            },
            "offer_limit_units": pool.offer_limit_units,
            "synthetic_ingress_cost": 1,
        },
        "lossless_at_design_units": row.lossless_at_design_units,
        "physical_tunnel_cost": row.physical_tunnel_cost,
        "plan": {
            "tunnels_per_head": p.tunnels_per_head,
            "design_kind": "finite",
            "design_demand_units": p.design_demand,
            "design_by_head": [
                {"head": source(topology, h, pool), "units": u}
                for h, u in p.design_by_head
            ],
            "total_reserved_bandwidth_units": p.total_reserved_bandwidth,
            "heads_with_capacity": [
                source(topology, h, pool) for h in p.heads_with_capacity
            ],
            "insufficient_resolution": p.insufficient_resolution,
            "max_fractional_bandwidth_per_tunnel": {
                "numerator": p.max_fractional_bandwidth_per_tunnel.numerator,
                "denominator": p.max_fractional_bandwidth_per_tunnel.denominator,
            },
            "max_bandwidth_per_tunnel_units": p.max_bandwidth_per_tunnel,
            "planned_bandwidth_per_tunnel_units": p.planned_bandwidth_per_tunnel,
            "total_planned_bandwidth_units": p.total_planned_bandwidth,
            "total_tunnel_cost": p.total_tunnel_cost,
            "headroom_penalty": p.headroom_penalty,
            "max_lossless_offer_units": p.max_lossless_offer,
        },
        "result": result,
    }


def exported(analysis):
    buffer = io.StringIO()
    write_json(analysis, buffer)
    text = buffer.getvalue()
    document = json.loads(text)
    jsonschema.validate(document, SCHEMA)
    return text, document["analysis"]


@pytest.mark.parametrize(
    ("details", "edge_flows"),
    [(False, False), (True, False), (True, True), (False, True)],
)
def test_rows_project_every_field_once(details, edge_flows):
    prep = pooled()
    analysis = tunnel_counts(
        prep,
        TunnelCountQuery(
            prep.demand_sets["d"],
            (2,),
            2,
            1000 if not details else 1000,
            up_to=3,
            outputs=ngc.OutputOptions(edge_flows=edge_flows),
            export_details=details,
        ),
    )
    text, data = exported(analysis)
    assert data["kind"] == "tunnel_counts"
    assert data["outputs"] == {
        "native": {
            "edge_flows": edge_flows,
            "residual": False,
            "edge_reservations": False,
            "saturated_boundary_edges": False,
            "min_cut": False,
        },
        "cost_distribution": False,
        "details": details,
    }
    topology = prep.topology
    assert data["rows"] == [
        expected_row(topology, row, details, edge_flows) for row in analysis.rows
    ]
    first = data["rows"][0]
    # The pool row of PLAN 4.3: 1 + 100 delivered, the narrow link drops 499, the wide 400.
    assert (first["count"], first["up_to"], first["result"]["delivered_units"]) == (
        2,
        False,
        101,
    )
    assert first["result"]["edge_drop_units"] == 899
    assert (first["plan"]["total_tunnel_cost"], first["physical_tunnel_cost"]) == (5, 3)
    assert '"headroom_penalty":4350801869,' in text
    # The tiny row's up-to limit 3 chooses 1 tunnel per head.
    limit = data["rows"][3]
    assert (limit["count"], limit["up_to"], limit["plan"]["tunnels_per_head"]) == (
        3,
        True,
        1,
    )
    assert all("plan" not in row["result"] for row in data["rows"])


def test_the_question_records_the_demands_and_the_mask():
    prep = pooled()
    mask = prep.topology.graph.eligibility(
        excluded_nodes=[prep.topology.node_id_by_name["a"]]
    )
    analysis = tunnel_counts(
        prep,
        TunnelCountQuery(
            prep.demand_sets["d"], (4, 2), 2, 10, up_to=3, eligibility=mask
        ),
    )
    _, data = exported(analysis)
    query = data["query"]
    assert {key: query[key] for key in ("kind", "demand_set", "counts", "up_to")} == {
        "kind": "tunnel_counts",
        "demand_set": "d",
        "counts": [4, 2],
        "up_to": 3,
    }
    assert (query["design_demand"], query["offer"]) == (2.0, 10.0)
    assert [d["id"] for d in query["demands"]] == ["pooled", "tiny"]
    assert query["demands"][0]["model"]["tunnel_count"] == {
        "per_head": 16,
        "up_to": False,
    }
    assert query["demands"][1]["model"]["prefer_headroom"] is False
    assert query["excluded_nodes"] == ["a"]
    assert {edge["link"] for edge in query["excluded_edges"]} == {"a|T|0"}


def test_a_run_writes_the_step_with_its_question():
    result = run(pooled())
    text = io.StringIO()
    write_json(result, text)
    document = json.loads(text.getvalue())
    jsonschema.validate(document, SCHEMA)
    (step,) = document["steps"]
    assert (step["step_type"], step["question"]["kind"], step["result"]["kind"]) == (
        "TunnelCountAnalysis",
        "tunnel_counts",
        "tunnel_counts",
    )
    assert "query" not in step["result"]
    assert result.steps[0].step_type == "TunnelCountAnalysis"


def text(result):
    out = io.StringIO()
    write_json(result, out)
    return out.getvalue()


def test_a_failure_publishes_nothing_and_a_retry_matches(monkeypatch):
    prep = pooled()
    clean = text(run(prep))

    def fail_at(module, name, at):
        real = getattr(module, name)
        calls = []

        def failing(*args, **kwargs):
            calls.append(1)
            if len(calls) == at:
                raise MemoryError("forced")
            return real(*args, **kwargs)

        monkeypatch.setattr(module, name, failing)
        # Run-time errors pass through unlabelled; the retry's whole document equals
        # the clean run's, so the failed run left nothing behind.
        with pytest.raises(MemoryError, match="^forced$"):
            run(prep)
        monkeypatch.setattr(module, name, real)
        assert text(run(prep)) == clean

    # The second native call, the third row, and the analysis record itself.
    fail_at(ngc, "evaluate_pairs", 2)
    fail_at(counts, "TunnelCountRow", 3)
    fail_at(counts, "TunnelCountAnalysis", 1)


def test_texts_name_the_class_by_module(caplog):
    assert ngraph.TunnelCountAnalysis is not ngraph.workflow.TunnelCountAnalysis
    step = TunnelCountAnalysis(
        "c", demand_set="d", counts=(1,), design_demand=1, offer=1
    )
    with pytest.raises(
        TypeError,
        match=r"^unregistered result type ngraph\.workflow\.tunnel_count_step\.TunnelCountAnalysis$",
    ):
        ngraph.export.owned_step_result(step)
    with caplog.at_level(logging.INFO, logger="ngraph.workflow.base"):
        run(pooled())
    assert any(
        "(ngraph.workflow.tunnel_count_step.TunnelCountAnalysis)" in message
        for message in caplog.messages
    )
