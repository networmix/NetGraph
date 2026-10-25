"""Closed YAML declarations for native routing and named physical references."""

from functools import partial

import netgraph_core as ngc

from ngraph.dsl.expansion.variables import _expand_declaration
from ngraph.model.demand import (
    ControllerGroup,
    DemandSet,
    DemandSpec,
    EdgeWeight,
    FlowPolicyPreset,
    ForwardingGroup,
    GroupChild,
    PinnedRoutes,
    RouteSpec,
    RoutingDomain,
    SupportSpec,
    WCMPController,
    WeightSpec,
    _CentralizedTEInput,
    _DistributedTEInput,
    _ParsedModel,
    _ShortestPathsInput,
)
from ngraph.model.network import DirectedLink
from ngraph.model.selectors import normalize_selector
from ngraph.utils.values import exact_fraction, flag, integer, physical
from ngraph.utils.yaml_utils import (
    check_no_extra_keys,
    declared,
    normalize_yaml_dict_keys,
)

OUTPUT_FLAGS = (
    "edge_flows",
    "residual",
    "edge_reservations",
    "saturated_boundary_edges",
    "min_cut",
)


def mapping(value, label):
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected mapping")
    return value


def closed(value, keys, label):
    value = mapping(value, label)
    check_no_extra_keys(value, set(keys), label)
    return value


def boolean(value, label):
    return flag(value, label)


def enum(kind, value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}: expected lowercase enum name")
    try:
        result = kind.__members__[value.upper()]
    except KeyError as exc:
        raise ValueError(f"{label}: unknown value {value!r}") from exc
    if value != value.lower():
        raise ValueError(f"{label}: expected lowercase enum name")
    return result


def names(value, label, *, nonempty=False):
    if (
        not isinstance(value, list)
        or not all(isinstance(n, str) and n for n in value)
        or (nonempty and not value)
    ):
        raise ValueError(
            f"{label}: expected {'nonempty ' if nonempty else ''}list of names"
        )
    return tuple(value)


def directed(value, label):
    value = closed(value, ("link", "direction"), label)
    if set(value) != {"link", "direction"}:
        raise ValueError(f"{label}: link and direction are required")
    return declared(
        label,
        lambda: DirectedLink(value["link"], value["direction"]),
        f"link {value['link']}",
    )


def tunnel_count(value, label):
    value = closed(value, ("per_head", "up_to"), label)
    count = integer(
        value.get("per_head"), label + ".per_head", minimum=1, maximum=10001
    )
    return ngc.TunnelCount(
        count, up_to=boolean(value.get("up_to", False), label + ".up_to")
    )


def ceiling(value, label):
    value = closed(value, ("type", "value"), label)
    if set(value) != {"type", "value"}:
        raise ValueError(f"{label}: type and value are required")
    if value["type"] == "absolute":
        return ngc.AbsoluteCost(integer(value["value"], label + ".value"))
    if value["type"] == "stretch":
        return ngc.CostStretch(exact_fraction(value["value"], f"{label}.value"))
    raise ValueError(f"{label}.type: expected absolute or stretch")


def policy(value, label):
    """Parse one discriminated model, retaining physical T1 minimum until q is fixed."""
    try:
        if "preset" in value and "model" in value:
            raise ValueError(f"{label}: preset and model are exclusive")
        if "model" not in value:
            try:
                return FlowPolicyPreset(value.get("preset", "SHORTEST_PATHS_ECMP"))
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{label}.preset: unknown preset {value.get('preset')!r}"
                ) from exc
        model = closed(value["model"], ("routing", "admission"), label + ".model")
        admission = enum(
            ngc.Admission,
            model.get("admission", "lossless"),
            label + ".model.admission",
        )
        routing = mapping(model.get("routing"), label + ".model.routing")
        kind = routing.get("type")
        location = label + ".model.routing"
        if kind == "shortest_paths":
            closed(
                routing,
                (
                    "type",
                    "allocation",
                    "source_allocation",
                    "weight_basis",
                    "edge_weights",
                    "tie_break",
                    "multipath",
                    "parallel_edges",
                ),
                location,
            )
            allocation = enum(
                ngc.RouteAllocation,
                routing.get("allocation", "equal"),
                location + ".allocation",
            )
            source = (
                None
                if routing.get("source_allocation") is None
                else enum(
                    ngc.SourceAllocation,
                    routing["source_allocation"],
                    location + ".source_allocation",
                )
            )
            basis = (
                None
                if routing.get("weight_basis") is None
                else enum(
                    ngc.WeightBasis, routing["weight_basis"], location + ".weight_basis"
                )
            )
            weight = routing.get("edge_weights")
            if weight is not None and (not isinstance(weight, str) or not weight):
                raise ValueError(f"{location}.edge_weights: expected a name")
            tie = enum(
                ngc.RouteTieBreak,
                routing.get("tie_break", "fewer_hops"),
                location + ".tie_break",
            )
            multipath = boolean(routing.get("multipath", True), location + ".multipath")
            parallel = boolean(
                routing.get("parallel_edges", True), location + ".parallel_edges"
            )
            # Check combinations now; graph-size validation uses the named vector at preparation.
            ngc.ShortestPaths(
                allocation=allocation,
                source_allocation=source,
                weight_basis=basis,
                edge_weights=None if weight is None else [0],
                tie_break=tie,
                multipath=multipath,
                parallel_edges=parallel,
            )
            parsed = _ShortestPathsInput(
                allocation, source, basis, weight, tie, multipath, parallel
            )
        elif kind == "distributed_te":
            closed(
                routing,
                (
                    "type",
                    "tunnel_count",
                    "cost_ceiling",
                    "min_unreserved_bandwidth",
                    "tie_break",
                    "parallel_edges",
                ),
                location,
            )
            count = tunnel_count(
                routing.get("tunnel_count"), location + ".tunnel_count"
            )
            cap = (
                None
                if routing.get("cost_ceiling") is None
                else ceiling(routing["cost_ceiling"], location + ".cost_ceiling")
            )
            minimum = physical(
                routing.get("min_unreserved_bandwidth", 0),
                location + ".min_unreserved_bandwidth",
            )
            tie = enum(
                ngc.RouteTieBreak,
                routing.get("tie_break", "fewer_hops"),
                location + ".tie_break",
            )
            parallel = boolean(
                routing.get("parallel_edges", True), location + ".parallel_edges"
            )
            ngc.DistributedTE(
                count, cost_ceiling=cap, tie_break=tie, parallel_edges=parallel
            )
            parsed = _DistributedTEInput(count, cap, minimum, tie, parallel)
        elif kind == "centralized_te":
            closed(
                routing,
                ("type", "source_allocation", "tunnel_count", "prefer_headroom"),
                location,
            )
            source = enum(
                ngc.SourceAllocation,
                routing.get("source_allocation"),
                location + ".source_allocation",
            )
            count = (
                None
                if routing.get("tunnel_count") is None
                else tunnel_count(routing["tunnel_count"], location + ".tunnel_count")
            )
            headroom = boolean(
                routing.get("prefer_headroom", False), location + ".prefer_headroom"
            )
            ngc.CentralizedTE(
                source_allocation=source, tunnel_count=count, prefer_headroom=headroom
            )
            parsed = _CentralizedTEInput(source, count, headroom)
        elif kind == "pinned":
            closed(
                routing,
                ("type", "routes", "allocation", "weight_basis", "edge_weights"),
                location,
            )
            return PinnedRoutes(
                names(routing.get("routes"), location + ".routes", nonempty=True),
                admission,
                None
                if routing.get("allocation") is None
                else enum(
                    ngc.RouteAllocation, routing["allocation"], location + ".allocation"
                ),
                None
                if routing.get("weight_basis") is None
                else enum(
                    ngc.WeightBasis, routing["weight_basis"], location + ".weight_basis"
                ),
                routing.get("edge_weights"),
            )
        else:
            raise ValueError(f"{location}.type: unknown routing type {kind!r}")
        return _ParsedModel(parsed, admission)
    except (ValueError, TypeError) as exc:
        if str(exc).startswith(label + ":") or str(exc).startswith(label + "."):
            raise
        raise type(exc)(f"{label}: {exc}") from exc


def named_declarations(data):
    """Own the three separate namespaces without resolving physical identities yet."""
    supports, weights, routes = {}, {}, {}
    for name, spec in mapping(data.get("supports") or {}, "supports").items():
        closed(spec, ("edges",), f"supports.{name}")
        if not isinstance(spec.get("edges"), list):
            raise ValueError(f"supports.{name}.edges: expected list")
        supports[name] = SupportSpec(
            tuple(
                directed(edge, f"supports.{name}.edges[{i}]")
                for i, edge in enumerate(spec["edges"])
            )
        )
    for name, spec in mapping(data.get("weights") or {}, "weights").items():
        closed(spec, ("entries",), f"weights.{name}")
        if not isinstance(spec.get("entries"), list):
            raise ValueError(f"weights.{name}.entries: expected list")
        entries = []
        for i, entry in enumerate(spec["entries"]):
            label = f"weights.{name}.entries[{i}]"
            closed(entry, ("edge", "value"), label)
            entries.append(
                EdgeWeight(
                    directed(entry.get("edge"), label + ".edge"), entry.get("value")
                )
            )
        weights[name] = WeightSpec(tuple(entries))
    for name, spec in mapping(data.get("routes") or {}, "routes").items():
        label = f"routes.{name}"
        closed(spec, ("head", "nodes", "edges", "support", "weight"), label)
        edges = spec.get("edges")
        if edges is not None and not isinstance(edges, list):
            raise ValueError(f"{label}.edges: expected list")
        nodes = (
            names(spec["nodes"], label + ".nodes")
            if spec.get("nodes") is not None
            else None
        )
        hops = (
            None
            if edges is None
            else tuple(directed(edge, label + ".edges") for edge in edges)
        )
        routes[name] = declared(
            label,
            lambda spec=spec, nodes=nodes, hops=hops: RouteSpec(
                spec.get("head"),
                nodes,
                hops,
                spec.get("support"),
                spec.get("weight", 1),
            ),
            "route",
        )
    return routes, supports, weights


def _group_child(value, label):
    value = closed(value, ("share", "edge", "children"), label)
    children = value.get("children")
    if children is not None:
        if not isinstance(children, list):
            raise ValueError(f"{label}.children: expected list")
        children = tuple(
            _group_child(child, f"{label}.children[{i}]")
            for i, child in enumerate(children)
        )
    edge = (
        None if value.get("edge") is None else directed(value["edge"], f"{label}.edge")
    )
    return declared(
        label, lambda: GroupChild(value.get("share", 1), edge, children), "group_child"
    )


def controller_declarations(data):
    """The routing domain, the WCMP controller and the forwarding groups, if declared."""
    routing = data.get("routing")
    if routing is not None:
        routing = closed(routing, ("igp_domain", "bgp_edge"), "routing")
        if set(routing) != {"igp_domain", "bgp_edge"}:
            raise ValueError("routing: igp_domain and bgp_edge are required")
        routing = RoutingDomain(
            normalize_selector(routing["igp_domain"], "demand"),
            normalize_selector(routing["bgp_edge"], "demand"),
        )
    controller = data.get("wcmp_controller")
    if controller is not None:
        controller = WCMPController(**closed(controller, ("scope",), "wcmp_controller"))
    groups = {}
    raw = normalize_yaml_dict_keys(
        mapping(data.get("forwarding_groups") or {}, "forwarding_groups")
    )
    for name, spec in raw.items():
        label = f"forwarding_groups.{name}"
        spec = closed(spec, ("router", "groups"), label)
        if set(spec) != {"router", "groups"} or not isinstance(spec["groups"], list):
            raise ValueError(f"{label}: router and a list of groups are required")
        roots = []
        for i, group in enumerate(spec["groups"]):
            group_label = f"{label}.groups[{i}]"
            group = closed(group, ("share", "children"), group_label)
            children = group.get("children")
            if not isinstance(children, list):
                raise ValueError(f"{group_label}.children: expected list")
            members = tuple(
                _group_child(child, f"{group_label}.children[{j}]")
                for j, child in enumerate(children)
            )
            roots.append(
                declared(
                    group_label,
                    lambda members=members, group=group: ControllerGroup(
                        members, group.get("share", 1)
                    ),
                    "controller_group",
                )
            )
        groups[name] = declared(
            label,
            lambda spec=spec, roots=roots: ForwardingGroup(
                spec["router"], tuple(roots)
            ),
            "forwarding_group",
        )
    return routing, controller, groups


def demand_sets(raw):
    result = {}
    for name, declarations in normalize_yaml_dict_keys(mapping(raw, "demands")).items():
        if not isinstance(declarations, list):
            raise ValueError(f"demands.{name}: expected list")
        demands = []
        for ordinal, declaration in enumerate(declarations):
            label = f"demands.{name}[{ordinal}]"
            closed(
                declaration,
                (
                    "id",
                    "source",
                    "target",
                    "volume",
                    "priority",
                    "mode",
                    "group_mode",
                    "preset",
                    "model",
                    "attrs",
                    "expand",
                ),
                label,
            )
            expanded, rows = _expand_declaration(declaration, label)
            for index, row in enumerate(rows):
                identity = row.get("id")
                if identity is None:
                    identity = f"{name}|{ordinal}"
                if not isinstance(identity, str) or not identity:
                    raise ValueError(
                        f"{label}.id: expected nonempty string, got {identity!r}"
                    )
                source, target = (
                    declared(
                        f"{label}.{end}",
                        partial(normalize_selector, row[end], "demand"),
                        "selector",
                    )
                    for end in ("source", "target")
                )
                build = partial(
                    DemandSpec,
                    source,
                    target,
                    row.get("volume", 0),
                    policy(row, label),
                    identity,
                    row.get("priority", 0),
                    row.get("mode", "combine"),
                    row.get("group_mode", "flatten"),
                    row.get("attrs", {}),
                    # Declaration identity, independent of the display id's delimiters.
                    yaml_label=label,
                    declaration_ordinal=ordinal,
                    expand_leaf_index=index if expanded else None,
                )
                demand = declared(label, build, "demand")
                demands.append(demand)
        result[name] = DemandSet(name, tuple(demands))
    return result


def flow_outputs(arguments, name):
    """A flow step's YAML ``outputs`` as native options, cost and detail flags."""
    label = f"workflow step {name}"
    for key, replacement in (
        ("export_details", "outputs.details"),
        ("export_cost_distribution", "outputs.cost_distribution"),
    ):
        if key in arguments:
            raise ValueError(f"{label}: unknown key {key}; use {replacement}")
    native, cost, details = outputs(arguments.get("outputs", {}), f"{label}.outputs")
    arguments["outputs"] = native
    arguments["export_cost_distribution"] = cost
    arguments["export_details"] = details
    return arguments


def outputs(raw, label):
    raw = closed(raw, (*OUTPUT_FLAGS, "cost_distribution", "details"), label)
    values = {name: boolean(value, label + "." + name) for name, value in raw.items()}
    cost = values.pop("cost_distribution", False)
    details = values.pop("details", False)
    return ngc.OutputOptions(**values), cost, details
