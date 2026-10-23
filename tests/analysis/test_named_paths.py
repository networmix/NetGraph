"""Nonuniform path choices, canonical group merging and exact query echoes."""

from fractions import Fraction

import netgraph_core as ngc
import pytest

from ngraph.analysis.paths import PathQuery, paths
from ngraph.analysis.topology import eligibility
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import Selector
from tests.prepared import prepare_network
from tests.question import asked


def prepared():
    network = Network()
    for name in ("s1", "s2", "b", "t"):
        network.add_node(Node(name))
    network.add_link(Link("s1", "b", 4, 1))
    network.add_link(Link("s1", "b", 4, 2))
    network.add_link(Link("b", "t", 4, 2))
    network.add_link(Link("s1", "t", 3, 5))
    network.add_link(Link("s2", "t", 2, 3))
    return prepare_network(network)


def named_hops(topology, path):
    return tuple(tuple(topology.edge_refs[edge] for edge in hop) for hop in path.hops())


def test_spf_combine_keeps_global_minimum_and_costs_only_skips_expansion():
    context = prepared()
    query = PathQuery(Selector("^s"), Selector("^t$"))
    result = paths(context, query)
    (row,) = result.rows
    assert row.cost == 3
    assert [(path.source(), path.destination(), path.cost()) for path in row.paths] == [
        (1, 3, 3),
        (2, 3, 3),
    ]
    question = asked(result)
    assert question["min_residual"] == 1
    assert question["residual_units"] is None
    assert question["source"]["path"] == "^s"
    assert question["target"]["path"] == "^t$"
    assert result.query.mode == "combine"
    costs = paths(context, PathQuery(Selector("^s"), Selector("^t$"), costs_only=True))
    assert costs.rows[0].cost == 3 and costs.rows[0].paths is None


def test_ksp_cross_pair_rank_and_inclusive_ceiling():
    context = prepared()
    query = PathQuery(
        Selector("^s"),
        Selector("^t$"),
        options=ngc.KspOptions(3, cost_ceiling=ngc.AbsoluteCost(4)),
    )
    result = paths(context, query)
    (row,) = result.rows
    assert [path.cost() for path in row.paths] == [3, 3, 4]
    assert [context.topology.node_names[path.source()] for path in row.paths] == [
        "s1",
        "s2",
        "s1",
    ]
    assert asked(result)["k"] == 3 and asked(result)["min_residual"] is None
    assert asked(result)["cost_ceiling"]["absolute"] == 4
    stretched = paths(
        context,
        PathQuery(
            Selector("^s1$"),
            Selector("^t$"),
            options=ngc.KspOptions(5, cost_ceiling=ngc.CostStretch(Fraction(4, 3))),
        ),
    )
    assert [path.cost() for path in stretched.rows[0].paths] == [3, 4]


def test_residual_minimum_changes_route_and_question():
    context = prepared()
    topology = context.topology
    residual = [1] * topology.graph.num_edges()
    results = [
        paths(
            context,
            PathQuery(
                Selector("^s1$"),
                Selector("^t$"),
                options=ngc.SpfOptions(
                    ngc.Direction.FORWARD, residual=residual, min_residual=minimum
                ),
            ),
        )
        for minimum in (1, 2)
    ]
    assert results[0].rows[0].cost == 3
    assert results[1].rows[0].cost is None
    assert results[1].rows[0].paths == ()
    assert [asked(result)["min_residual"] for result in results] == [1, 2]
    assert all(asked(result)["residual_units"] == list(residual) for result in results)


def test_native_option_integer_types_and_index_controls_keep_native_error_classes():
    import numpy as np

    context = prepared()
    topology = context.topology
    source = topology.node_id_by_name["s1"]
    destination = topology.node_id_by_name["t"]

    class Index:
        def __index__(self):
            return 1

    for value in (True, np.bool_(True), 1.0, "1"):
        options = ngc.SpfOptions(ngc.Direction.FORWARD, min_residual=value)
        with pytest.raises(TypeError):
            ngc.spf(topology.graph, source, options)
        with pytest.raises(TypeError, match="min_residual"):
            paths(
                context, PathQuery(Selector("^s1$"), Selector("^t$"), options=options)
            )
        options = ngc.KspOptions(k=value)
        with pytest.raises(TypeError):
            ngc.ksp(topology.graph, source, destination, options)
        with pytest.raises(TypeError, match="paths.k"):
            paths(
                context, PathQuery(Selector("^s1$"), Selector("^t$"), options=options)
            )
    for value in (Index(), np.int64(1)):
        result = paths(
            context,
            PathQuery(
                Selector("^s1$"),
                Selector("^t$"),
                options=ngc.SpfOptions(ngc.Direction.FORWARD, min_residual=value),
            ),
        )
        assert asked(result)["min_residual"] == 1 and result.rows[0].cost == 3
        result = paths(
            context,
            PathQuery(
                Selector("^s1$"), Selector("^t$"), options=ngc.KspOptions(k=value)
            ),
        )
        assert asked(result)["k"] == 1 and result.rows[0].cost == 3


def test_directed_mask_node_mask_limits_diagonal_overlap_and_legal_controls():
    context = prepared()
    topology = context.topology
    forward, reverse = topology.edges_by_link["s1|b|0"]
    directed = eligibility(topology, excluded_edges=[forward])
    result = paths(
        context,
        PathQuery(
            Selector("^s1$"),
            Selector("^t$"),
            options=ngc.SpfOptions(ngc.Direction.FORWARD, eligibility=directed),
            max_paths=1,
            split_parallel_edges=True,
        ),
    )
    assert result.rows[0].cost == 4
    assert len(result.rows[0].paths) == 1
    assert directed.edge_allowed()[reverse]
    masked = paths(
        context,
        PathQuery(
            Selector("^s1$"),
            Selector("^t$"),
            options=ngc.SpfOptions(
                ngc.Direction.FORWARD,
                eligibility=eligibility(topology, excluded_nodes=["b"]),
            ),
        ),
    )
    assert masked.rows[0].cost == 5
    diagonal = paths(context, PathQuery(Selector("^b$"), Selector("^b$")))
    assert diagonal.rows[0].kind == "self" and diagonal.rows[0].cost == 0
    with pytest.raises(ValueError, match="overlap.*s1"):
        paths(context, PathQuery(Selector("^s"), Selector("^s1$")))
    assert (
        paths(context, PathQuery(Selector("^s1$"), Selector("^t$"))).rows[0].cost == 3
    )


@pytest.mark.parametrize(
    "options,extra,message",
    [
        (ngc.SpfOptions(ngc.Direction.REVERSE), {}, "FORWARD"),
        (ngc.SpfOptions(ngc.Direction.FORWARD, targets=[0]), {}, "targets=None"),
        (ngc.KspOptions(2), {"max_paths": 1}, "SPF-only"),
        (ngc.KspOptions(2), {"split_parallel_edges": False}, "SPF-only"),
        (ngc.KspOptions(2, cost_ceiling=ngc.AbsoluteCost(-1)), {}, "nonnegative"),
        (
            ngc.KspOptions(2, cost_ceiling=ngc.CostStretch(Fraction(1, 2))),
            {},
            "at least one",
        ),
    ],
)
def test_path_option_refusals_have_success_controls(options, extra, message):
    with pytest.raises(ValueError, match=message):
        PathQuery(Selector("^b$"), Selector("^b$"), options=options, **extra)
    assert (
        paths(prepared(), PathQuery(Selector("^b$"), Selector("^b$"))).rows[0].cost == 0
    )
