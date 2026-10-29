"""Hand-derived counterexamples and independent computations for the precision domain.

Only native_values imports NetGraph and its native engine. All native scenarios are constructed here from literal inputs.
"""

from fractions import Fraction as F
from math import gcd
from typing import Any

EXPECTED: dict[str, dict[str, Any]] = {
    "selected_tunnel_endpoints": {
        "t1_one_tunnels": 16,
        "t1_one_count": F(77, 4),
        "t1_one_q": F(1, 64),
        "t1_one_roster": (0,),
        "t1_both_tunnels": 32,
        "t1_both_count": F(141, 4),
        "t1_both_q": F(1, 128),
        "t1_both_roster": (0,),
        "t2_one_tunnels": 16,
        "t2_one_count": F(77, 4),
        "t2_one_q": F(1, 64),
        "t2_one_roster": (0,),
        "t2_both_tunnels": 32,
        "t2_both_count": F(141, 4),
        "t2_both_q": F(1, 128),
        "t2_both_roster": (0,),
    },
    "binary64_precision": {"q_exponent": -1, "split_count": F(3)},
    "set_uses": {
        "simultaneous_q": F(1, 16),
        "requested_q": F(1, 32),
        "simultaneous_count": F(3),
        "requested_count": F(6),
    },
    "unbounded": {"q_exponent": 32, "limited_by": "unbounded", "target_met": True},
    "expanded_leaf": {
        "q_exponent": -3,
        "leaf_units": (2, 2, 1, 1, 1, 1),
        "fluid_each": F(1, 6),
    },
    "scaled_product": {
        "q_exponent": -31,
        "delivered_physical": F(2**28),
        "product_error": F(234881025, 2**53),
        "conversion_error": F(0),
        "binary64_band_covers": True,
    },
    "large_residual": {
        "q_exponent": -16,
        "last_units": 129360,
        "fluid_last_units": F(129860),
    },
    "later_offer": {
        "q_exponent": -5,
        "delivered_units": 0,
        "fluid_delivery": F(1, 128),
    },
    "finite_offer": {"q_exponent": -9, "delivered_units": 512, "uncapped_units": 51200},
    "later_count": {
        "q_exponent": -3,
        "prepared_tunnel_size": 8,
        "later_tunnel_size": 0,
    },
    "supplied_dags": {
        "q_exponent": -14,
        "delivered_physical": F(253, 128),
        "fluid_delivery": F(2),
    },
    "weighted_lossy": {"delivered_units": 24458019, "fluid_error": F(57361, 2038)},
    "lossy_sharing": {
        "delivered_units": (3, 0, 0),
        "fluid_each": (F(15, 7), F(3, 7), F(3, 7)),
    },
    "controller": {"weights_q1": (3, 1), "weights_qfine": (30721, 10240)},
    "msd_limit": {"alpha": F(1), "status": "limit", "fluid_threshold": F(10)},
    "validation_case": {
        "valid_units": 100,
        "refusal": "workflow[0] (name 'cap'): edge_weights: expected 2 entries",
    },
    "floor_input": {"q_exponent": -32, "delivered_units": 0, "relative_error": F(1)},
}


def rounded(x):
    return (F(x) + F(1, 2)).__floor__()


def rr(total, count):
    whole, rest = divmod(total, count)
    return tuple(whole + (i < rest) for i in range(count))


def compute(name, ref):
    if name == "selected_tunnel_endpoints":
        out = {}
        for model in ("t1", "t2"):
            for label, sources in (("one", ("S1",)), ("both", ("S1", "S2"))):
                tunnels = len(sources) * 16
                exponent, count, *_ = ref.rule(5, [(0, tunnels)], 1, 1, p=F(1, 2))
                prefix = f"{model}_{label}"
                out.update(
                    {
                        f"{prefix}_tunnels": tunnels,
                        f"{prefix}_count": count,
                        f"{prefix}_q": F(2) ** exponent,
                        # The sole link S1–T admits only S1 to the runtime roster.
                        f"{prefix}_roster": (0,),
                    }
                )
        return out
    if name == "binary64_precision":
        # 0.3 is below 3/10 in binary64: p*10/3 < 1, so q is 1/2.
        exponent, count, *_ = ref.rule(4, [(1, 0)], 10, 10, p=F(3, 10))
        return dict(q_exponent=exponent, split_count=count)
    if name == "set_uses":
        simultaneous = ref.rule(4, [], 1, 1, p=F(1, 4))
        requested = ref.rule(4, [(2, 0)], 1, 1, p=F(1, 4))
        return dict(
            simultaneous_q=F(2) ** simultaneous[0],
            requested_q=F(2) ** requested[0],
            simultaneous_count=simultaneous[1],
            requested_count=requested[1],
        )
    if name == "unbounded":
        e, _, limited, _, met = ref.rule(0, [], None, None)
        return dict(q_exponent=e, limited_by=limited, target_met=met)
    if name == "expanded_leaf":
        e = ref.rule(19, [(6, 0)], 1000, 1, p=F(1, 10))[0]
        return dict(
            q_exponent=e,
            leaf_units=rr(rounded(F(1) / F(2) ** e), 6),
            fluid_each=F(1, 6),
        )
    if name == "scaled_product":
        volume = 2**28 + 1
        alpha = 1 - F(1, 2**28) + F(1, 2**53)
        p = F(1, 2**57)
        e = ref.rule(4, [(1, 0)], volume, volume, p=p)[0]
        exact = alpha * volume
        product = F(float(alpha) * float(volume))
        physical = rounded(product / F(2) ** e) * F(2) ** e
        return dict(
            q_exponent=e,
            delivered_physical=physical,
            product_error=exact - product,
            conversion_error=abs(physical - product),
            binary64_band_covers=abs(physical - exact)
            <= ref.msd_band(p) * exact + F(2) ** e / 2,
        )
    if name == "large_residual":
        q = F(2) ** -16
        request = F(1051, 131072)
        return dict(
            q_exponent=ref.rule(8, [(1, 0)], 1, request)[0],
            last_units=rounded(10 / q) - 1000 * rounded(request / q),
            fluid_last_units=(10 - 1000 * request) / q,
        )
    if name in ("later_offer", "finite_offer"):
        declared = name == "finite_offer"
        e = ref.rule(4, [], 100, 1 if declared else 100)[0]
        q = F(2) ** e
        offered = F(1) if declared else F(1, 128)
        out = dict(
            q_exponent=e, delivered_units=min(rounded(offered / q), rounded(100 / q))
        )
        out.update(uncapped_units=rounded(100 / q)) if declared else out.update(
            fluid_delivery=offered
        )
        return out
    if name == "later_count":
        e = ref.rule(4, [(0, 1)], 1, 1, p=F(1, 2))[0]
        capacity = rounded(1 / F(2) ** e)
        return dict(
            q_exponent=e,
            prepared_tunnel_size=capacity,
            later_tunnel_size=capacity // 16,
        )
    if name == "supplied_dags":
        e = ref.rule(48, [], 1, 20)[0]
        q = F(2) ** e
        lo, hi = 0, rounded(20 / q) + 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            load = sum(sum(rr(x, 20)[:10]) for x in rr(mid, 100))
            if load <= rounded(1 / q):
                lo = mid
            else:
                hi = mid
        return dict(q_exponent=e, delivered_physical=lo * q, fluid_delivery=F(2))
    if name == "weighted_lossy":
        offer = 1000 * 24002 + 19 * 24001
        fluid = F(offer * 1000, 1019) + 19 * F(48001, 2)
        return dict(delivered_units=offer, fluid_error=offer - fluid)
    if name == "lossy_sharing":
        # Three capacity units, proportional sharing with highest averages: all go to the offer of five.
        offers = (5, 1, 1)
        seats = [0, 0, 0]
        for _ in range(3):
            best = max(range(3), key=lambda i: (F(offers[i], seats[i] + 1), -i))
            seats[best] += 1
        return dict(
            delivered_units=tuple(seats), fluid_each=tuple(F(3 * x, 7) for x in offers)
        )
    if name == "controller":
        out: dict[str, Any] = {}
        for key, q in (("weights_q1", F(1)), ("weights_qfine", F(1, 1024))):
            a, b = rounded(F(30.0007) / q), rounded(10 / q)
            common = gcd(a, b)
            out[key] = (a // common, b // common)
        return out
    if name == "msd_limit":
        return dict(alpha=F(1), status="limit", fluid_threshold=F(10))
    if name == "validation_case":
        return dict(
            valid_units=100,
            refusal="workflow[0] (name 'cap'): edge_weights: expected 2 entries",
        )
    if name == "floor_input":
        e = ref.rule(4, [(1, 0)], 1, 2**-40)[0]
        actual = rounded(F(2) ** -40 / F(2) ** e)
        return dict(
            q_exponent=e,
            delivered_units=actual,
            relative_error=abs(actual * F(2) ** e - F(2) ** -40) / F(2) ** -40,
        )
    raise KeyError(name)


def native_values(name):
    import netgraph_core as ngc
    import yaml

    from ngraph import (
        CapacityQuery,
        Scenario,
        Selector,
        TunnelCountQuery,
        capacity,
        prepare,
        run,
        tunnel_counts,
    )

    def solve(doc) -> tuple[Any, Any]:
        prepared = prepare(Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False)))
        assert prepared.topology.q == doc["units"]["resolution"]
        return prepared, run(prepared)

    def base(q, volume: Any = 1, cap=100, routing=None) -> dict[str, Any]:
        demand: dict[str, Any] = dict(source="^S$", target="^T$", volume=float(volume))
        if routing:
            demand["model"] = dict(routing=routing)
        else:
            demand["preset"] = "SHORTEST_PATHS_ECMP"
        return dict(
            units=dict(resolution=float(q)),
            network=dict(
                nodes={"S": {}, "T": {}},
                links=[dict(source="S", target="T", capacity=float(cap))],
            ),
            demands={"d": [demand]},
            workflow=[
                dict(type="TrafficMatrixPlacement", name="p", demand_set="d", workers=1)
            ],
        )

    def rows(result) -> Any:
        return result.steps[0].result.cases[0].states["converged"].rows

    if name == "selected_tunnel_endpoints":
        out: dict[str, Any] = {}
        for model, routing_type in (("t1", "distributed_te"), ("t2", "centralized_te")):
            tunnel_routing: dict[str, Any] = dict(
                type=routing_type, tunnel_count=dict(per_head=16)
            )
            if model == "t2":
                tunnel_routing["source_allocation"] = "equal"
            for label, selector in (("one", "^S1$"), ("both", "^S")):
                doc = base(1, routing=tunnel_routing)
                doc["units"] = dict(precision=0.5)
                doc["network"] = dict(
                    nodes={n: {} for n in ("S1", "S2", "T")},
                    links=[dict(source="S1", target="T", capacity=1)],
                )
                doc["demands"]["d"][0].update(source=selector)
                prepared = prepare(
                    Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False))
                )
                bound = prepared.units_report.split_bound
                assert bound is not None
                assert (bound.nodes, bound.directed_links, bound.demands) == (3, 2, 0)
                result = rows(run(prepared))[0].result
                assert result.plan is not None
                prefix = f"{model}_{label}"
                out.update(
                    {
                        f"{prefix}_tunnels": bound.tunnels,
                        f"{prefix}_count": bound.count,
                        f"{prefix}_q": F(prepared.topology.q),
                        f"{prefix}_roster": tuple(
                            head for head, _ in result.plan.design_by_head
                        ),
                    }
                )
        return out
    if name == "binary64_precision":
        doc = base(1, volume=10, cap=10)
        doc["units"] = dict(precision=0.3)
        prepared = prepare(Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False)))
        assert prepared.units_report.split_bound is not None
        return dict(
            q_exponent=prepared.units_report.exponent,
            split_count=prepared.units_report.split_bound.count,
        )
    if name == "set_uses":
        doc = base(1, cap=1)
        doc["units"] = dict(precision=0.25)
        doc["demands"]["d"] *= 2
        doc["workflow"][0]["interaction"] = "simultaneous"
        simultaneous_scenario = Scenario.from_yaml(yaml.safe_dump(doc, sort_keys=False))
        simultaneous = prepare(simultaneous_scenario).units_report
        requested = prepare(simultaneous_scenario, demand_sets=("d",)).units_report
        assert simultaneous.split_bound is not None
        assert requested.split_bound is not None
        return dict(
            simultaneous_q=F(simultaneous.q),
            requested_q=F(requested.q),
            simultaneous_count=simultaneous.split_bound.count,
            requested_count=requested.split_bound.count,
        )
    if name == "unbounded":
        empty = prepare(Scenario.from_yaml("network: {nodes: {}, links: []}"))
        report = empty.units_report
        assert report.input_bound is None and report.split_bound is None
        assert report.achieved_precision is None
        return dict(
            q_exponent=report.exponent,
            limited_by=report.limited_by,
            target_met=report.target_met,
        )
    if name == "expanded_leaf":
        doc = base(F(1, 8))
        doc["network"] = dict(
            nodes={n: {} for n in [*(f"S{i}" for i in range(6)), "T"]},
            links=[dict(source=f"S{i}", target="T", capacity=1000) for i in range(6)],
        )
        doc["demands"]["d"][0].update(source="^S", mode="pairwise")
        doc["units"]["precision"] = 0.1
        _, result = solve(doc)
        return dict(leaf_units=tuple(row.result.delivered for row in rows(result)))
    if name == "scaled_product":
        alpha = float(1 - F(1, 2**28) + F(1, 2**53))
        q = F(2) ** -31
        doc = base(q, 2**28 + 1, 2**28 + 1)
        doc["units"]["precision"] = 2**-57
        doc["workflow"][0]["alpha"] = alpha
        _, result = solve(doc)
        physical = F(rows(result)[0].result.delivered) * q
        product = F(alpha * float(2**28 + 1))
        return dict(
            delivered_physical=physical,
            product_error=F(alpha) * (2**28 + 1) - physical,
            conversion_error=abs(product - physical),
        )
    if name == "large_residual":
        doc = base(F(2) ** -16, cap=10)
        doc["network"]["nodes"].update(U={}, V={})
        doc["network"]["links"].append(dict(source="U", target="V", capacity=1))
        prior = dict(
            source="^S$", target="^T$", volume=1051 / 131072, preset="TE_MAXFLOW_UNLIM"
        )
        doc["demands"]["d"] = [dict(prior) for _ in range(1000)] + [
            dict(source="^S$", target="^T$", volume=10, preset="SHORTEST_PATHS_ECMP")
        ]
        _, result = solve(doc)
        return dict(last_units=rows(result)[-1].result.delivered)
    if name in ("later_offer", "finite_offer"):
        declared = name == "finite_offer"
        q = F(2) ** (-9 if declared else -5)
        doc = base(q)
        doc.pop("demands")
        doc["workflow"] = []
        if declared:
            doc["workflow"] = [
                dict(
                    type="MaxFlow",
                    name="cap",
                    source="^S$",
                    target="^T$",
                    offer=1,
                    workers=1,
                )
            ]
        prepared, result = solve(doc)

        def query(offer):
            answer: Any = capacity(
                prepared,
                CapacityQuery(Selector("^S$"), Selector("^T$"), offer=offer, workers=1),
            )
            return answer.cases[0].states["converged"].rows[0].result.delivered

        if declared:
            return dict(
                delivered_units=rows(result)[0].result.delivered,
                uncapped_units=query(None),
            )
        return dict(delivered_units=query(1 / 128))
    if name == "later_count":
        doc = base(
            F(1, 8),
            cap=1,
            routing=dict(
                type="centralized_te",
                source_allocation="equal",
                tunnel_count=dict(per_head=1),
            ),
        )
        doc["units"]["precision"] = 0.5
        prepared, result = solve(doc)
        later = tunnel_counts(
            prepared,
            TunnelCountQuery(
                prepared.demand_sets["d"], (16,), design_demand=2, offer=2, workers=1
            ),
        )
        assert later.rows[0].result.plan is not None
        return dict(
            prepared_tunnel_size=rows(result)[0].result.plan.max_bandwidth_per_tunnel,
            later_tunnel_size=later.rows[0].result.plan.max_bandwidth_per_tunnel,
        )
    if name == "supplied_dags":
        q = F(2) ** -14
        forward = [(0, 1, 100)] * 10 + [(0, 2, 100)] * 10 + [(1, 3, 1), (2, 3, 100)]
        edges = sorted(forward + [(v, u, c) for u, v, c in forward])
        graph = ngc.Graph(
            4,
            [e[0] for e in edges],
            [e[1] for e in edges],
            [rounded(e[2] / q) for e in edges],
            [1] * len(edges),
            float(q),
        )
        via = [
            i
            for v in range(4)
            for i, (u, dst, _) in enumerate(edges)
            if dst == v and ((u == 0 and v in (1, 2)) or (u in (1, 2) and v == 3))
        ]
        offsets = [0]
        for v in range(4):
            offsets.append(offsets[-1] + sum(edges[i][1] == v for i in via))
        dag = ngc.PredecessorDAG.from_csr(
            graph, offsets, [edges[i][0] for i in via], via
        )
        program = ngc.ForwardingProgram.from_routes(
            graph, 0, 3, [ngc.RouteDefinition(0, dag) for _ in range(100)]
        )
        config = ngc.FlowPolicyConfig(routing=ngc.Pinned(program))
        answer = ngc.evaluate_demand(
            graph, 0, 3, ngc.EvaluationOptions(config, offer=rounded(20 / q))
        )
        return dict(delivered_physical=F(answer.delivered) * q)
    if name == "weighted_lossy":
        offer = 24458019
        caps = [2 * offer] + [24001] * 19
        graph = ngc.Graph(
            2, [0] * 20 + [1] * 20, [1] * 20 + [0] * 20, caps * 2, [1] * 40, 1
        )
        routing = ngc.ShortestPaths(
            allocation=ngc.RouteAllocation.WEIGHTED,
            weight_basis=ngc.WeightBasis.EXPLICIT,
            edge_weights=([1000] + [1] * 19) * 2,
        )
        config = ngc.FlowPolicyConfig(routing=routing, admission=ngc.Admission.LOSSY)
        answer = ngc.evaluate_demand(
            graph, 0, 1, ngc.EvaluationOptions(config, offer=offer)
        )
        fluid = F(offer * 1000, 1019) + 19 * F(48001, 2)
        return dict(
            delivered_units=answer.delivered, fluid_error=F(answer.delivered) - fluid
        )
    if name == "lossy_sharing":
        graph = ngc.Graph(2, [0], [1], [3], [1], 1)
        ledger = ngc.FlowLedger(graph)
        config = ngc.FlowPolicyConfig(
            routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
        )
        policies = [ngc.FlowPolicy(ledger, 0, 1, config) for _ in range(3)]
        results = ngc.apply_actions(
            ledger,
            [
                ngc.Replace(p, amount)
                for p, amount in zip(policies, (5, 1, 1), strict=False)
            ],
            mode=ngc.BatchMode.SIMULTANEOUS,
        )
        return dict(delivered_units=tuple(r.delivered for r in results))
    if name == "controller":
        out: dict[str, Any] = {}
        for key, q in (("weights_q1", 1), ("weights_qfine", 1 / 1024)):
            doc = base(q, 40)
            doc["network"] = dict(
                nodes={n: {} for n in ("S", "X1", "X2", "T")},
                links=[
                    dict(source=s, target=t, capacity=c)
                    for s, t, c in [
                        ("S", "X1", 100),
                        ("S", "X2", 100),
                        ("X1", "T", 30.0007),
                        ("X2", "T", 10),
                    ]
                ],
            )
            doc["demands"]["d"][0]["preset"] = "SHORTEST_PATHS_WCMP"
            doc["routing"] = dict(
                igp_domain=dict(path="^X"), bgp_edge=dict(path="^(S|T)$")
            )
            doc["wcmp_controller"] = dict(scope="next_hop")
            prepared, _ = solve(doc)
            table = prepared.demand_sets["d"].controller[0]
            out[key] = tuple(m.weight for m in table.programmed[0].members)
        return out
    if name == "msd_limit":
        doc = base(F(1, 512), cap=10)
        doc["workflow"] = [
            dict(type="MaximumSupportedDemand", name="m", demand_set="d", alpha_max=1)
        ]
        _, result = solve(doc)
        answer = result.steps[0].result
        return dict(alpha=F(answer.alpha_feasible.value), status=answer.search_status)
    if name == "validation_case":
        from ngraph import Link, Network, Node, UnitsSettings
        from ngraph.workflow import MaxFlow

        def scenario(weights):
            network = Network(nodes={n: Node(n) for n in ("A", "T")})
            network.add_link(Link("A", "T", 100))
            routing = ngc.ShortestPaths(
                allocation=ngc.RouteAllocation.WEIGHTED,
                weight_basis=ngc.WeightBasis.EXPLICIT,
                edge_weights=weights,
            )
            config = ngc.FlowPolicyConfig(routing=routing)
            return Scenario(
                network,
                [
                    MaxFlow(
                        name="cap",
                        source=Selector("A"),
                        target=Selector("T"),
                        model=config,
                        workers=1,
                    )
                ],
                units=UnitsSettings(1),
            )

        prepared = prepare(scenario([1, 1]))
        answer = rows(run(prepared))[0].result.delivered
        assert answer == 100
        try:
            prepare(scenario([1]))
        except ValueError as exc:
            refusal = str(exc)
        else:
            raise AssertionError("prepare must reject the wrong-sized vector")
        return dict(valid_units=answer, refusal=refusal)
    if name == "floor_input":
        _, result = solve(base(F(2) ** -32, F(2) ** -40, 1))
        return dict(delivered_units=rows(result)[0].result.delivered)
    raise KeyError(name)
