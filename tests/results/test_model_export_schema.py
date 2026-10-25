"""Every routing model and allocation the exporter can write validates against results.json."""

import json
from importlib.resources import files
from io import StringIO

import jsonschema
import netgraph_core as ngc
import pytest

from ngraph import (
    CapacityQuery,
    Link,
    Network,
    Node,
    Scenario,
    Selector,
    UnitsSettings,
    capacity,
    prepare,
    write_json,
)

SCHEMA = json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)


def prepared():
    # Two sources into T: S1 directly (100) and over X (50, cost 2), S2 directly (10).
    network = Network()
    for name in ("S1", "S2", "X", "T"):
        network.add_node(Node(name))
    for source, target, cap, cost in (
        ("S1", "T", 100, 1),
        ("S1", "X", 50, 1),
        ("X", "T", 50, 1),
        ("S2", "T", 10, 1),
    ):
        network.add_link(Link(source, target, cap, cost))
    return prepare(Scenario(network, units=UnitsSettings(resolution=1)))


def models(prep):
    """(label, routing model) for every combination the Core accepts."""
    weights = [1] * prep.topology.graph.num_edges()
    for allocation in ngc.RouteAllocation.__members__.values():
        for source in (None, *ngc.SourceAllocation.__members__.values()):
            for basis in (None, *ngc.WeightBasis.__members__.values()):
                for tie in ngc.RouteTieBreak.__members__.values():
                    for multipath, parallel in (
                        (True, True),
                        (False, True),
                        (True, False),
                    ):
                        kwargs = {
                            "allocation": allocation,
                            "tie_break": tie,
                            "multipath": multipath,
                            "parallel_edges": parallel,
                        }
                        if source is not None:
                            kwargs["source_allocation"] = source
                        if basis is not None:
                            kwargs["weight_basis"] = basis
                            if basis == ngc.WeightBasis.EXPLICIT:
                                kwargs["edge_weights"] = weights
                        yield (
                            f"shortest_paths {kwargs}",
                            lambda kw=kwargs: ngc.ShortestPaths(**kw),
                        )
    for ceiling in (None, ngc.AbsoluteCost(3)):
        yield (
            f"distributed_te ceiling={ceiling}",
            lambda c=ceiling: ngc.DistributedTE(
                ngc.TunnelCount(2), cost_ceiling=c, min_unreserved_bandwidth=1
            ),
        )
    for source in ngc.SourceAllocation.__members__.values():
        for count in (None, ngc.TunnelCount(2)):
            for headroom in (False, True):
                kwargs = {"source_allocation": source, "tunnel_count": count}
                if count is not None:
                    kwargs["prefer_headroom"] = headroom
                elif headroom:
                    continue
                if source == ngc.SourceAllocation.WEIGHTED:
                    # one weight per graph node: S1 and S2 send 1:1, X and T nothing
                    kwargs["source_weights"] = [1, 1, 0, 0]
                yield (
                    f"centralized_te {kwargs}",
                    lambda kw=kwargs: ngc.CentralizedTE(**kw),
                )


def test_every_exportable_model_validates_against_the_results_schema():
    prep = prepared()
    exported, refused = {}, []
    for label, make in models(prep):
        try:
            routing = make()
            config = ngc.FlowPolicyConfig(routing=routing)
            # tunnel models are sized at a design demand
            tunnels = isinstance(routing, ngc.DistributedTE) or (
                isinstance(routing, ngc.CentralizedTE)
                and routing.tunnel_count is not None
            )
            analysis = capacity(
                prep,
                CapacityQuery(
                    Selector("^S"),
                    Selector("^T$"),
                    config,
                    offer=20,
                    design_demand=20 if tunnels else None,
                ),
            )
        except (TypeError, ValueError) as exc:  # a combination the Core refuses
            refused.append((label, str(exc)))
            continue
        output = StringIO()
        write_json(analysis, output)
        wire = json.loads(output.getvalue())
        errors = [e.message for e in VALIDATOR.iter_errors(wire)]
        assert not errors, (label, errors[:3])
        exported[label] = model = wire["analysis"]["query"]["model"]
        # Every model record carries the key: null unless the sources are weighted.
        assert ("source_weights" in model) and (
            (model["source_weights"] is None)
            == (model["source_allocation"] != "weighted")
        ), (label, model)
        if model["source_allocation"] != "weighted":
            for broken in (
                {k: v for k, v in model.items() if k != "source_weights"},
                {**model, "source_weights": [{"source": "S1", "weight": 1}]},
            ):
                wire["analysis"]["query"]["model"] = broken
                assert not VALIDATOR.is_valid(wire), (label, "accepted", broken)
    # Every value of every enumerated model field was written (and so validated) once.
    seen = {}
    for model in exported.values():
        for field in (
            "routing",
            "allocation",
            "source_allocation",
            "weight_basis",
            "tie_break",
        ):
            seen.setdefault(field, set()).add(model[field])
    assert seen["routing"] == {"shortest_paths", "distributed_te", "centralized_te"}
    assert seen["source_allocation"] >= {"equal", "optimized", "weighted"}
    assert seen["allocation"] >= {"equal", "weighted", "optimized"}
    assert seen["weight_basis"] >= {"capacity", "explicit", "residual_snapshot"}
    assert seen["tie_break"] >= {t.lower() for t in ngc.RouteTieBreak.__members__}
    # the combinations the Core refuses are its own rules (tie-breaks need one path, ...)
    assert refused and all("requires" in reason for _, reason in refused)


@pytest.mark.parametrize(
    ("links", "weights", "delivered", "recorded"),
    [
        # The inventory's probe: S1-T 100, S2-T 10, weights 1:1:0 (T sends nothing).
        (
            [("S1", "T", 100, 1), ("S2", "T", 10, 1)],
            [1, 1, 0],
            21,
            [{"source": "S1", "weight": 1}, {"source": "S2", "weight": 1}],
        ),
        # The coordinator's: A1-B 7 at cost 3, A2-B 40 at cost 1, weights 2:1:0.
        (
            [("A1", "B", 7, 3), ("A2", "B", 40, 1)],
            [2, 1, 0],
            10,
            [{"source": "A1", "weight": 2}, {"source": "A2", "weight": 1}],
        ),
    ],
)
def test_a_weighted_centralized_te_records_the_given_source_weights(
    links, weights, delivered, recorded
):
    network = Network()
    for name in dict.fromkeys(n for link in links for n in link[:2]):
        network.add_node(Node(name))
    for source, target, cap, cost in links:
        network.add_link(Link(source, target, capacity=cap, cost=cost))
    prep = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
    target = links[0][1]
    config = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.WEIGHTED, source_weights=weights
        )
    )
    analysis = capacity(
        prep,
        CapacityQuery(Selector(f"^(?!{target}$)"), Selector(f"^{target}$"), config),
    )
    assert analysis.cases[0].states["converged"].rows[0].result.delivered == delivered
    output = StringIO()
    write_json(analysis, output)
    wire = json.loads(output.getvalue())
    VALIDATOR.validate(wire)
    model = wire["analysis"]["query"]["model"]
    assert model["source_allocation"] == "weighted"
    # Each nonzero weight as a record, in node order; the zero weight is not listed.
    assert model["source_weights"] == recorded
    given = zip(prep.topology.node_names, weights, strict=True)
    assert [{"source": n, "weight": w} for n, w in given if w] == recorded
    # The schema ties the weights to weighted sources, both ways; the key is required.
    for broken in (
        {**model, "source_weights": None},
        {k: v for k, v in model.items() if k != "source_weights"},
        {**model, "source_allocation": "equal"},
        {**model, "source_weights": [{"source": "A1", "weight": 0}]},
    ):
        wire["analysis"]["query"]["model"] = broken
        with pytest.raises(jsonschema.ValidationError):
            VALIDATOR.validate(wire)


def test_shortest_paths_refuses_weighted_sources_so_none_is_exported():
    # The Core refuses WEIGHTED sources outside CentralizedTE without tunnels when the
    # policy is built, so the exporter never writes `weighted` for another model.
    network = Network()
    for name in ("A1", "A2", "B"):
        network.add_node(Node(name))
    network.add_link(Link("A1", "B", capacity=7, cost=3))
    network.add_link(Link("A2", "B", capacity=40, cost=1))
    prep = prepare(Scenario(network, units=UnitsSettings(resolution=1)))
    for routing in (
        ngc.ShortestPaths(source_allocation=ngc.SourceAllocation.WEIGHTED),
        ngc.CentralizedTE(
            source_allocation=ngc.SourceAllocation.WEIGHTED,
            source_weights=[2, 1, 0],
            tunnel_count=ngc.TunnelCount(2),
        ),
    ):
        with pytest.raises(ValueError, match="WEIGHTED requires CentralizedTE without"):
            capacity(
                prep,
                CapacityQuery(
                    Selector("^A"),
                    Selector("^B$"),
                    ngc.FlowPolicyConfig(routing=routing),
                ),
            )
