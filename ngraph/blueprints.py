from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from itertools import product, zip_longest
from typing import Any, Dict, List

from ngraph.network import Link, Network, Node


@dataclass(slots=True)
class Blueprint:
    """
    Represents a reusable blueprint for hierarchical sub-topologies.

    A blueprint may contain multiple groups of nodes (each can have a node_count
    and a name_template), plus adjacency rules describing how those groups connect.

    Attributes:
        name (str): Unique identifier of this blueprint.
        groups (Dict[str, Any]): A mapping of group_name -> group definition
            (e.g., node_count, name_template, attrs, use_blueprint, etc.).
        adjacency (List[Dict[str, Any]]): A list of adjacency dictionaries
            describing how groups are linked.
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
        blueprints (Dict[str, Blueprint]): Dictionary of blueprint-name -> Blueprint.
        network (Network): The Network into which expanded nodes/links are inserted.
    """

    blueprints: Dict[str, Blueprint]
    network: Network


def expand_network_dsl(data: Dict[str, Any]) -> Network:
    """
    Expands a combined blueprint + network DSL into a complete Network object.

    Overall flow:
      1) Parse "blueprints" into Blueprint objects.
      2) Build a new Network from "network" metadata (e.g. name, version).
      3) Expand 'network["groups"]'.
         - If a group references a blueprint, incorporate that blueprint's subgroups.
         - Otherwise, directly create nodes.
      4) Process any direct node definitions.
      5) Expand adjacency definitions in 'network["adjacency"]'.
      6) Process any direct link definitions.
      7) Process link overrides (applied in order if multiple overrides match).
      8) Process node overrides (applied in order if multiple overrides match).

    Args:
        data (Dict[str, Any]): The YAML-parsed dictionary containing
            optional "blueprints" + "network".

    Returns:
        Network: The fully expanded Network object with all nodes and links.
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
        _expand_group(ctx, parent_path="", group_name=group_name, group_def=group_def)

    # 4) Process direct node definitions
    _process_direct_nodes(ctx.network, network_data)

    # 5) Expand adjacency definitions
    for adj_def in network_data.get("adjacency", []):
        _expand_adjacency(ctx, adj_def)

    # 6) Process direct link definitions
    _process_direct_links(ctx.network, network_data)

    # 7) Process link overrides (in order)
    _process_link_overrides(ctx.network, network_data)

    # 8) Process node overrides (in order)
    _process_node_overrides(ctx.network, network_data)

    return net


def _expand_group(
    ctx: DSLExpansionContext,
    parent_path: str,
    group_name: str,
    group_def: Dict[str, Any],
) -> None:
    """
    Expands a single group definition into either:
      - Another blueprint's subgroups, or
      - A direct node group (with node_count, etc.),
      - Possibly replicating itself if group_name has bracket expansions.

    If 'use_blueprint' is present, we expand that blueprint. Otherwise, we
    create nodes. We also handle bracket expansions in 'group_name' to
    replicate the definition multiple times.

    Args:
        ctx (DSLExpansionContext): The context containing blueprint info and the Network.
        parent_path (str): The parent path in the hierarchy.
        group_name (str): The current group's name (may have bracket expansions).
        group_def (Dict[str, Any]): The group definition (e.g. node_count, use_blueprint, etc.).
    """
    # First, check if group_name has expansions like 'fa[1-16]'
    expanded_names = _expand_name_patterns(group_name)
    if len(expanded_names) > 1 or expanded_names[0] != group_name:
        # We have multiple expansions: replicate group_def for each expanded name
        for expanded_name in expanded_names:
            _expand_group(ctx, parent_path, expanded_name, group_def)
        return

    # No expansions: proceed normally
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
            )

        # Expand blueprint adjacency
        for adj_def in bp.adjacency:
            _expand_blueprint_adjacency(ctx, adj_def, effective_path)

    else:
        # It's a direct node group
        node_count = group_def.get("node_count", 1)
        name_template = group_def.get("name_template", f"{group_name}-{{node_num}}")

        # Start from the user-supplied 'attrs' or create new
        combined_attrs = copy.deepcopy(group_def.get("attrs", {}))

        # Copy any other top-level keys (besides recognized ones) into 'combined_attrs'
        recognized_keys = {
            "node_count",
            "name_template",
            "coords",
            "attrs",
            "use_blueprint",
            "parameters",
        }
        for key, val in group_def.items():
            if key not in recognized_keys:
                combined_attrs[key] = val

        for i in range(1, node_count + 1):
            label = name_template.format(node_num=i)
            node_name = f"{effective_path}/{label}" if effective_path else label
            node = Node(name=node_name)

            # If coords are specified, store them
            if "coords" in group_def:
                node.attrs["coords"] = group_def["coords"]

            # Merge combined_attrs into node.attrs
            node.attrs.update(combined_attrs)

            # Ensure node.attrs has a default "type" if not set
            node.attrs.setdefault("type", "node")

            ctx.network.add_node(node)


def _expand_blueprint_adjacency(
    ctx: DSLExpansionContext,
    adj_def: Dict[str, Any],
    parent_path: str,
) -> None:
    """
    Expands adjacency definitions from within a blueprint, using parent_path
    as the local root. This also handles optional expand_vars.

    Args:
        ctx (DSLExpansionContext): The context object with blueprint info and the network.
        adj_def (Dict[str, Any]): The adjacency definition inside the blueprint,
            containing 'source', 'target', 'pattern', etc.
        parent_path (str): The path serving as the base for the blueprint's node paths.
    """
    expand_vars = adj_def.get("expand_vars", {})
    if expand_vars:
        _expand_adjacency_with_variables(ctx, adj_def, parent_path)
        return

    source_rel = adj_def["source"]
    target_rel = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_params = adj_def.get("link_params", {})
    link_count = adj_def.get("link_count", 1)

    src_path = _join_paths(parent_path, source_rel)
    tgt_path = _join_paths(parent_path, target_rel)

    _expand_adjacency_pattern(ctx, src_path, tgt_path, pattern, link_params, link_count)


def _expand_adjacency(ctx: DSLExpansionContext, adj_def: Dict[str, Any]) -> None:
    """
    Expands a top-level adjacency definition from 'network.adjacency'. If 'expand_vars'
    is provided, we expand the source/target as templates repeatedly.

    Args:
        ctx (DSLExpansionContext): The context containing the target network.
        adj_def (Dict[str, Any]): The adjacency definition dict, containing 'source', 'target',
            and optional 'pattern', 'link_params', 'link_count', 'expand_vars'.
    """
    expand_vars = adj_def.get("expand_vars", {})
    if expand_vars:
        _expand_adjacency_with_variables(ctx, adj_def, parent_path="")
        return

    source_path_raw = adj_def["source"]
    target_path_raw = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_count = adj_def.get("link_count", 1)
    link_params = adj_def.get("link_params", {})

    source_path = _join_paths("", source_path_raw)
    target_path = _join_paths("", target_path_raw)

    _expand_adjacency_pattern(
        ctx, source_path, target_path, pattern, link_params, link_count
    )


def _expand_adjacency_with_variables(
    ctx: DSLExpansionContext, adj_def: Dict[str, Any], parent_path: str
) -> None:
    """
    Handles adjacency expansions when 'expand_vars' is provided.
    We substitute variables into the 'source' and 'target' templates to produce
    multiple adjacency expansions. Then each expansion is passed to _expand_adjacency_pattern.

    Example adjacency entry:
      source: "/ssw-{dc_id}"
      target: "/fa{fa_id}/fadu"
      expand_vars:
        dc_id: [1, 2, 3]
        fa_id: [5, 6]
      pattern: one_to_one
      link_params:
        capacity: 200
        cost: 1
      expansion_mode: "cartesian" or "zip"

    Args:
        ctx (DSLExpansionContext): The DSL expansion context.
        adj_def (Dict[str, Any]): The adjacency definition including expand_vars, source, target, etc.
        parent_path (str): Prepended to source/target if they do not start with '/'.
    """
    source_template = adj_def["source"]
    target_template = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_params = adj_def.get("link_params", {})
    link_count = adj_def.get("link_count", 1)
    expand_vars = adj_def["expand_vars"]
    expansion_mode = adj_def.get("expansion_mode", "cartesian")

    # Sort the variables so we have a consistent order for product or zip
    var_names = sorted(expand_vars.keys())
    lists_of_values = [expand_vars[var] for var in var_names]

    if expansion_mode == "zip":
        # If zip mode, we zip all lists in lockstep. All must be same length or we raise.
        lengths = [len(lst) for lst in lists_of_values]
        if len(set(lengths)) != 1:
            raise ValueError(
                f"zip expansion requires all lists be the same length; got {lengths}"
            )

        for combo_tuple in zip_longest(*lists_of_values, fillvalue=None):
            combo_dict = dict(zip(var_names, combo_tuple))
            expanded_src = _join_paths(
                parent_path, source_template.format(**combo_dict)
            )
            expanded_tgt = _join_paths(
                parent_path, target_template.format(**combo_dict)
            )
            _expand_adjacency_pattern(
                ctx,
                expanded_src,
                expanded_tgt,
                pattern,
                link_params,
                link_count,
            )
    else:
        # "cartesian" by default
        for combo_tuple in product(*lists_of_values):
            combo_dict = dict(zip(var_names, combo_tuple))
            expanded_src = _join_paths(
                parent_path, source_template.format(**combo_dict)
            )
            expanded_tgt = _join_paths(
                parent_path, target_template.format(**combo_dict)
            )
            _expand_adjacency_pattern(
                ctx,
                expanded_src,
                expanded_tgt,
                pattern,
                link_params,
                link_count,
            )


def _expand_adjacency_pattern(
    ctx: DSLExpansionContext,
    source_path: str,
    target_path: str,
    pattern: str,
    link_params: Dict[str, Any],
    link_count: int = 1,
) -> None:
    """
    Generates Link objects for the chosen adjacency pattern among matched nodes.

    Supported Patterns:
      * "mesh": Connect every source node to every target node
                (no self-loops, deduplicate reversed pairs).
      * "one_to_one": Pair each source node with exactly one target node
                      using wrap-around. The larger set size must be
                      a multiple of the smaller set size.

    Args:
        ctx (DSLExpansionContext): The context with the target network.
        source_path (str): Path pattern identifying source node group(s).
        target_path (str): Path pattern identifying target node group(s).
        pattern (str): "mesh" or "one_to_one".
        link_params (Dict[str, Any]): Additional link parameters (capacity, cost, etc.).
        link_count (int): Number of parallel links to create for each adjacency.
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
                if sn.name == tn.name:
                    continue
                pair = tuple(sorted((sn.name, tn.name)))
                if pair not in dedup_pairs:
                    dedup_pairs.add(pair)
                    _create_link(ctx.network, sn.name, tn.name, link_params, link_count)

    elif pattern == "one_to_one":
        s_count = len(source_nodes)
        t_count = len(target_nodes)
        bigger_count = max(s_count, t_count)
        smaller_count = min(s_count, t_count)

        if bigger_count % smaller_count != 0:
            raise ValueError(
                "one_to_one pattern requires sizes with a multiple factor; "
                f"source={s_count}, target={t_count} do not align."
            )

        for i in range(bigger_count):
            if s_count >= t_count:
                sn = source_nodes[i].name
                tn = target_nodes[i % t_count].name
            else:
                sn = source_nodes[i % s_count].name
                tn = target_nodes[i].name

            if sn == tn:
                continue

            pair = tuple(sorted((sn, tn)))
            if pair not in dedup_pairs:
                dedup_pairs.add(pair)
                _create_link(ctx.network, sn, tn, link_params, link_count)
    else:
        raise ValueError(f"Unknown adjacency pattern: {pattern}")


def _create_link(
    net: Network,
    source: str,
    target: str,
    link_params: Dict[str, Any],
    link_count: int = 1,
) -> None:
    """
    Creates and adds one or more Links to the network, applying capacity, cost,
    and attributes from link_params.

    Args:
        net (Network): The network to which the new link(s) will be added.
        source (str): Source node name for the link.
        target (str): Target node name for the link.
        link_params (Dict[str, Any]): Dict possibly containing 'capacity', 'cost', 'attrs'.
        link_count (int): Number of parallel links to create between source and target.
    """
    for _ in range(link_count):
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


def _process_direct_nodes(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes direct node definitions (network_data["nodes"]) and adds them to the network
    if they do not already exist. If the node name already exists, no new node is created.

    Example:
        nodes:
          my_node:
            coords: [10, 20]
            hw_type: "X100"

    Args:
        net (Network): The network to which nodes are added.
        network_data (Dict[str, Any]): DSL data possibly containing a "nodes" dict.
    """
    for node_name, attrs in network_data.get("nodes", {}).items():
        if node_name not in net.nodes:
            new_node = Node(name=node_name, attrs=attrs or {})
            new_node.attrs.setdefault("type", "node")
            net.add_node(new_node)


def _process_direct_links(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes direct link definitions (network_data["links"]) and adds them to the network.

    Example:
        links:
          - source: A
            target: B
            link_params:
              capacity: 100
              cost: 2
              attrs:
                color: "blue"
            link_count: 2

    Args:
        net (Network): The network to which links are added.
        network_data (Dict[str, Any]): DSL data possibly containing a "links" list.
    """
    existing_node_names = set(net.nodes.keys())
    for link_info in network_data.get("links", []):
        source = link_info["source"]
        target = link_info["target"]
        if source not in existing_node_names or target not in existing_node_names:
            raise ValueError(f"Link references unknown node(s): {source}, {target}.")
        if source == target:
            raise ValueError(f"Link cannot have the same source and target: {source}")
        link_params = link_info.get("link_params", {})
        link_count = link_info.get("link_count", 1)
        _create_link(net, source, target, link_params, link_count)


def _process_link_overrides(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes the 'link_overrides' section of the network DSL, updating
    existing links with new parameters. Overrides are applied in order if
    multiple items match the same link.

    Example:
        link_overrides:
          - source: "/region1/*"
            target: "/region2/*"
            link_params:
              capacity: 200
              attrs:
                shared_risk_group: "SRG1"
            any_direction: true

    Args:
        net (Network): The Network whose links will be updated.
        network_data (Dict[str, Any]): DSL data possibly containing 'link_overrides'.
    """
    link_overrides = network_data.get("link_overrides", [])
    for link_override in link_overrides:
        source = link_override["source"]
        target = link_override["target"]
        link_params = link_override["link_params"]
        any_direction = link_override.get("any_direction", True)
        _update_links(net, source, target, link_params, any_direction)


def _process_node_overrides(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes the 'node_overrides' section of the network DSL, updating
    existing nodes with new attributes in bulk. Overrides are applied in order
    if multiple items match the same node.

    Example:
        node_overrides:
          - path: "/region1/spine*"
            attrs:
              hw_type: "DellX"
              shared_risk_group: "SRG2"

    Args:
        net (Network): The Network whose nodes will be updated.
        network_data (Dict[str, Any]): DSL data possibly containing 'node_overrides'.
    """
    node_overrides = network_data.get("node_overrides", [])
    for override in node_overrides:
        path = override["path"]
        attrs_to_set = override["attrs"]
        _update_nodes(net, path, attrs_to_set)


def _update_links(
    net: Network,
    source: str,
    target: str,
    link_params: Dict[str, Any],
    any_direction: bool = True,
) -> None:
    """
    Updates all Link objects between nodes matching 'source' and 'target' paths
    with new parameters.

    If any_direction=True, both (source->target) and (target->source) links
    are updated if present.

    Args:
        net (Network): The network whose links should be updated.
        source (str): A path pattern identifying source node group(s).
        target (str): A path pattern identifying target node group(s).
        link_params (Dict[str, Any]): New parameter values (capacity, cost, attrs).
        any_direction (bool): If True, also update reversed direction links.
    """
    source_node_groups = net.select_node_groups_by_path(source)
    target_node_groups = net.select_node_groups_by_path(target)

    source_nodes = {
        node.name for _, nodes in source_node_groups.items() for node in nodes
    }
    target_nodes = {
        node.name for _, nodes in target_node_groups.items() for node in nodes
    }

    for link in net.links.values():
        forward_match = link.source in source_nodes and link.target in target_nodes
        reverse_match = (
            any_direction
            and link.source in target_nodes
            and link.target in source_nodes
        )
        if forward_match or reverse_match:
            link.capacity = link_params.get("capacity", link.capacity)
            link.cost = link_params.get("cost", link.cost)
            link.attrs.update(link_params.get("attrs", {}))


def _update_nodes(net: Network, path: str, attrs: Dict[str, Any]) -> None:
    """
    Updates attributes on all nodes matching a given path pattern.

    Args:
        net (Network): The network containing the nodes.
        path (str): A path pattern identifying which node group(s) to modify.
        attrs (Dict[str, Any]): A dictionary of new attributes to set/merge.
    """
    node_groups = net.select_node_groups_by_path(path)
    for _, nodes in node_groups.items():
        for node in nodes:
            node.attrs.update(attrs)


def _apply_parameters(
    subgroup_name: str, subgroup_def: Dict[str, Any], params_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Applies user-provided parameter overrides to a blueprint subgroup.

    Example:
        If 'spine.node_count' = 6 is in params_overrides,
        it sets 'node_count' = 6 for the 'spine' subgroup.
        If 'spine.attrs.hw_type' = 'Dell', it sets subgroup_def['attrs']['hw_type'] = 'Dell'.

    Args:
        subgroup_name (str): Name of the subgroup in the blueprint (e.g. 'spine').
        subgroup_def (Dict[str, Any]): The default definition of that subgroup.
        params_overrides (Dict[str, Any]): Overrides in the form of
            {'spine.node_count': 6, 'spine.attrs.hw_type': 'Dell'}.

    Returns:
        Dict[str, Any]: A copy of subgroup_def with parameter overrides applied.
    """
    out = copy.deepcopy(subgroup_def)

    for key, val in params_overrides.items():
        parts = key.split(".")
        if parts[0] == subgroup_name and len(parts) > 1:
            # We have a dotted path that might refer to nested dictionaries.
            subpath = parts[1:]
            _apply_nested_path(out, subpath, val)

    return out


def _apply_nested_path(
    node_def: Dict[str, Any], path_parts: List[str], value: Any
) -> None:
    """
    Recursively applies a path like ["attrs", "role"] to set node_def["attrs"]["role"] = value.
    Creates intermediate dicts as needed.

    Args:
        node_def (Dict[str, Any]): The dictionary to update.
        path_parts (List[str]): List of keys specifying nested fields.
        value (Any): The value to set in the nested field.
    """
    if not path_parts:
        return
    key = path_parts[0]
    if len(path_parts) == 1:
        node_def[key] = value
        return
    if key not in node_def or not isinstance(node_def[key], dict):
        node_def[key] = {}
    _apply_nested_path(node_def[key], path_parts[1:], value)


_RANGE_REGEX = re.compile(r"\[([^\]]+)\]")


def _expand_name_patterns(name: str) -> List[str]:
    """
    Parses and expands bracketed expressions in a group name. For example:

        "fa[1-3]" -> ["fa1", "fa2", "fa3"]
        "dc[1,3,5-6]" -> ["dc1", "dc3", "dc5", "dc6"]
        "fa[1-2]_plane[5-6]" ->
          ["fa1_plane5", "fa1_plane6", "fa2_plane5", "fa2_plane6"]

    If no bracket expressions are present, returns [name] unchanged.

    Args:
        name (str): A group name that may contain bracket expansions.

    Returns:
        List[str]: All expanded names. If no expansion was needed, returns
            a single-element list with 'name' itself.
    """
    matches = list(_RANGE_REGEX.finditer(name))
    if not matches:
        return [name]  # no expansions

    expansions_list = []
    for match in matches:
        range_expr = match.group(1)
        expansions_list.append(_parse_range_expr(range_expr))

    expanded_names = []
    for combo in product(*expansions_list):
        result_str = ""
        last_end = 0
        for m_idx, match in enumerate(matches):
            start, end = match.span()
            result_str += name[last_end:start]
            result_str += combo[m_idx]
            last_end = end
        result_str += name[last_end:]
        expanded_names.append(result_str)

    return expanded_names


def _parse_range_expr(expr: str) -> List[str]:
    """
    Parses a bracket expression that might have commas, single values, and dash ranges.
    For example: "1-3,5,7-9" -> ["1", "2", "3", "5", "7", "8", "9"].

    Args:
        expr (str): The raw expression from inside brackets, e.g. "1-3,5,7-9".

    Returns:
        List[str]: A sorted list of all string expansions.
    """
    values = []
    parts = [x.strip() for x in expr.split(",")]
    for part in parts:
        if "-" in part:
            start_str, end_str = part.split("-", 1)
            start = int(start_str)
            end = int(end_str)
            for val in range(start, end + 1):
                values.append(str(val))
        else:
            values.append(part)
    return values


def _join_paths(parent_path: str, rel_path: str) -> str:
    """
    Joins two path segments according to NetGraph's DSL conventions:

    - If rel_path starts with '/', we strip the leading slash and treat it as
      appended to parent_path if parent_path is not empty.
    - Otherwise, simply append rel_path to parent_path if parent_path is non-empty.

    Args:
        parent_path (str): The existing path prefix.
        rel_path (str): A relative path that may start with '/'.

    Returns:
        str: The combined path as a single string.
    """
    if rel_path.startswith("/"):
        rel_path = rel_path[1:]
        if parent_path:
            return f"{parent_path}/{rel_path}"
        return rel_path

    if parent_path:
        return f"{parent_path}/{rel_path}"
    return rel_path
