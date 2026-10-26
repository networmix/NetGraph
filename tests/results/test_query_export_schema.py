"""Every analysis's query options export a document that validates against results.json.

Each analysis (paths with SPF and KSP options, capacity, placement, MSD, tunnel counts and
edge sensitivity) is asked with every option value that reaches the results file, set and
unset, on a plain graph and on one a pooled demand set augments with a private head node
and its attachments. Combinations the product or the Core refuses are recorded with their
refusal; every option value is required to reach at least one exported document.
"""

import json
from functools import partial
from importlib.resources import files
from io import StringIO
from itertools import product

import jsonschema
import netgraph_core as ngc

from ngraph import (
    CapacityQuery,
    DemandSet,
    DemandSpec,
    FailureMode,
    FailurePolicy,
    FailureRequest,
    FailureRule,
    FlowPolicyPreset,
    Link,
    MSDQuery,
    Network,
    Node,
    PathQuery,
    PlacementQuery,
    Scenario,
    Selector,
    SensitivityQuery,
    TunnelCountQuery,
    UnitsSettings,
    capacity,
    edge_sensitivity,
    maximum_supported_demand,
    paths,
    place,
    prepare,
    tunnel_counts,
    write_json,
)

SCHEMA = json.loads(files("ngraph.schemas").joinpath("results.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
EVERY = ngc.OutputOptions(
    edge_flows=True,
    residual=True,
    edge_reservations=True,
    saturated_boundary_edges=True,
    min_cut=True,
)
NONE = ngc.OutputOptions()
FAILURE = FailureRequest(
    FailurePolicy(
        modes=[FailureMode(1, [FailureRule("link", mode="all", path="^B\\|T")])]
    ),
    1,
    1,
)


def graph(pooled):
    """A-T 5 (cost 1), A-B 4 (cost 1), B-T 8 (cost 1); with `pooled`, a pool head node 3."""
    network = Network(nodes={name: Node(name) for name in ("A", "B", "T")})
    network.add_link(Link("A", "T", 5, 1))
    network.add_link(Link("A", "B", 4, 1))
    network.add_link(Link("B", "T", 8, 1))

    def one(name, source, preset):
        spec = DemandSpec(
            Selector(source),
            Selector("^T$"),
            4,
            preset,
            id=name,
            mode="pairwise" if name == "load" else "combine",
        )
        return DemandSet(name, (spec,))

    sets = {
        "load": one("load", "^(A|T)$", FlowPolicyPreset.SHORTEST_PATHS_ECMP),
        # T2 as a native model: a preset's finite demand would add a pool head here too
        "te": one(
            "te",
            "^A$",
            ngc.FlowPolicyConfig(
                routing=ngc.CentralizedTE(
                    source_allocation=ngc.SourceAllocation.EQUAL,
                    tunnel_count=ngc.TunnelCount(16),
                )
            ),
        ),
    }
    if pooled:
        sets["pool"] = one("pool", "^(A|B)$", FlowPolicyPreset.TE_ECMP_16_LSP)
    prep = prepare(
        Scenario(network, demand_sets=sets, units=UnitsSettings(1)),
        demand_sets=tuple(sets),
    )
    nodes = prep.topology.graph.num_nodes()
    assert nodes == (4 if pooled else 3)
    return prep


def path_queries(prep):
    edges = prep.topology.graph.num_edges()
    vectors = {"none": None, "positive": [3] * edges, "zero": [0] * edges}
    for multipath, parallel, tie, (name, residual), minimum in product(
        (True, False),
        (True, False),
        ngc.RouteTieBreak.__members__.values(),
        vectors.items(),
        (1, 3),
    ):
        options = ngc.SpfOptions(
            ngc.Direction.FORWARD,
            tie_break=tie,
            multipath=multipath,
            parallel_edges=parallel,
            residual=residual,
            min_residual=minimum,
        )
        yield (
            ("spf", f"residual={name}", f"min_residual={minimum}", f"tie={tie.name}"),
            partial(PathQuery, Selector("^A$"), Selector("^T$"), options=options),
        )
    for k, tie, parallel, ceiling, (name, residual) in product(
        (1, 2),
        ngc.RouteTieBreak.__members__.values(),
        (True, False),
        (None, ngc.AbsoluteCost(5), ngc.CostStretch(2)),
        vectors.items(),
    ):
        options = ngc.KspOptions(
            k,
            tie_break=tie,
            parallel_edges=parallel,
            cost_ceiling=ceiling,
            residual=residual,
        )
        yield (
            ("ksp", f"residual={name}", f"k={k}", f"ceiling={type(ceiling).__name__}"),
            partial(PathQuery, Selector("^A$"), Selector("^T$"), options=options),
        )
    for mode, costs_only, max_paths, split in product(
        ("combine", "pairwise"), (False, True), (None, 1), (None, True, False)
    ):
        yield (
            (
                "spf",
                f"mode={mode}",
                f"costs_only={costs_only}",
                f"max_paths={max_paths}",
                f"split={split}",
            ),
            partial(
                PathQuery,
                Selector("^(A|B)$"),
                Selector("^T$"),
                mode=mode,
                costs_only=costs_only,
                max_paths=max_paths,
                split_parallel_edges=split,
            ),
        )


def mask(prep, pooled):
    return prep.topology.graph.eligibility(excluded_nodes=[3] if pooled else [1])


def documents(pooled):
    """(analysis kind, option labels, a callable returning the analysis)."""
    prep = graph(pooled)
    for labels, factory in path_queries(prep):
        yield "paths", labels, lambda f=factory: paths(prep, f())
    yield (
        "paths",
        ("spf", "eligibility=mask"),
        lambda: paths(
            prep,
            PathQuery(
                Selector("^A$"),
                Selector("^T$"),
                options=ngc.SpfOptions(
                    ngc.Direction.FORWARD, eligibility=mask(prep, pooled)
                ),
            ),
        ),
    )
    ecmp = ngc.FlowPolicyConfig(routing=ngc.ShortestPaths())
    lossy = ngc.FlowPolicyConfig(
        routing=ngc.ShortestPaths(), admission=ngc.Admission.LOSSY
    )
    optimized = ngc.FlowPolicyConfig(
        routing=ngc.CentralizedTE(source_allocation=ngc.SourceAllocation.OPTIMIZED)
    )
    for mode, offer, failures, outputs, costs, details in product(
        ("combine", "pairwise"),
        (None, 3),
        (None, FAILURE),
        (NONE, EVERY),
        (False, True),
        (False, True),
    ):
        labels = (
            f"mode={mode}",
            f"offer={offer}",
            f"failures={failures is not None}",
            f"outputs={'every' if outputs is EVERY else 'none'}",
            f"cost_distribution={costs}",
            f"details={details}",
        )
        factory = partial(
            CapacityQuery,
            Selector("^(A|B)$"),
            Selector("^T$"),
            ecmp,
            mode=mode,
            offer=offer,
            failures=failures,
            workers=1,
            outputs=outputs,
            export_cost_distribution=costs,
            export_details=details,
        )
        yield "capacity", labels, lambda f=factory: capacity(prep, f())
    yield (
        "capacity",
        ("design_demand=4",),
        lambda: capacity(
            prep,
            CapacityQuery(
                Selector("^A$"),
                Selector("^T$"),
                ngc.FlowPolicyConfig(
                    routing=ngc.CentralizedTE(
                        source_allocation=ngc.SourceAllocation.EQUAL,
                        tunnel_count=ngc.TunnelCount(2),
                    )
                ),
                offer=4,
                design_demand=4,
            ),
        ),
    )
    sets = ("load", "te", "pool") if pooled else ("load", "te")
    states = (("converged",), ("converged", "stale", "repair"))
    for name, alpha, state, interaction, failures, outputs, flags in product(
        sets,
        (1.0, 2.5),
        states,
        ("ordered", "simultaneous"),
        (None, FAILURE),
        (NONE, EVERY),
        (False, True),
    ):
        labels = (
            f"set={name}",
            f"alpha={alpha}",
            f"states={len(state)}",
            f"interaction={interaction}",
            f"failures={failures is not None}",
            f"outputs={'every' if outputs is EVERY else 'none'}",
            f"flags={flags}",
        )
        factory = partial(
            PlacementQuery,
            prep.demand_sets[name],
            alpha=alpha,
            failures=failures,
            workers=1,
            outputs=outputs,
            export_cost_distribution=flags,
            export_details=flags,
            states=state,
            interaction=interaction,
        )
        yield "placement", labels, lambda f=factory: place(prep, f())
    for name, start, tolerance, rows, details in product(
        ("load", "te"), (1.0, 0.5), (0.01, 0.25), (False, True), (False, True)
    ):
        labels = (
            f"set={name}",
            f"alpha_start={start}",
            f"alpha_tolerance={tolerance}",
            f"probe_rows={rows}",
            f"details={details}",
        )
        factory = partial(
            MSDQuery,
            prep.demand_sets[name],
            alpha_start=start,
            alpha_tolerance=tolerance,
            export_probe_rows=rows,
            export_details=details,
        )
        yield "msd", labels, lambda f=factory: maximum_supported_demand(prep, f())
    for name, counts, up_to, masked, outputs, details in product(
        ("te", "pool") if pooled else ("te",),
        ((1,), (1, 2)),
        (None, 4),
        (False, True),
        (NONE, EVERY),
        (False, True),
    ):
        labels = (
            f"set={name}",
            f"counts={len(counts)}",
            f"up_to={up_to}",
            f"eligibility={masked}",
            f"outputs={'every' if outputs is EVERY else 'none'}",
            f"details={details}",
        )
        factory = partial(
            TunnelCountQuery,
            prep.demand_sets[name],
            counts=counts,
            up_to=up_to,
            design_demand=4,
            offer=0 if name == "pool" else 4,
            eligibility=mask(prep, pooled) if masked else None,
            workers=1,
            outputs=outputs,
            export_details=details,
        )
        yield "tunnel_counts", labels, lambda f=factory: tunnel_counts(prep, f())
    for config, offer, masked, outputs, details in product(
        (ecmp, lossy, optimized), (None, 3), (False, True), (NONE, EVERY), (False, True)
    ):
        labels = (
            f"config={'ecmp' if config is ecmp else 'lossy ecmp' if config is lossy else 'optimized'}",
            f"offer={offer}",
            f"eligibility={masked}",
            f"outputs={'every' if outputs is EVERY else 'none'}",
            f"details={details}",
        )
        factory = partial(
            SensitivityQuery,
            Selector("^A$"),
            Selector("^T$"),
            config,
            offer=offer,
            eligibility=mask(prep, pooled) if masked else None,
            workers=1,
            outputs=outputs,
            export_details=details,
        )
        yield "sensitivity", labels, lambda f=factory: edge_sensitivity(prep, f())


def export_all():
    """Export every document; returns (exported, refused) per graph form."""
    out = {}
    for pooled in (False, True):
        exported, refused = [], []
        for kind, labels, make in documents(pooled):
            try:
                analysis = make()
            except (TypeError, ValueError) as exc:
                refused.append((kind, labels, str(exc)))
                continue
            output = StringIO()
            write_json(analysis, output)
            wire = json.loads(output.getvalue())
            errors = [e.message for e in VALIDATOR.iter_errors(wire)]
            assert not errors, (pooled, kind, labels, errors[:2])
            exported.append((kind, labels, wire["analysis"]["query"]))
        out["pooled" if pooled else "plain"] = (exported, refused)
    return out


def test_every_query_option_exports_a_valid_document_on_both_graphs():
    results = export_all()
    for form, (exported, refused) in results.items():
        seen = {(kind, label) for kind, labels, _ in exported for label in labels}
        attempted = {
            (kind, label)
            for kind, labels, _ in documents(form == "pooled")
            for label in labels
        }
        # Every option value that was asked reached an exported document.
        assert attempted - seen == set(), (form, sorted(attempted - seen))
        # Refusals are the product's or the Core's own rules, never an export error.
        assert all(
            "requires" in r or "expected" in r or "budget" in r for _, _, r in refused
        ), [
            r
            for r in refused
            if not ("requires" in r[2] or "expected" in r[2] or "budget" in r[2])
        ][:3]
        # A supplied KSP residual vector, positive and zero, round-trips; unset stays null.
        ksp = [
            q for kind, _, q in exported if kind == "paths" and q["algorithm"] == "ksp"
        ]
        assert any(q["residual_units"] is None for q in ksp), form
        vectors = {
            tuple(q["residual_units"]) for q in ksp if q["residual_units"] is not None
        }
        assert len(vectors) == 2 and {v[0] for v in vectors} == {0, 3}, (form, vectors)
