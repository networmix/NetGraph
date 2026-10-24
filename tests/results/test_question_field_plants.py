"""Independent question declarations distinguish every recorded control."""

from copy import deepcopy
from fractions import Fraction

import netgraph_core as ngc
import pytest

import ngraph.export as exporting
from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FlowPolicyPreset,
    Link,
    MSDQuery,
    Network,
    Node,
    PathQuery,
    PlacementQuery,
    RoutingDomain,
    Scenario,
    Selector,
    SensitivityQuery,
    UnitsSettings,
    WCMPController,
    capacity,
    edge_sensitivity,
    maximum_supported_demand,
    paths,
    place,
    prepare,
)
from tests.question import asked
from tests.results.test_report_field_plants import change, exact, field_paths, project

SOURCE = {"path": "^s$", "group_by": None, "match": None, "active_only": False}
TARGET = {"path": "^t$", "group_by": "name", "match": None, "active_only": True}
MODEL_FIELDS = (
    "routing",
    "admission",
    "allocation",
    "source_allocation",
    "weight_basis",
    "edge_weights",
    "tie_break",
    "multipath",
    "parallel_edges",
    "tunnel_count",
    "prefer_headroom",
    "cost_ceiling",
    "min_unreserved_bandwidth_units",
    "route_names",
    "controller",
    "supplied_support",
    "supplied_program",
)


def model(**values):
    return {
        **dict.fromkeys(MODEL_FIELDS),
        "admission": "lossless",
        "supplied_support": False,
        "supplied_program": False,
        **values,
    }


def samples():
    source, target = (
        Selector("^s$", active_only=False),
        Selector("^t$", group_by="name", active_only=True),
    )
    network = Network(nodes={"s": Node("s"), "t": Node("t")})
    network.add_link(Link("s", "t", 4, 3))
    demands = DemandSet(
        "load", (DemandSpec(source, target, 2, id="service", priority=7),)
    )
    context = prepare(
        Scenario(network, demand_sets={"load": demands}, units=UnitsSettings(1)),
        demand_sets=("load",),
    )
    default = model(
        routing="shortest_paths",
        allocation="equal",
        source_allocation="equal",
        tie_break="fewer_hops",
        multipath=True,
        parallel_edges=True,
    )
    default_config = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    configs = [
        (default_config, default),
        (
            ngc.FlowPolicyConfig(
                routing=ngc.ShortestPaths(
                    allocation=ngc.RouteAllocation.WEIGHTED,
                    source_allocation=ngc.SourceAllocation.EQUAL,
                    weight_basis=ngc.WeightBasis.EXPLICIT,
                    edge_weights=[2, 5],
                    tie_break=ngc.RouteTieBreak.HIGHER_CAPACITY,
                    multipath=False,
                    parallel_edges=False,
                )
            ),
            model(
                routing="shortest_paths",
                allocation="weighted",
                source_allocation="equal",
                weight_basis="explicit",
                edge_weights=[
                    {"edge": {"link": "s|t|0", "direction": "forward"}, "value": 2},
                    {"edge": {"link": "s|t|0", "direction": "reverse"}, "value": 5},
                ],
                tie_break="higher_capacity",
                multipath=False,
                parallel_edges=False,
            ),
        ),
        (
            ngc.FlowPolicyConfig(
                routing=ngc.DistributedTE(
                    tunnel_count=ngc.TunnelCount(2),
                    cost_ceiling=ngc.AbsoluteCost(3),
                    min_unreserved_bandwidth=2,
                    parallel_edges=False,
                )
            ),
            model(
                routing="distributed_te",
                tunnel_count={"per_head": 2, "up_to": False},
                cost_ceiling={"kind": "absolute", "absolute": 3, "stretch": None},
                min_unreserved_bandwidth_units=2,
                tie_break="fewer_hops",
                parallel_edges=False,
            ),
        ),
        (
            ngc.FlowPolicyConfig(
                routing=ngc.CentralizedTE(
                    source_allocation=ngc.SourceAllocation.EQUAL,
                    tunnel_count=ngc.TunnelCount(3, up_to=True),
                    prefer_headroom=True,
                )
            ),
            model(
                routing="centralized_te",
                source_allocation="equal",
                tunnel_count={"per_head": 3, "up_to": True},
                prefer_headroom=True,
            ),
        ),
    ]
    result = []
    for config, echo in configs:
        design = 2 if echo["routing"] in ("distributed_te", "centralized_te") else None
        value = capacity(
            context,
            CapacityQuery(
                source,
                target,
                config,
                mode="pairwise",
                offer=3,
                design_demand=design,
                workers=1,
            ),
        )
        result.append(
            (
                value,
                {
                    "kind": "capacity",
                    "source": SOURCE,
                    "target": TARGET,
                    "mode": "pairwise",
                    "model": echo,
                    "offer": 3.0,
                    "design_demand": 2.0 if design is not None else None,
                    "failures": None,
                },
            )
        )
    sensitive = edge_sensitivity(
        context,
        SensitivityQuery(
            source,
            target,
            ngc.FlowPolicyConfig(
                routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
            ),
            offer=3,
            workers=1,
        ),
    )
    result.append(
        (
            sensitive,
            {
                "kind": "sensitivity",
                "source": SOURCE,
                "target": TARGET,
                "model": {**default, "admission": "lossy"},
                "offer": 3.0,
                "design_demand": None,
                "excluded_nodes": [],
                "excluded_edges": [],
            },
        )
    )
    for spf in (True, False):
        options = (
            ngc.SpfOptions(
                ngc.Direction.FORWARD,
                residual=[4, 4],
                min_residual=2,
                multipath=False,
                parallel_edges=False,
                tie_break=ngc.RouteTieBreak.HIGHER_CAPACITY,
            )
            if spf
            else ngc.KspOptions(
                k=2,
                cost_ceiling=ngc.CostStretch(Fraction(3, 2)),
                parallel_edges=False,
                tie_break=ngc.RouteTieBreak.HIGHER_CAPACITY,
            )
        )
        value = paths(
            context,
            PathQuery(
                source,
                target,
                mode="pairwise",
                options=options,
                costs_only=False,
                max_paths=2 if spf else None,
                split_parallel_edges=True if spf else None,
            ),
        )
        result.append(
            (
                value,
                {
                    "kind": "paths",
                    "source": SOURCE,
                    "target": TARGET,
                    "mode": "pairwise",
                    "algorithm": "spf" if spf else "ksp",
                    "costs_only": False,
                    "max_paths": 2 if spf else None,
                    "split_parallel_edges": True if spf else None,
                    "k": None if spf else 2,
                    "cost_ceiling": None
                    if spf
                    else {
                        "kind": "stretch",
                        "absolute": None,
                        "stretch": {"numerator": 3, "denominator": 2},
                    },
                    "tie_break": "higher_capacity",
                    "multipath": False if spf else None,
                    "parallel_edges": False,
                    "excluded_nodes": [],
                    "excluded_edges": [],
                    "residual_units": [4, 4] if spf else None,
                    "min_residual": 2 if spf else None,
                },
            )
        )
    demand = {
        "source": SOURCE,
        "target": TARGET,
        "priority": 7,
        "id": "service",
        "model": default,
        "physical_volume": 2.0,
        "mode": "combine",
        "group_mode": "flatten",
    }
    placement = place(
        context, PlacementQuery(context.demand_sets["load"], alpha=1.5, workers=1)
    )
    result.append(
        (
            placement,
            {
                "kind": "placement",
                "demand_set": "load",
                "demands": [demand],
                "alpha": {"value": 1.5, "numerator": 3, "denominator": 2},
                "alpha_source": {"kind": "query", "step": None},
                "failures": None,
                "states": ["converged"],
                "interaction": "ordered",
            },
        )
    )
    search = maximum_supported_demand(
        context,
        MSDQuery(
            context.demand_sets["load"],
            alpha_start=0.5,
            growth_factor=3.0,
            alpha_min=0.25,
            alpha_max=4.0,
            alpha_tolerance=0.5,
            max_bracket_iters=4,
            max_bisect_iters=3,
            export_probe_rows=True,
        ),
    )
    result.append(
        (
            search,
            {
                "kind": "msd",
                "demand_set": "load",
                "demands": [demand],
                "alpha_start": 0.5,
                "growth_factor": 3.0,
                "alpha_min": 0.25,
                "alpha_max": 4.0,
                "alpha_tolerance": 0.5,
                "max_bracket_iters": 4,
                "max_bisect_iters": 3,
                "export_probe_rows": True,
            },
        )
    )
    # A demand the WCMP controller programs names the controller, not a program.
    domain = Network(nodes={name: Node(name) for name in ("S", "U", "T")})
    domain.add_link(Link("S", "U", 4, 1))
    domain.add_link(Link("U", "T", 4, 1))
    programmed = DemandSet(
        "wcmp",
        (
            DemandSpec(
                Selector("^S$"),
                Selector("^T$"),
                2,
                FlowPolicyPreset.SHORTEST_PATHS_WCMP,
                id="dc",
            ),
        ),
    )
    controlled = prepare(
        Scenario(
            domain,
            demand_sets={"wcmp": programmed},
            units=UnitsSettings(1),
            routing=RoutingDomain(Selector("^U$"), Selector("^(S|T)$")),
            wcmp_controller=WCMPController("next_hop"),
            forwarding_groups={},
        ),
        demand_sets=("wcmp",),
    )
    result.append(
        (
            place(
                controlled, PlacementQuery(controlled.demand_sets["wcmp"], workers=1)
            ),
            {
                "kind": "placement",
                "demand_set": "wcmp",
                "demands": [
                    {
                        "source": {**SOURCE, "path": "^S$", "active_only": None},
                        "target": {**SOURCE, "path": "^T$", "active_only": None},
                        "priority": 0,
                        "id": "dc",
                        "model": model(
                            routing="shortest_paths",
                            allocation="weighted",
                            source_allocation="equal",
                            controller="next_hop",
                        ),
                        "physical_volume": 2.0,
                        "mode": "combine",
                        "group_mode": "flatten",
                    }
                ],
                "alpha": {"value": 1.0, "numerator": 1, "denominator": 1},
                "alpha_source": {"kind": "query", "step": None},
                "failures": None,
                "states": ["converged"],
                "interaction": "ordered",
            },
        )
    )
    return result


def test_every_recorded_question_field_has_hand_expectation():
    # Each analysis records its own typed query; its normalized form is written once.
    for value, expected in samples():
        assert type(value.query).__name__.endswith("Query")
        exact(asked(value), expected)
        exact(project(value)["analysis"]["query"], expected)


def test_question_projection_field_plants_have_success_and_applicability_controls(
    monkeypatch,
):
    original = exporting.question
    caught = equivalent = count = 0
    for value, expected in samples():
        exact(project(value)["analysis"]["query"], expected)
        for path in field_paths(expected):
            for mode in ("missing", "null", "wrong"):
                current = expected
                for key in path:
                    current = current[key]
                if mode == "null" and current is None:
                    equivalent += 1
                    continue

                def planted(question, topology, path=path, mode=mode):
                    result = deepcopy(original(question, topology))
                    change(result, path, mode)
                    return result

                with monkeypatch.context() as patch:
                    patch.setattr(exporting, "question", planted)
                    with pytest.raises(AssertionError):
                        exact(project(value)["analysis"]["query"], expected)
                caught += 1
            count += 1
        exact(project(value)["analysis"]["query"], expected)
    assert caught + equivalent == count * 3
    print(
        f"QUESTION PLANTS: {count} fields; {caught} caught; {equivalent} equivalent null->null; model and SPF/KSP applicability controls pass"
    )


def test_sensitivity_question_records_the_excluded_nodes_and_edges():
    network = Network(nodes={name: Node(name) for name in ("s", "m", "t")})
    network.add_link(Link("s", "t", 4, 3))
    network.add_link(Link("s", "m", 4, 1))
    network.add_link(Link("m", "t", 4, 1))
    context = prepare(Scenario(network, units=UnitsSettings(1)))
    topology = context.topology
    reverse = topology.edges_by_link["s|t|0"][1]
    value = edge_sensitivity(
        context,
        SensitivityQuery(
            Selector("^s$"),
            Selector("^t$"),
            ngc.FlowPolicyConfig(routing=ngc.ShortestPaths()),
            eligibility=topology.graph.eligibility(
                excluded_nodes=[topology.node_id_by_name["m"]],
                excluded_edges=[reverse],
            ),
            workers=1,
        ),
    )
    question = project(value)["analysis"]["query"]
    assert question["excluded_nodes"] == ["m"]
    # An excluded node also excludes its edges; the list keeps native edge order.
    expected = {("s|t|0", "reverse")} | {
        (link, direction)
        for link in ("s|m|0", "m|t|0")
        for direction in ("forward", "reverse")
    }
    assert question["excluded_edges"] == [
        {"link": ref.link, "direction": ref.direction}
        for ref in topology.edge_refs
        if (ref.link, ref.direction) in expected
    ]
    assert asked(value) == question
