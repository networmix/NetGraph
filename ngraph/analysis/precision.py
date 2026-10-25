"""Local split-precision constraints of native observations, under one set of rules.

A placed demand and an evaluated capacity question split traffic by the same
rules: sources share a demand equally, tunnels share a head, and DAG routers
share their incoming amount by allocation and weights. The rules read their
facts from one of two observers: a placement's native records, or the
searches a capacity evaluator would make on an empty ledger.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from fractions import Fraction
from functools import cached_property
from typing import TYPE_CHECKING, Literal

import netgraph_core as ngc

from ngraph.analysis.demands import controlled, residual_weights
from ngraph.analysis.topology import NamedRoutes, PreparedTopology
from ngraph.analysis.units import (
    input_constraint,
    input_samples,
    precision_miss,
)
from ngraph.model.demand import PinnedRoutes, _DistributedTEInput, _ParsedModel
from ngraph.results import (
    ExpansionLeaf,
    ExpansionParent,
    PrecisionMiss,
    SplitConstraint,
    UnverifiedConstraint,
)
from ngraph.utils.values import integer, physical

if TYPE_CHECKING:
    from ngraph.analysis.preparation import PreparedScenario


def split_constraint(
    kind: Literal["expansion", "source", "router", "tunnel"],
    label: str,
    incoming: Fraction,
    members: int,
    q: float,
    precision: float,
) -> SplitConstraint:
    """Record a local split bound without solving admission or forwarding."""
    integer(members, "split members", minimum=2)
    bound = (
        Fraction(physical(precision, "units.precision", positive=True))
        * incoming
        / (members - 1)
    )
    return SplitConstraint(
        kind, label, incoming, "declared", members, bound, Fraction(q) <= bound
    )


def expansion_bounds(plans, q, precision, alpha=1.0):
    """Describe continuous declared splits on the fixed ordered tree."""
    constraints, incoming = [], {}

    def visit(node, amount):
        if isinstance(node, ExpansionLeaf):
            incoming[node.id] = amount
            return
        members = len(node.children)
        if amount > 0 and members > 1:
            constraints.append(
                split_constraint("expansion", node.label, amount, members, q, precision)
            )
        for child in node.children:
            visit(child, amount / members)

    for plan in plans:
        volume = (
            plan.physical_volume
            if isinstance(plan, ExpansionParent)
            else plan.spec.volume
        )
        visit(plan.root, Fraction(float(volume) * float(alpha)))
    return tuple(constraints), incoming


def effective_rows(topology, edges, destinations, allocation, weights):
    """Native preparation's split rows over a set of DAG edges.

    Native W prunes zero-capacity members even for positive EXPLICIT weights,
    then removes branches with no effective continuation to a destination;
    EQUAL keeps every member. Returns each router's members in EdgeId order,
    with their weights (1 for EQUAL).
    """
    graph = topology.graph
    sources, targets = graph.edge_sources(), graph.edge_destinations()
    capacities = graph.edge_capacity_units()
    effective_edges = {
        edge
        for edge in edges
        if int(sources[edge]) not in destinations
        and (
            allocation == ngc.RouteAllocation.EQUAL
            or (capacities[edge] > 0 and weights[edge] > 0)
        )
    }
    parents = [[] for _ in range(graph.num_nodes())]
    for edge in effective_edges:
        parents[int(targets[edge])].append(int(sources[edge]))
    reachable = set(destinations)
    pending = list(destinations)
    while pending:
        for source in parents[pending.pop()]:
            if source not in reachable:
                reachable.add(source)
                pending.append(source)
    rows: dict[int, list[tuple[int, int]]] = {}
    for edge in sorted(effective_edges):
        if int(targets[edge]) in reachable:
            share = 1 if allocation == ngc.RouteAllocation.EQUAL else int(weights[edge])
            rows.setdefault(int(sources[edge]), []).append((edge, share))
    return rows


def propagate(graph, rows, injections, *, reached_only=False):
    """Exact rational propagation of injected amounts through split rows.

    ``rows`` maps a router to its members (EdgeId, positive weight); a router
    splits what it holds in proportion to the weights. Returns the nodes in
    processing order (with ``reached_only``, only those the injections reach),
    the amount each node holds and the amount on each edge. Amounts at a node
    without a row stay there (a destination, or a loss).
    """
    targets = graph.edge_destinations()
    indegree = [0] * graph.num_nodes()
    if reached_only:
        nodes, pending = set(injections), list(injections)
        while pending:
            for edge, _ in rows.get(pending.pop(), ()):
                target = int(targets[edge])
                indegree[target] += 1
                if target not in nodes:
                    nodes.add(target)
                    pending.append(target)
    else:
        nodes = range(graph.num_nodes())
        for members in rows.values():
            for edge, _ in members:
                indegree[int(targets[edge])] += 1
    ready = deque(node for node in sorted(nodes) if indegree[node] == 0)
    incoming: list[Fraction | int] = [0] * len(indegree)
    for node, amount in injections.items():
        incoming[node] += Fraction(amount)
    order, load = [], {}
    while ready:
        node = ready.popleft()
        order.append(node)
        members = rows.get(node, ())
        if incoming[node] > 0 and members:
            denominator = sum(weight for _, weight in members)
            for edge, weight in members:
                share = incoming[node] * weight / denominator
                load[edge] = load.get(edge, 0) + share
                incoming[int(targets[edge])] += share
        for edge, _ in members:
            target = int(targets[edge])
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    return order, incoming, load


def dag_bounds(
    topology,
    dags,
    injections,
    destinations,
    allocation,
    weights,
    label,
    precision,
    *,
    allowed_edges=None,
):
    """Rational split propagation over native-selected DAGs, without capacity/admission."""
    graph = topology.graph
    edges = set()
    for dag in dags:
        edges.update(int(edge) for edge in dag.via_edges())
    if allowed_edges is not None:
        edges.intersection_update(allowed_edges)
    rows = effective_rows(topology, edges, destinations, allocation, weights)
    order, incoming, _ = propagate(graph, rows, injections)
    constraints = []
    for node in order:
        count = len(rows.get(node, ()))
        if node not in destinations and incoming[node] > 0 and count > 1:
            name = (
                topology.node_names[node]
                if node < len(topology.node_names)
                else f"private[{node}]"
            )
            constraints.append(
                split_constraint(
                    "router",
                    f"{label}.router.{name}",
                    incoming[node],
                    count,
                    topology.q,
                    precision,
                )
            )
    return tuple(constraints)


@dataclass(frozen=True)
class _Entry:
    """One live pinned route entry: its head, its share and its DAG, if any."""

    index: int
    tag: object  # the head as the entry's tunnel label names it
    head: int
    weight: int
    siblings: int
    denominator: int
    dag: ngc.PredecessorDAG | None


def _vector(topology, allocation, basis, explicit, residual):
    """The weights a weighted DAG split reads; an empty ledger's residual is capacity."""
    if allocation == ngc.RouteAllocation.EQUAL:
        return None
    if basis == ngc.WeightBasis.EXPLICIT:
        return explicit
    if basis == ngc.WeightBasis.RESIDUAL_SNAPSHOT and residual is not None:
        return residual
    return topology.graph.edge_capacity_units()


def _equal_sources(model: ngc.ShortestPaths) -> bool:
    allocation = model.source_allocation or (
        ngc.SourceAllocation.OPTIMIZED
        if model.allocation == ngc.RouteAllocation.OPTIMIZED
        else ngc.SourceAllocation.EQUAL
    )
    return allocation == ngc.SourceAllocation.EQUAL


def _model_splits(
    topology, named, model, declaration, label, amount, facts, precision, table=None
):
    """Apply the split rules of one native model to one observed amount.

    A demand the WCMP controller programs (``table``) splits equally over its
    sources, then by its destination table.
    """
    constraints = []

    def add(kind, suffix, incoming, members):
        if incoming > 0 and members > 1:
            constraints.append(
                split_constraint(
                    kind, f"{label}.{suffix}", incoming, members, topology.q, precision
                )
            )

    if (
        table is None
        and isinstance(model, ngc.Pinned)
        and not isinstance(declaration, PinnedRoutes)
    ):
        return constraints, (UnverifiedConstraint(label),)
    if amount <= 0:
        return constraints, ()
    heads = facts.tunnel_heads
    if heads is not None:
        assert isinstance(model, (ngc.DistributedTE, ngc.CentralizedTE))
        assert model.tunnel_count is not None
        add("source", "sources", amount, len(heads))
        for head in heads:
            add(
                "tunnel",
                f"head[{head}]",
                amount / len(heads),
                model.tunnel_count.per_head,
            )
    elif table is not None or isinstance(model, ngc.ShortestPaths):
        if table is None:
            assert isinstance(model, ngc.ShortestPaths)
            roster, dags = facts.shortest(model)
            equal, allocation = _equal_sources(model), model.allocation
            basis, explicit = model.weight_basis, model.edge_weights
        else:
            roster, dags = facts.sources, (table.dag,)
            equal, allocation = True, table.encoding
            basis, explicit = ngc.WeightBasis.EXPLICIT, table.weights
        if equal:
            add("source", "sources", amount, len(roster))
        if allocation != ngc.RouteAllocation.OPTIMIZED and roster:
            constraints.extend(
                dag_bounds(
                    topology,
                    dags,
                    {source: amount / len(roster) for source in roster},
                    facts.destinations,
                    allocation,
                    _vector(topology, allocation, basis, explicit, facts.residual),
                    label,
                    precision,
                )
            )
    elif isinstance(model, ngc.Pinned):
        assert isinstance(declaration, PinnedRoutes)
        roster, entries = facts.pinned(declaration)
        add("source", "sources", amount, len(roster))
        allocation = (
            ngc.RouteAllocation.WEIGHTED
            if declaration.allocation == ngc.RouteAllocation.WEIGHTED
            else ngc.RouteAllocation.EQUAL
        )
        explicit = (
            None
            if declaration.edge_weights is None
            else named.weights[declaration.edge_weights]
        )
        for entry in entries:
            if not entry.denominator or not roster or not entry.weight:
                continue
            incoming = amount / len(roster)
            add("tunnel", f"entries.{entry.tag}", incoming, entry.siblings)
            if entry.dag is not None:
                constraints.extend(
                    dag_bounds(
                        topology,
                        (entry.dag,),
                        {entry.head: incoming * entry.weight / entry.denominator},
                        facts.destinations,
                        allocation,
                        _vector(
                            topology,
                            allocation,
                            declaration.weight_basis,
                            explicit,
                            facts.residual,
                        ),
                        f"{label}.entry[{entry.index}]",
                        precision,
                        allowed_edges=facts.allowed,
                    )
                )
    elif (
        isinstance(model, ngc.CentralizedTE)
        and model.source_allocation == ngc.SourceAllocation.EQUAL
    ):
        add("source", "sources", amount, len(facts.sources))
    return constraints, ()


def _unique(constraints):
    return tuple(
        {
            (c.kind, c.label, c.incoming_physical, c.members): c for c in constraints
        }.values()
    )


class _Placed:
    """Facts of one placed demand, read from its native records."""

    allowed = None

    def __init__(self, topology, named, demand, result, records, mask, residual):
        self.topology, self.named, self.demand = topology, named, demand
        self.result, self.records, self.mask = result, records, mask
        self.residual = residual
        self.destinations = {
            topology.node_id_by_name[name] for name in demand.endpoints.destinations
        }

    @property
    def tunnel_heads(self):
        plan = self.result.plan
        return None if plan is None else [head for head, _ in plan.design_by_head]

    def shortest(self, model):
        search = ngc.spf(
            self.topology.graph,
            sorted(self.destinations),
            ngc.SpfOptions(ngc.Direction.REVERSE, eligibility=self.mask),
        )
        distances = search.costs
        assert distances is not None
        sources = [
            self.topology.node_id_by_name[name]
            for name in self.demand.endpoints.sources
        ]
        roster = [source for source in sources if distances[source] != ngc.UNREACHABLE]
        return roster, [record.route for record in self.records]

    @property
    def sources(self):
        return sorted({source for record in self.records for source in record.sources})

    def pinned(self, declaration):
        specs = [self.named.route_specs[name] for name in declaration.routes]
        # An entry the case's eligibility fails gets nothing; only live ones split.
        failed = {
            row.entry_id
            for row in self.result.by_tunnel
            if row.status == ngc.TunnelStatus.FAILED
        }
        live = []
        for record in self.records:
            if record.entry_id is None:
                raise ValueError(
                    f"demand.{self.demand.id}: named pinned entry has no entry_id"
                )
            if record.entry_id not in failed:
                live.append(record)
        entries = []
        for record in live:
            spec = specs[record.entry_id]
            siblings = [
                specs[other.entry_id]
                for other in live
                if specs[other.entry_id].head == spec.head
                and specs[other.entry_id].weight > 0
            ]
            entries.append(
                _Entry(
                    record.entry_id,
                    spec.head,
                    self.topology.node_id_by_name[spec.head],
                    spec.weight,
                    len(siblings),
                    sum(item.weight for item in siblings),
                    record.route if spec.support is not None else None,
                )
            )
        return sorted({source for record in live for source in record.sources}), entries


def placement_splits(
    topology: PreparedTopology,
    named: NamedRoutes,
    demands,
    owners,
    results,
    record_sets,
    mask,
    alpha,
    precision,
    tables=None,
    ordered=True,
):
    """Describe actual native records; never rerun a placement to obtain a report.

    A row is described by its demand's declared model, from the participant's
    records. A controlled row is described from its table: the set's nominal
    one, or the case's own (``tables``, by destination). Under a SIMULTANEOUS
    list (not ``ordered``) every participant was prepared on one common view.
    """
    expansion, incoming = expansion_bounds(
        demands.expansion_template, topology.q, precision, alpha
    )
    parents = {parent.base_id: parent for parent in demands.expansion_template}
    constraints = list(expansion)
    extra = []
    before = (
        [int(value) for value in topology.graph.edge_capacity_units()]
        if residual_weights(named, demands.expansion_template)
        else None
    )
    for demand, result, records in zip(
        demands.demands, results, record_sets, strict=True
    ):
        facts = _Placed(topology, named, demand, result, records, mask, before)
        local, opaque = _model_splits(
            topology,
            named,
            demand.config.routing,
            parents[demand.base_id].policy,
            f"demand.{demand.id}",
            incoming[demand.id],
            facts,
            precision,
            (
                tables[demand.endpoints.destinations[0]]
                if tables is not None
                else demands.controller_table(demand.endpoints.destinations[0])
            )
            if controlled(demands.controller, parents[demand.base_id].policy)
            else None,
        )
        constraints.extend(local)
        extra.extend(opaque)
        # Service and reservation baselines are distinct; only carried flows
        # change the next ordered policy's RESIDUAL_SNAPSHOT weights.
        if before is not None and ordered:
            for record in records:
                for edge, units in record.edge_flows:
                    before[edge] -= units
    return _unique(constraints), tuple(extra)


class _Searched:
    """Facts of one capacity question's pair, from the searches its evaluator makes.

    Every evaluator begins on an empty ledger, so availability equals capacity.
    """

    residual = None

    def __init__(self, topology, named, model, pair, mask, pool=None):
        self.topology, self.named, self.model, self.mask = topology, named, model, mask
        self.roster = (
            [topology.pool_heads[pool.head.pool_id]]
            if pool is not None
            else [topology.node_id_by_name[n] for n in pair.sources]
        )
        self.destinations = {topology.node_id_by_name[n] for n in pair.destinations}

    def _reached(self, mask):
        search = ngc.spf(
            self.topology.graph,
            sorted(self.destinations),
            ngc.SpfOptions(ngc.Direction.REVERSE, eligibility=mask),
        )
        distances = search.costs
        assert distances is not None
        return [
            source for source in self.roster if distances[source] != ngc.UNREACHABLE
        ]

    @cached_property
    def tunnel_heads(self):
        model = self.model
        if isinstance(model, ngc.DistributedTE) or (
            isinstance(model, ngc.CentralizedTE) and model.tunnel_count is not None
        ):
            return self._reached(self.mask)
        return None

    def shortest(self, model):
        # No residual is supplied, so zero-capacity members remain in native SPF.
        dags, roster = [], []
        for source in self.roster:
            search = ngc.spf(
                self.topology.graph,
                sorted(self.destinations),
                ngc.SpfOptions(
                    ngc.Direction.REVERSE,
                    targets=None if model.multipath else source,
                    tie_break=model.tie_break,
                    multipath=model.multipath,
                    parallel_edges=model.parallel_edges,
                    eligibility=self.mask,
                ),
            )
            if model.multipath:
                distances = search.costs
                assert distances is not None
                reached = distances[source] != ngc.UNREACHABLE
            else:
                reached = search.target_cost is not None
            if reached:
                roster.append(source)
                dags.append(search.dag)
        return roster, dags

    @property
    def sources(self):
        model = self.model
        mask = self.mask
        if model.support is not None:
            members = {int(edge) for edge in model.support.via_edges()}
            mask = ngc.Eligibility.intersect(
                mask,
                self.topology.graph.eligibility(
                    excluded_edges=[
                        edge
                        for edge in range(self.topology.graph.num_edges())
                        if edge not in members
                    ]
                ),
            )
        return self._reached(mask)

    @cached_property
    def allowed(self):
        graph = self.topology.graph
        edge_allowed, node_allowed = self.mask.edge_allowed(), self.mask.node_allowed()
        sources, targets = graph.edge_sources(), graph.edge_destinations()
        return {
            edge
            for edge in range(graph.num_edges())
            if edge_allowed[edge]
            and node_allowed[int(sources[edge])]
            and node_allowed[int(targets[edge])]
        }

    def _live(self, definition):
        # Native eligibility repairs the route; only surviving members count.
        route = definition.route
        if not isinstance(route, ngc.PredecessorDAG):
            return all(
                int(edge) in self.allowed for hop in route.hops() for edge in hop
            )
        graph = self.topology.graph
        sources, targets = graph.edge_sources(), graph.edge_destinations()
        parents = [[] for _ in range(graph.num_nodes())]
        for edge in route.via_edges():
            if int(edge) in self.allowed:
                parents[int(targets[edge])].append(int(sources[edge]))
        reachable, pending = set(self.destinations), list(self.destinations)
        while pending:
            for parent in parents[pending.pop()]:
                if parent not in reachable:
                    reachable.add(parent)
                    pending.append(parent)
        return definition.head in reachable

    def pinned(self, declaration):
        definitions = [self.named.routes[name] for name in declaration.routes]
        live = [
            (index, definition)
            for index, definition in enumerate(definitions)
            if self._live(definition)
        ]
        roster = sorted({definition.head for _, definition in live})
        entries = []
        for index, definition in live:
            siblings = [
                other
                for _, other in live
                if other.head == definition.head and other.weight > 0
            ]
            route = definition.route
            entries.append(
                _Entry(
                    index,
                    definition.head,
                    definition.head,
                    definition.weight,
                    len(siblings),
                    sum(other.weight for other in siblings),
                    route if isinstance(route, ngc.PredecessorDAG) else None,
                )
            )
        return roster, entries


def question_inputs(offer, design_demand, declaration):
    """A capacity question's physical atoms, by field, known before evaluation."""
    values = {}
    if offer is not None:
        values["offer"] = ("offer", offer)
    if design_demand is not None:
        values["design_demand"] = ("design", design_demand)
    if isinstance(declaration, _ParsedModel) and isinstance(
        declaration.routing, _DistributedTEInput
    ):
        values["min_unreserved"] = (
            "min_unreserved",
            declaration.routing.min_unreserved_bandwidth,
        )
    return values


def query_has_splits(query) -> bool:
    """Whether this native allocation has local split constraints at all."""
    model = query.config.routing
    return not (
        (
            isinstance(model, ngc.CentralizedTE)
            and model.tunnel_count is None
            and model.source_allocation == ngc.SourceAllocation.OPTIMIZED
        )
        or (
            isinstance(model, ngc.ShortestPaths)
            and model.allocation == ngc.RouteAllocation.OPTIMIZED
            and model.source_allocation in (None, ngc.SourceAllocation.OPTIMIZED)
        )
    )


def query_splits(
    topology,
    named,
    query,
    pair,
    delivered,
    mask,
    label,
    precision,
    pool=None,
    facts=None,
):
    """Describe this native evaluation's splits, without another traffic solve.

    ``facts`` reuses one pair's searches across questions that differ only in
    their tunnel count.
    """
    if not query_has_splits(query):
        return (), ()
    model = query.config.routing
    observed = query.offer is None
    amount = query.offer
    if (
        amount is None
        and query.config.admission == ngc.Admission.LOSSY
        and isinstance(model, ngc.CentralizedTE)
        and model.tunnel_count is not None
        and query.design_demand is not None
    ):
        amount, observed = query.design_demand, False
    if observed:
        amount = Fraction(delivered) * Fraction(topology.q)
    else:
        amount = Fraction(float(amount))
    if facts is None:
        facts = _Searched(topology, named, model, pair, mask, pool)
    declaration = getattr(query, "declaration", None)  # sensitivity has none
    constraints, opaque = _model_splits(
        topology, named, model, declaration, label, amount, facts, precision
    )
    if observed:
        constraints = [replace(c, basis="observed") for c in constraints]
    heads = facts.tunnel_heads
    if heads is not None and query.design_demand is not None:
        assert isinstance(model, (ngc.DistributedTE, ngc.CentralizedTE))
        assert model.tunnel_count is not None
        design = Fraction(float(query.design_demand))
        if design > 0 and (observed or design != amount):
            if len(heads) > 1:
                constraints.append(
                    split_constraint(
                        "source",
                        f"{label}.design.sources",
                        design,
                        len(heads),
                        topology.q,
                        precision,
                    )
                )
            if model.tunnel_count.per_head > 1:
                for head in heads:
                    constraints.append(
                        split_constraint(
                            "tunnel",
                            f"{label}.design.head[{head}]",
                            design / len(heads),
                            model.tunnel_count.per_head,
                            topology.q,
                            precision,
                        )
                    )
    return _unique(constraints), tuple(opaque)


def observed_inputs(prepared: PreparedScenario, inputs):
    """Reuse exact prepared atoms; scaled or query-local atoms remain local."""
    q = prepared.topology.q
    samples, constraints = [], []
    for label, (kind, value) in sorted(inputs.items()):
        cached = prepared._input_observations.get(label)
        if (
            cached is not None
            and (cached[0].kind, cached[0].binary64_value) == (kind, value)
            and (value != 0 or cached[0].binary64_hex == float(value).hex())
        ):
            sample, constraint = cached
        else:
            sample = input_samples({label: (kind, value)}, q)[0]
            constraint = input_constraint(
                label, value, q, prepared.units_report.precision
            )
        samples.append(sample)
        if constraint is not None:
            constraints.append(constraint)
    return tuple(samples), tuple(constraints)


def placement_inputs(prepared: PreparedScenario, demands, alpha):
    """The input observations shared by cases of one fixed-alpha question."""
    parents = {parent.base_id for parent in demands.expansion_template}
    inputs = {
        label: value
        for label, value in prepared._inputs.items()
        if value[0] == "capacity"
        or (
            value[0] == "min_unreserved"
            and any(label == f"demand.{base_id}.min_unreserved" for base_id in parents)
        )
    }
    inputs.update(
        {
            f"demand.{parent.base_id}.volume": (
                "demand",
                float(parent.physical_volume) * float(alpha),
            )
            for parent in demands.expansion_template
        }
    )
    return observed_inputs(prepared, inputs)


def query_inputs(prepared: PreparedScenario, query, label):
    """The input observations of one capacity question, shared by its cases."""
    inputs = {
        name: atom for name, atom in prepared._inputs.items() if atom[0] == "capacity"
    }
    inputs.update(
        {
            f"{label}.{name}": atom
            for name, atom in question_inputs(
                query.offer, query.design_demand, getattr(query, "declaration", None)
            ).items()
        }
    )
    return observed_inputs(prepared, inputs)


def placement_miss(
    prepared: PreparedScenario,
    demands,
    owners,
    results,
    records,
    mask,
    alpha,
    location,
    observations,
    tables=None,
    ordered=True,
) -> PrecisionMiss | None:
    """The missed local targets of one placement on the fixed prepared q.

    ``tables`` are a failure case's controller tables by destination.
    """
    samples, constraints = observations
    splits, opaque = placement_splits(
        prepared.topology,
        prepared._named,
        demands,
        owners,
        results,
        records,
        mask,
        alpha,
        prepared.units_report.precision,
        tables,
        ordered,
    )
    return precision_miss(location, samples, (*constraints, *splits, *opaque))


def query_miss(
    prepared: PreparedScenario, query, observations, location, inputs
) -> PrecisionMiss | None:
    """The missed local targets of one capacity question's evaluations.

    ``observations`` holds (pair, delivered units, eligibility, label, pool)
    rows.
    """
    samples, constraints = inputs
    constraints = list(constraints)
    if query_has_splits(query):
        for pair, delivered, mask, label, pool in observations:
            splits, opaque = query_splits(
                prepared.topology,
                prepared._named,
                query,
                pair,
                delivered,
                mask,
                label,
                prepared.units_report.precision,
                pool,
            )
            constraints.extend((*splits, *opaque))
    return precision_miss(location, samples, constraints)
