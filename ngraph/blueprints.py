from dataclasses import dataclass
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
            (e.g. node_count, name_template, node_attrs).
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
        blueprints (Dict[str, Blueprint]): A dictionary of blueprint-name ->
            Blueprint object.
        network (Network): The Network into which expanded nodes/links
            will be inserted.
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
         - Otherwise, directly create nodes (e.g., node_count).
      4) Process any direct node definitions.
      5) Expand adjacency definitions in 'network["adjacency"]'.
      6) Process any direct link definitions.
      7) Process link overrides.
      8) Process node overrides.

    Args:
        data (Dict[str, Any]): The YAML-parsed dictionary containing
            optional "blueprints" + "network".

    Returns:
        Network: A fully expanded Network object with all nodes and links.
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

    # 3) Expand top-level groups (blueprint usage or direct node groups)
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

    # 7) Process link overrides
    _process_link_overrides(ctx.network, network_data)

    # 8) Process node overrides
    _process_node_overrides(ctx.network, network_data)

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
      - A direct node group (node_count, name_template, node_attrs).

    If the group references 'use_blueprint', we expand that blueprint's groups
    under the current hierarchy path. Otherwise, we create nodes directly.

    Args:
        ctx (DSLExpansionContext): The context containing all blueprint info
            and the target Network.
        parent_path (str): The parent path in the hierarchy.
        group_name (str): The current group's name.
        group_def (Dict[str, Any]): The group definition (e.g. {node_count, name_template}
            or {use_blueprint, parameters, ...}).
        blueprint_expansion (bool): Indicates whether we are expanding within
            a blueprint context or not.
    """
    if parent_path:
        effective_path = f"{parent_path}/{group_name}"
    else:
        effective_path = group_name

    if "use_blueprint" in group_def:
        # Expand blueprint subgroups
        blueprint_name: str = group_def["use_blueprint"]
        try:
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

        except Exception as e:
            raise ValueError(f"Error expanding blueprint '{blueprint_name}': {e}")
    else:
        # It's a direct node group
        node_count = group_def.get("node_count", 1)
        name_template = group_def.get("name_template", f"{group_name}-{{node_num}}")
        node_attrs = group_def.get("node_attrs", {})

        for i in range(1, node_count + 1):
            label = name_template.format(node_num=i)
            node_name = f"{effective_path}/{label}" if effective_path else label

            node = Node(name=node_name)
            # Merge any extra attributes
            if "coords" in group_def:
                node.attrs["coords"] = group_def["coords"]
            node.attrs.update(node_attrs)  # Apply bulk attributes
            node.attrs.setdefault("type", "node")

            ctx.network.add_node(node)


def _expand_blueprint_adjacency(
    ctx: DSLExpansionContext,
    adj_def: Dict[str, Any],
    parent_path: str,
) -> None:
    """
    Expands adjacency definitions from within a blueprint, using parent_path
    as the local root.

    Args:
        ctx (DSLExpansionContext): The context object with blueprint info and the network.
        adj_def (Dict[str, Any]): The adjacency definition inside the blueprint,
            containing 'source', 'target', 'pattern', etc.
        parent_path (str): The path that serves as the base for the blueprint's node paths.
    """
    source_rel = adj_def["source"]
    target_rel = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_params = adj_def.get("link_params", {})
    link_count = adj_def.get("link_count", 1)

    src_path = _join_paths(parent_path, source_rel)
    tgt_path = _join_paths(parent_path, target_rel)

    _expand_adjacency_pattern(ctx, src_path, tgt_path, pattern, link_params, link_count)


def _expand_adjacency(
    ctx: DSLExpansionContext,
    adj_def: Dict[str, Any],
) -> None:
    """
    Expands a top-level adjacency definition from 'network.adjacency'.

    Args:
        ctx (DSLExpansionContext): The context containing the target network.
        adj_def (Dict[str, Any]): The adjacency definition dict, containing
            'source', 'target', and optional 'pattern', 'link_params'.
    """
    source_path_raw = adj_def["source"]
    target_path_raw = adj_def["target"]
    pattern = adj_def.get("pattern", "mesh")
    link_count = adj_def.get("link_count", 1)
    link_params = adj_def.get("link_params", {})

    # Convert to an absolute or relative path
    source_path = _join_paths("", source_path_raw)
    target_path = _join_paths("", target_path_raw)

    _expand_adjacency_pattern(
        ctx, source_path, target_path, pattern, link_params, link_count
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
      * "mesh": Connect every node from source side to every node on target side,
                skipping self-loops and deduplicating reversed pairs.
      * "one_to_one": Pair each source node with exactly one target node (wrap-around),
                      requiring that the larger set size is an integer multiple
                      of the smaller set size.

    Args:
        ctx (DSLExpansionContext): The context containing the target network.
        source_path (str): The path pattern identifying the source node group(s).
        target_path (str): The path pattern identifying the target node group(s).
        pattern (str): The type of adjacency pattern (e.g., "mesh", "one_to_one").
        link_params (Dict[str, Any]): Additional link parameters (capacity, cost, attrs).
        link_count (int): Number of parallel links to create for each adjacency.
    """
    source_node_groups = ctx.network.select_node_groups_by_path(source_path)
    target_node_groups = ctx.network.select_node_groups_by_path(target_path)

    source_nodes = [node for _, nodes in source_node_groups.items() for node in nodes]
    target_nodes = [node for _, nodes in target_node_groups.items() for node in nodes]

    # If either list is empty, no links to create
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
                f"one_to_one pattern requires sizes with a multiple factor. "
                f"Got source={s_count}, target={t_count}."
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
    and attributes from link_params. Uses deep copies of the attributes to avoid
    accidental shared mutations.

    Args:
        net (Network): The network to which the new link(s) is/are added.
        source (str): Source node name for the link.
        target (str): Target node name for the link.
        link_params (Dict[str, Any]): A dict possibly containing 'capacity', 'cost',
            and 'attrs' keys.
        link_count (int): Number of parallel links to create between source and target.
    """
    import copy

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
    if they do not already exist.

    Example:
        nodes:
          my_node:
            coords: [10, 20]
            hw_type: "X100"

    Args:
        net (Network): The network to which nodes are added.
        network_data (Dict[str, Any]): DSL data containing a "nodes" dict
            keyed by node name -> attributes.
    """
    for node_name, node_attrs in network_data.get("nodes", {}).items():
        if node_name not in net.nodes:
            new_node = Node(name=node_name, attrs=node_attrs or {})
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

    Args:
        net (Network): The network to which links are added.
        network_data (Dict[str, Any]): DSL data containing a "links" list,
            each item must have "source", "target", and optionally "link_params".
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


def _process_link_overrides(network: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes the 'link_overrides' section of the network DSL, updating
    existing links with new parameters.

    Example:
        link_overrides:
          - source: "/region1/*"
            target: "/region2/*"
            link_params:
              capacity: 200
              attrs:
                shared_risk_group: "SRG1"

    Args:
        network (Network): The Network whose links will be updated.
        network_data (Dict[str, Any]): The overall DSL data for the 'network'.
            Expected to contain 'link_overrides' as a list of dicts, each with
            'source', 'target', and 'link_params'.
    """
    link_overrides = network_data.get("link_overrides", [])
    for link_override in link_overrides:
        source = link_override["source"]
        target = link_override["target"]
        link_params = link_override["link_params"]
        any_direction = link_override.get("any_direction", True)
        _update_links(network, source, target, link_params, any_direction)


def _process_node_overrides(net: Network, network_data: Dict[str, Any]) -> None:
    """
    Processes the 'node_overrides' section of the network DSL, updating
    existing nodes with new attributes in bulk.

    Example:
        node_overrides:
          - path: "/region1/spine*"
            attrs:
              hw_type: "DellX"
              shared_risk_group: "SRG2"

    Args:
        net (Network): The Network whose nodes will be updated.
        network_data (Dict[str, Any]): The overall DSL data for the 'network'.
            Expected to contain 'node_overrides' as a list of dicts, each with
            'path' and 'attrs'.
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
    are updated.

    Args:
        net (Network): The network whose links should be updated.
        source (str): A path pattern identifying source node group(s).
        target (str): A path pattern identifying target node group(s).
        link_params (Dict[str, Any]): New parameter values for the links (capacity, cost, attrs).
        any_direction (bool): If True, also update links in the reverse direction.
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


def _update_nodes(
    net: Network,
    path: str,
    node_attrs: Dict[str, Any],
) -> None:
    """
    Updates attributes on all nodes matching a given path pattern.

    Args:
        net (Network): The network containing nodes.
        path (str): A path pattern identifying which node group(s) to modify.
        node_attrs (Dict[str, Any]): A dictionary of new attributes to set/merge.
    """
    node_groups = net.select_node_groups_by_path(path)
    for _, nodes in node_groups.items():
        for node in nodes:
            node.attrs.update(node_attrs)


def _apply_parameters(
    subgroup_name: str, subgroup_def: Dict[str, Any], params_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Applies user-provided parameter overrides to a blueprint subgroup.

    Example:
        If 'spine.node_count' = 6 is in params_overrides,
        it sets 'node_count'=6 for the 'spine' subgroup.

        If 'spine.node_attrs.hw_type' = 'Dell',
        it sets subgroup_def['node_attrs']['hw_type'] = 'Dell'.

    Args:
        subgroup_name (str): Name of the subgroup in the blueprint (e.g. 'spine').
        subgroup_def (Dict[str, Any]): The default definition of the subgroup.
        params_overrides (Dict[str, Any]): Overrides in the form of
            {'spine.node_count': 6, 'spine.node_attrs.hw_type': 'Dell'}.

    Returns:
        Dict[str, Any]: A copy of subgroup_def with parameter overrides applied,
        including nested dictionary fields if specified by dotted paths (e.g. node_attrs.foo).
    """
    import copy

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
    Recursively applies a path like ["node_attrs", "role"] to set node_def["node_attrs"]["role"] = value.
    Creates intermediate dicts as needed.
    """
    if not path_parts:
        return
    key = path_parts[0]
    if len(path_parts) == 1:
        node_def[key] = value
        return

    # Ensure that node_def[key] is a dict
    if key not in node_def or not isinstance(node_def[key], dict):
        node_def[key] = {}
    _apply_nested_path(node_def[key], path_parts[1:], value)


def _join_paths(parent_path: str, rel_path: str) -> str:
    """
    Joins two path segments according to NetGraph's DSL conventions:

    - If rel_path starts with '/', strip the leading slash and treat it as
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
