from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Dict, List

from ngraph.network import Network, Node, Link


@dataclass(slots=True)
class Blueprint:
    """
    Represents a reusable blueprint for hierarchical sub-topologies.

    A blueprint may contain multiple groups of nodes (each can have a node_count
    and a name_template), plus adjacency rules describing how those groups connect.

    Attributes:
        name: Unique identifier of this blueprint.
        groups: A mapping of group_name -> group definition (e.g. node_count, name_template).
        adjacency: A list of adjacency dictionaries describing how groups are linked.
    """

    name: str
    groups: Dict[str, Any]
    adjacency: List[Dict[str, Any]]


@dataclass(slots=True)
class DSLExpansionContext:
    """
    Carries the blueprint definitions and the final Network instance
    to be populated during DSL expansion.

    Attributes:
        blueprints: A dictionary of blueprint name -> Blueprint object.
        network: The Network into which expanded nodes/links will be inserted.
    """

    blueprints: Dict[str, Blueprint]
    network: Network


def expand_network_dsl(data: Dict[str, Any]) -> Network:
    """
    Expands a combined blueprint + network DSL into a complete Network object.

    Overall flow:
      1) Parse "blueprints" into Blueprint objects.
      2) Build a new Network from "network" metadata (name, version, etc.).
      3) Expand 'network["groups"]':
         - If a group references a blueprint, incorporate that blueprint's subgroups.
         - Otherwise, directly create nodes (e.g., node_count).
      4) Process any direct node definitions.
      5) Expand adjacency definitions in 'network["adjacency"]'.
      6) Process any direct link definitions.

    Args:
        data: The YAML-parsed dictionary containing optional "blueprints" + "network".

    Returns:
        A fully expanded Network object with all nodes and links.
    """
    # 1) Parse blueprint definitions
    blueprint_map: Dict[str, Blueprint] = {}
    for bp_name, bp_data in data.get("blueprints", {}).items():
        blueprint_map[bp_name] = Blueprint(
            name=bp_name,
            groups=bp_data.get("groups", {}),
            adjacency=bp_data.get("adjacency", []),
        )

    # 2) Initialize the Network from "network" metadata
    network_data = data.get("network", {})
    net = Network()
    if "name" in network_data:
        net.attrs["name"] = network_data["name"]
    if "version" in network_data:
        net.attrs["version"] = network_data["version"]

    # Create a context
    ctx = DSLExpansionContext(blueprints=blueprint_map, network=net)

    # 3) Expand top-level groups
    for group_name, group_def in network_data.get("groups", {}).items():
        _expand_group(
            ctx,
            parent_path="",
            group_name=group_name,
            group_def=group_def,
            blueprint_expansion=False,
        )

    # 4) Process direct node definitions
    _process_direct_nodes(ctx.network, network_data)

    # 5) Expand adjacency definitions
    for adj_def in network_data.get("adjacency", []):
        _expand_adjacency(ctx, adj_def)

    # 6) Process direct link definitions
    _process_direct_links(ctx.network, network_data)

    return net


def _expand_group(
    ctx: DSLExpansionContext,
    parent_path: str,
    group_name: str,
    group_def: Dict[str, Any],
    *,
    blueprint_expansion: bool = False,
) -> None:
    """
    Expands a single group definition into either:
      - Another blueprint's subgroups, or
      - A direct node group (node_count, name_template).

    We do *not* skip the subgroup name even inside blueprint expansion, because
    typically the 'group_name' is "leaf"/"spine" etc., not the blueprint’s name.

    So the final path is always 'parent_path + "/" + group_name' if parent_path is non-empty,
    otherwise just group_name.
    """
    # Construct the effective path by appending group_name if parent_path is non-empty
    if parent_path:
        effective_path = f"{parent_path}/{group_name}"
    else:
        effective_path = group_name

    if "use_blueprint" in group_def:
        # Expand blueprint subgroups
        blueprint_name: str = group_def["use_blueprint"]
        bp = ctx.blueprints.get(blueprint_name)
        if not bp:
            raise ValueError(
                f"Group '{group_name}' references unknown blueprint '{blueprint_name}'."
            )

        param_overrides: Dict[str, Any] = group_def.get("parameters", {})
        coords = group_def.get("coords")

        # For each subgroup in the blueprint, apply overrides and expand
        for bp_sub_name, bp_sub_def in bp.groups.items():
            merged_def = _apply_parameters(bp_sub_name, bp_sub_def, param_overrides)
            if coords is not None and "coords" not in merged_def:
                merged_def["coords"] = coords

            _expand_group(
                ctx,
                parent_path=effective_path,
                group_name=bp_sub_name,
                group_def=merged_def,
                blueprint_expansion=True,
            )

        # Expand blueprint adjacency
        for adj_def in bp.adjacency:
            _expand_blueprint_adjacency(ctx, adj_def, effective_path)

    else:
        # It's a direct node group
        node_count = group_def.get("node_count", 1)
        name_template = group_def.get("name_template", f"{group_name}-{{node_num}}")

        for i in range(1, node_count + 1):
            label = name_template.format(node_num=i)
            node_name = f"{effective_path}/{label}" if effective_path else label

            node = Node(name=node_name)
            if "coords" in group_def:
                node.attrs["coords"] = group_def["coords"]
            node.attrs.setdefault("type", "node")

            ctx.network.add_node(node)


def _expand_blueprint_adjacency(
    ctx: DSLExpansionContext,
    adj_def: Dict[str, Any],
    parent_path: str,
) -> None:
    """
    Expands adjacency definitions from within a blueprint, using parent_path as the local root.
    """
    source_rel = adj_def["source"]
    target_rel = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_params = adj_def.get("link_params", {})

    src_path = _join_paths(parent_path, source_rel)
    tgt_path = _join_paths(parent_path, target_rel)

    _expand_adjacency_pattern(ctx, src_path, tgt_path, pattern, link_params)


def _expand_adjacency(
    ctx: DSLExpansionContext,
    adj_def: Dict[str, Any],
) -> None:
    """
    Expands a top-level adjacency definition from 'network.adjacency'.
    """
    source_path_raw = adj_def["source"]
    target_path_raw = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_params = adj_def.get("link_params", {})

    # Strip leading '/' from source/target paths
    source_path = _join_paths("", source_path_raw)
    target_path = _join_paths("", target_path_raw)

    _expand_adjacency_pattern(ctx, source_path, target_path, pattern, link_params)


def _expand_adjacency_pattern(
    ctx: DSLExpansionContext,
    source_path: str,
    target_path: str,
    pattern: str,
    link_params: Dict[str, Any],
) -> None:
    """
    Generates Link objects for the chosen adjacency pattern among matched nodes.

    Supported Patterns:
      * "mesh": Cross-connect every node from source side to every node on target side,
                skipping self-loops, and deduplicating reversed pairs.
      * "one_to_one": Pair each source node with exactly one target node, supporting
                      wrap-around if one side is an integer multiple of the other.
                      Also skips self-loops.
    """
    source_node_groups = ctx.network.select_node_groups_by_path(source_path)
    target_node_groups = ctx.network.select_node_groups_by_path(target_path)

    source_nodes = [node for _, nodes in source_node_groups.items() for node in nodes]
    target_nodes = [node for _, nodes in target_node_groups.items() for node in nodes]

    if not source_nodes or not target_nodes:
        return

    dedup_pairs = set()

    if pattern == "mesh":
        for sn in source_nodes:
            for tn in target_nodes:
                # Skip self-loops
                if sn.name == tn.name:
                    continue
                pair = tuple(sorted((sn.name, tn.name)))
                if pair not in dedup_pairs:
                    dedup_pairs.add(pair)
                    _create_link(ctx.network, sn.name, tn.name, link_params)

    elif pattern == "one_to_one":
        s_count = len(source_nodes)
        t_count = len(target_nodes)
        bigger, smaller = max(s_count, t_count), min(s_count, t_count)

        if bigger % smaller != 0:
            raise ValueError(
                f"one_to_one pattern requires either equal node counts "
                f"or a valid wrap-around. Got {s_count} vs {t_count}."
            )

        # total 'bigger' connections
        for i in range(bigger):
            if s_count >= t_count:
                sn = source_nodes[i].name
                tn = target_nodes[i % t_count].name
            else:
                sn = source_nodes[i % s_count].name
                tn = target_nodes[i].name

            # Skip self-loops
            if sn == tn:
                continue

            pair = tuple(sorted((sn, tn)))
            if pair not in dedup_pairs:
                dedup_pairs.add(pair)
                _create_link(ctx.network, sn, tn, link_params)

    else:
        raise ValueError(f"Unknown adjacency pattern: {pattern}")


def _create_link(
    net: Network, source: str, target: str, link_params: Dict[str, Any]
) -> None:
    """
    Creates and adds a Link to the network, applying capacity/cost/attrs from link_params.
    """
    capacity = link_params.get("capacity", 1.0)
    cost = link_params.get("cost", 1.0)
    attrs = copy.deepcopy(link_params.get("attrs", {}))

    link = Link(
        source=source,
        target=target,
        capacity=capacity,
        cost=cost,
        attrs=attrs,
    )
    net.add_link(link)


def _apply_parameters(
    subgroup_name: str, subgroup_def: Dict[str, Any], params_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Applies user-provided parameter overrides to a blueprint subgroup.

    E.g.:
      if 'spine.node_count' = 6 is in params_overrides,
      we set 'node_count'=6 for the 'spine' subgroup.
    """
    out = dict(subgroup_def)
    for key, val in params_overrides.items():
        parts = key.split(".")
        if parts[0] == subgroup_name and len(parts) > 1:
            field_name = ".".join(parts[1:])
            out[field_name] = val
    return out


def _join_paths(parent_path: str, rel_path: str) -> str:
    """
    If rel_path starts with '/', interpret that as relative to 'parent_path';
    otherwise, simply append rel_path to parent_path with '/' if needed.
    """
    if rel_path.startswith("/"):
        rel_path = rel_path[1:]
        if parent_path:
            return f"{parent_path}/{rel_path}"
        else:
            return rel_path
    if parent_path:
        return f"{parent_path}/{rel_path}"
    return rel_path


def _process_direct_nodes(net: Network, network_data: Dict[str, Any]) -> None:
    """Processes direct node definitions (network_data["nodes"])."""
    for node_name, node_attrs in network_data.get("nodes", {}).items():
        if node_name not in net.nodes:
            new_node = Node(name=node_name, attrs=node_attrs or {})
            new_node.attrs.setdefault("type", "node")
            net.add_node(new_node)


def _process_direct_links(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes direct link definitions (network_data["links"]).
    """
    existing_node_names = set(net.nodes.keys())
    for link_info in network_data.get("links", []):
        source = link_info["source"]
        target = link_info["target"]
        if source not in existing_node_names or target not in existing_node_names:
            raise ValueError(f"Link references unknown node(s): {source}, {target}.")
        link_params = link_info.get("link_params", {})
        link = Link(
            source=source,
            target=target,
            capacity=link_params.get("capacity", 1.0),
            cost=link_params.get("cost", 1.0),
            attrs=link_params.get("attrs", {}),
        )
        net.add_link(link)
