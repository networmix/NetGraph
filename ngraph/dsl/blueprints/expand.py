"""Network topology blueprints and generation."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from ngraph.dsl.blueprints import parser as _bp_parse
from ngraph.dsl.expansion import (
    ExpansionSpec,
    expand_block,
    expand_risk_group_refs,
    expand_templates,
)
from ngraph.dsl.selectors import (
    evaluate_conditions,
    flatten_link_attrs,
    normalize_selector,
    parse_match_spec,
    select_nodes,
)
from ngraph.model.network import Link, Network, Node


@dataclass
class Blueprint:
    """Represents a reusable blueprint for hierarchical sub-topologies.

    A blueprint may contain multiple node definitions (each can have count
    and template), plus link definitions describing how those nodes connect.

    Attributes:
        name: Unique identifier of this blueprint.
        nodes: A mapping of node_name -> node definition.
        links: A list of link definitions.
    """

    name: str
    nodes: Dict[str, Any]
    links: List[Dict[str, Any]]


@dataclass
class DSLExpansionContext:
    """Carries the blueprint definitions and the final Network instance
    to be populated during DSL expansion.

    Attributes:
        blueprints: Dictionary of blueprint-name -> Blueprint.
        network: The Network into which expanded nodes/links are inserted.
        pending_bp_links: Deferred blueprint link expansions.
    """

    blueprints: Dict[str, Blueprint]
    network: Network
    pending_bp_links: List[tuple[Dict[str, Any], str]] = field(default_factory=list)


def expand_network_dsl(data: Dict[str, Any]) -> Network:
    """Expands a combined blueprint + network DSL into a complete Network object.

    Overall flow:
      1) Parse "blueprints" into Blueprint objects.
      2) Build a Network from "network" metadata (e.g. name, version).
      3) Expand 'network["nodes"]' (collect blueprint links for later).
         - If a node group references a blueprint, incorporate that blueprint's
           nodes while merging parent's attrs + disabled + risk_groups.
           Blueprint links are deferred and processed after node rules.
         - Otherwise, directly create nodes (a "direct node group").
      4) Process node rules (in order if multiple rules match).
      5) Expand deferred blueprint links.
      6) Expand link definitions in 'network["links"]'.
      7) Process link rules (in order if multiple rules match).

    Field validation rules:
      - Only certain top-level fields are permitted in each structure.
      - Link properties are flat (capacity, cost, etc. at link level).
      - For node definitions: count, template, attrs, disabled, risk_groups,
        or blueprint for blueprint-based nodes.

    Args:
        data: The YAML-parsed dictionary containing optional "blueprints" + "network".

    Returns:
        The expanded Network object with all nodes and links.
    """
    # 1) Parse blueprint definitions
    blueprint_map: Dict[str, Blueprint] = {}
    if "blueprints" in data:
        if not isinstance(data["blueprints"], dict):
            raise ValueError("'blueprints' must be a dictionary.")
        for bp_name, bp_data in data["blueprints"].items():
            if not isinstance(bp_data, dict):
                raise ValueError(
                    f"Blueprint definition for '{bp_name}' must be a dict."
                )
            _bp_parse.check_no_extra_keys(
                bp_data,
                allowed={"nodes", "links"},
                context=f"blueprint '{bp_name}'",
            )
            blueprint_map[bp_name] = Blueprint(
                name=bp_name,
                nodes=bp_data.get("nodes", {}),
                links=bp_data.get("links", []),
            )

    # 2) Initialize the Network from "network" metadata
    network_data = data.get("network", {})
    if not isinstance(network_data, dict):
        raise ValueError("'network' must be a dictionary if present.")

    net = Network()
    # Pull recognized top-level fields from network_data
    for key in network_data.keys():
        if key not in (
            "name",
            "version",
            "nodes",
            "links",
            "link_rules",
            "node_rules",
        ):
            raise ValueError(f"Unrecognized top-level key in 'network': {key}")

    if "name" in network_data:
        net.attrs["name"] = network_data["name"]
    if "version" in network_data:
        net.attrs["version"] = network_data["version"]

    # Create a context
    ctx = DSLExpansionContext(blueprints=blueprint_map, network=net)

    # 3) Expand top-level node definitions
    for node_name, node_def in network_data.get("nodes", {}).items():
        if not isinstance(node_def, dict):
            raise ValueError(f"Node definition for '{node_name}' must be a dict.")
        _expand_node_group(
            ctx, parent_path="", group_name=node_name, group_def=node_def
        )

    # 4) Process node rules early so they influence link selection
    _process_node_rules(ctx.network, network_data)

    # 5) Expand deferred blueprint links
    for _link_def, _parent in ctx.pending_bp_links:
        _expand_blueprint_link(ctx, _link_def, _parent)

    # 6) Expand top-level link definitions
    for link_def in network_data.get("links", []):
        if not isinstance(link_def, dict):
            raise ValueError("Each link entry must be a dictionary.")
        _expand_link(ctx, link_def)

    # 7) Process link rules (in order)
    _process_link_rules(ctx.network, network_data)

    return net


def _expand_node_group(
    ctx: DSLExpansionContext,
    parent_path: str,
    group_name: str,
    group_def: Dict[str, Any],
    inherited_risk_groups: Optional[Set[str]] = None,
) -> None:
    """Expands a single node definition into either:
      - Another blueprint's nodes, or
      - Nested nodes (inline hierarchy), or
      - A direct node group (with count, etc.),
      - Possibly replicating itself if group_name has bracket expansions.

    If 'blueprint' is present, we expand that blueprint. If 'nodes' is present,
    we recurse for nested groups. Otherwise, we create nodes directly.

    For blueprint usage:
      Allowed keys: {"blueprint", "params", "attrs", "disabled", "risk_groups"}.
      We merge 'attrs', 'disabled', and 'risk_groups' from this parent
      into each blueprint node definition.

    For nested nodes:
      Allowed keys: {"nodes", "attrs", "disabled", "risk_groups"}.

    For direct node groups (no 'blueprint', no 'nodes'):
      Allowed keys: {"count", "template", "attrs", "disabled", "risk_groups"}.

    If group_name includes bracket expansions like "fa[1-2]", it replicates the
    same group_def for each expanded name.

    Args:
        ctx: The context containing blueprint info and the Network.
        parent_path: The parent path in the hierarchy.
        group_name: The current group's name (may have bracket expansions).
        group_def: The node definition (count, template, etc.).
        inherited_risk_groups: Risk groups inherited from a higher-level group.
    """
    if inherited_risk_groups is None:
        inherited_risk_groups = set()
    expanded_names = _bp_parse.expand_name_patterns(group_name)
    # If bracket expansions exist, replicate for each expansion
    if len(expanded_names) > 1 or expanded_names[0] != group_name:
        for expanded_name in expanded_names:
            _expand_node_group(
                ctx, parent_path, expanded_name, group_def, inherited_risk_groups
            )
        return

    # Compute the full path for this group
    if parent_path:
        effective_path = f"{parent_path}/{group_name}"
    else:
        effective_path = group_name

    if "blueprint" in group_def:
        # Blueprint usage => recognized keys
        _bp_parse.check_no_extra_keys(
            group_def,
            allowed={"blueprint", "params", "attrs", "disabled", "risk_groups"},
            context=f"node '{group_name}' using blueprint",
        )
        blueprint_name: str = group_def["blueprint"]
        bp = ctx.blueprints.get(blueprint_name)
        if not bp:
            raise ValueError(
                f"Node '{group_name}' references unknown blueprint '{blueprint_name}'."
            )

        parent_attrs = copy.deepcopy(group_def.get("attrs", {}))
        if not isinstance(parent_attrs, dict):
            raise ValueError(f"'attrs' must be a dict in node '{group_name}'.")
        parent_disabled = bool(group_def.get("disabled", False))

        # Merge parent's risk_groups
        parent_risk_groups = set(inherited_risk_groups)
        if "risk_groups" in group_def:
            rg_val = group_def["risk_groups"]
            if not isinstance(rg_val, (list, set)):
                raise ValueError(
                    f"'risk_groups' must be list or set in node '{group_name}'."
                )
            parent_risk_groups |= expand_risk_group_refs(rg_val)

        param_overrides: Dict[str, Any] = group_def.get("params", {})
        if not isinstance(param_overrides, dict):
            raise ValueError(f"'params' must be a dict in node '{group_name}'.")

        # For each node in the blueprint, apply param overrides and
        # merge parent's attrs/disabled/risk_groups
        for bp_sub_name, bp_sub_def in bp.nodes.items():
            merged_def = _apply_parameters(bp_sub_name, bp_sub_def, param_overrides)
            merged_def = dict(merged_def)  # ensure we can mutate

            # Force disabled if parent is disabled
            if parent_disabled:
                merged_def["disabled"] = True

            # Merge parent's attrs
            child_attrs = merged_def.get("attrs", {})
            if not isinstance(child_attrs, dict):
                raise ValueError(
                    f"Node '{bp_sub_name}' has non-dict 'attrs' inside blueprint '{blueprint_name}'."
                )
            merged_def["attrs"] = {**parent_attrs, **child_attrs}

            # Merge parent's risk_groups with child's
            child_rgs = expand_risk_group_refs(merged_def.get("risk_groups", []))
            merged_def["risk_groups"] = parent_risk_groups | child_rgs

            # Recursively expand
            _expand_node_group(
                ctx,
                parent_path=effective_path,
                group_name=bp_sub_name,
                group_def=merged_def,
                inherited_risk_groups=merged_def["risk_groups"],
            )

        # Defer blueprint links under this parent's path to run after node rules
        for link_def in bp.links:
            ctx.pending_bp_links.append((link_def, effective_path))

    elif "nodes" in group_def:
        # Nested nodes => recognized keys
        _bp_parse.check_no_extra_keys(
            group_def,
            allowed={"nodes", "attrs", "disabled", "risk_groups"},
            context=f"nested node '{group_name}'",
        )

        parent_attrs = copy.deepcopy(group_def.get("attrs", {}))
        parent_disabled = bool(group_def.get("disabled", False))

        # Merge parent's risk_groups
        parent_risk_groups = set(inherited_risk_groups)
        if "risk_groups" in group_def:
            rg_val = group_def["risk_groups"]
            if not isinstance(rg_val, (list, set)):
                raise ValueError(
                    f"'risk_groups' must be list or set in node '{group_name}'."
                )
            parent_risk_groups |= expand_risk_group_refs(rg_val)

        # Recursively process nested nodes
        nested_nodes = group_def["nodes"]
        if not isinstance(nested_nodes, dict):
            raise ValueError(f"'nodes' must be a dict in '{group_name}'.")

        for nested_name, nested_def in nested_nodes.items():
            if not isinstance(nested_def, dict):
                raise ValueError(
                    f"Nested node definition for '{nested_name}' must be a dict."
                )
            merged_def = dict(nested_def)

            # Force disabled if parent is disabled
            if parent_disabled:
                merged_def["disabled"] = True

            # Merge parent's attrs
            child_attrs = merged_def.get("attrs", {})
            if not isinstance(child_attrs, dict):
                child_attrs = {}
            merged_def["attrs"] = {**parent_attrs, **child_attrs}

            # Merge parent's risk_groups with child's
            child_rgs = expand_risk_group_refs(merged_def.get("risk_groups", []))
            merged_def["risk_groups"] = parent_risk_groups | child_rgs

            _expand_node_group(
                ctx,
                parent_path=effective_path,
                group_name=nested_name,
                group_def=merged_def,
                inherited_risk_groups=merged_def["risk_groups"],
            )

    else:
        # Direct node group => recognized keys
        _bp_parse.check_no_extra_keys(
            group_def,
            allowed={"count", "template", "attrs", "disabled", "risk_groups"},
            context=f"node '{group_name}'",
        )
        combined_attrs = copy.deepcopy(group_def.get("attrs", {}))
        if not isinstance(combined_attrs, dict):
            raise ValueError(f"attrs must be a dict in node '{group_name}'.")
        group_disabled = bool(group_def.get("disabled", False))

        # Merge parent's risk groups
        parent_risk_groups = set(inherited_risk_groups)
        child_rgs = expand_risk_group_refs(group_def.get("risk_groups", []))
        final_risk_groups = parent_risk_groups | child_rgs

        # Check if this is a simple single node (no count, no template)
        has_count = "count" in group_def
        has_template = "template" in group_def

        if not has_count and not has_template:
            # Simple single node - use effective_path as the node name
            node = Node(
                name=effective_path,
                disabled=group_disabled,
                attrs=copy.deepcopy(combined_attrs),
            )
            node.attrs.setdefault("type", "node")
            node.risk_groups = final_risk_groups.copy()
            ctx.network.add_node(node)
        else:
            # Node group with count/template - create numbered nodes
            count = group_def.get("count", 1)
            template = group_def.get("template", f"{group_name}-{{n}}")
            if not isinstance(count, int) or count < 1:
                raise ValueError(f"node '{group_name}' has invalid count: {count}")

            for i in range(1, count + 1):
                label = template.format(n=i)
                node_name = f"{effective_path}/{label}" if effective_path else label

                node = Node(
                    name=node_name,
                    disabled=group_disabled,
                    attrs=copy.deepcopy(combined_attrs),
                )
                node.attrs.setdefault("type", "node")
                node.risk_groups = final_risk_groups.copy()
                ctx.network.add_node(node)


def _normalize_link_selector(sel: Any, base: str) -> Dict[str, Any]:
    """Normalize a source/target selector for link expansion.

    Args:
        sel: String path or dict with 'path', 'group_by', and/or 'match'.
        base: Parent path to prepend.

    Returns:
        Normalized selector dict.
    """
    if isinstance(sel, str):
        return {"path": _bp_parse.join_paths(base, sel)}
    if isinstance(sel, dict):
        path = sel.get("path")
        group_by = sel.get("group_by")
        match = sel.get("match")

        # Validate: must have path, group_by, or match
        if path is None and group_by is None and match is None:
            raise ValueError(
                "Selector object must contain 'path', 'group_by', or 'match'."
            )

        out = dict(sel)
        if path is not None:
            if not isinstance(path, str):
                raise ValueError("Selector 'path' must be a string.")
            out["path"] = _bp_parse.join_paths(base, path)
        return out
    raise ValueError(
        "Link 'source'/'target' must be string or object with "
        "'path', 'group_by', or 'match'."
    )


def _expand_blueprint_link(
    ctx: DSLExpansionContext,
    link_def: Dict[str, Any],
    parent_path: str,
) -> None:
    """Expands link definitions from within a blueprint, using parent_path
    as the local root. Handles optional expand: block for repeated links.

    Args:
        ctx: The context object with blueprint info and the network.
        link_def: The link definition inside the blueprint.
        parent_path: The path serving as the base for the blueprint's node paths.
    """
    _bp_parse.check_link_keys(link_def, context="blueprint link")

    # Check for expand block
    expand_spec = ExpansionSpec.from_dict(link_def)
    if expand_spec and not expand_spec.is_empty():
        _expand_link_with_variables(ctx, link_def, parent_path)
        return

    source_rel = link_def["source"]
    target_rel = link_def["target"]
    pattern = link_def.get("pattern", "mesh")
    count = link_def.get("count", 1)

    src_sel = _normalize_link_selector(source_rel, parent_path)
    tgt_sel = _normalize_link_selector(target_rel, parent_path)

    _expand_link_pattern(ctx, src_sel, tgt_sel, pattern, link_def, count)


def _expand_link(ctx: DSLExpansionContext, link_def: Dict[str, Any]) -> None:
    """Expands a top-level link definition from 'network.links'.
    If expand: block is provided, we expand the source/target as templates.

    Args:
        ctx: The context containing the target network.
        link_def: The link definition dict.
    """
    _bp_parse.check_link_keys(link_def, context="top-level link")

    # Check for expand block
    expand_spec = ExpansionSpec.from_dict(link_def)
    if expand_spec and not expand_spec.is_empty():
        _expand_link_with_variables(ctx, link_def, parent_path="")
        return

    source_raw = link_def["source"]
    target_raw = link_def["target"]
    pattern = link_def.get("pattern", "mesh")
    count = link_def.get("count", 1)

    src_sel = _normalize_link_selector(source_raw, "")
    tgt_sel = _normalize_link_selector(target_raw, "")

    _expand_link_pattern(ctx, src_sel, tgt_sel, pattern, link_def, count)


def _expand_link_with_variables(
    ctx: DSLExpansionContext, link_def: Dict[str, Any], parent_path: str
) -> None:
    """Handles link expansions when 'expand' block is provided.

    Substitutes variables into 'source' and 'target' templates using $var or ${var}
    syntax to produce multiple link expansions. Supports both string paths
    and dict selectors (with path/group_by).

    Args:
        ctx: The DSL expansion context.
        link_def: The link definition including expand block, source, target, etc.
        parent_path: Prepended to source/target paths.
    """
    source_template = link_def["source"]
    target_template = link_def["target"]
    pattern = link_def.get("pattern", "mesh")
    count = link_def.get("count", 1)

    # Get expansion spec from expand: block
    expand_spec = ExpansionSpec.from_dict(link_def)
    if expand_spec is None:
        expand_spec = ExpansionSpec(vars={}, mode="cartesian")

    # Collect all string fields that need variable substitution
    templates = _extract_selector_templates(source_template, "source")
    templates.update(_extract_selector_templates(target_template, "target"))

    if not templates:
        # No variables to expand - just process once
        src_sel = _normalize_link_selector(source_template, parent_path)
        tgt_sel = _normalize_link_selector(target_template, parent_path)
        _expand_link_pattern(ctx, src_sel, tgt_sel, pattern, link_def, count)
        return

    # Expand templates and rebuild selectors
    for substituted in expand_templates(templates, expand_spec):
        src_sel = _rebuild_selector(source_template, substituted, "source", parent_path)
        tgt_sel = _rebuild_selector(target_template, substituted, "target", parent_path)
        _expand_link_pattern(ctx, src_sel, tgt_sel, pattern, link_def, count)


def _extract_selector_templates(selector: Any, prefix: str) -> Dict[str, str]:
    """Extract string fields from a selector that may contain variables."""
    templates: Dict[str, str] = {}
    if isinstance(selector, str):
        templates[prefix] = selector
    elif isinstance(selector, dict):
        if "path" in selector and isinstance(selector["path"], str):
            templates[f"{prefix}.path"] = selector["path"]
        if "group_by" in selector and isinstance(selector["group_by"], str):
            templates[f"{prefix}.group_by"] = selector["group_by"]
    return templates


def _rebuild_selector(
    original: Any, substituted: Dict[str, str], prefix: str, parent_path: str
) -> Dict[str, Any]:
    """Rebuild a selector with substituted values."""
    if isinstance(original, str):
        path = substituted.get(prefix, original)
        return {"path": _bp_parse.join_paths(parent_path, path)}

    if isinstance(original, dict):
        result = dict(original)
        if f"{prefix}.path" in substituted:
            result["path"] = _bp_parse.join_paths(
                parent_path, substituted[f"{prefix}.path"]
            )
        elif "path" in result:
            result["path"] = _bp_parse.join_paths(parent_path, result["path"])
        if f"{prefix}.group_by" in substituted:
            result["group_by"] = substituted[f"{prefix}.group_by"]
        return result

    raise ValueError(f"Selector must be string or dict, got {type(original)}")


def _expand_link_pattern(
    ctx: DSLExpansionContext,
    source_selector: Any,
    target_selector: Any,
    pattern: str,
    link_def: Dict[str, Any],
    count: int = 1,
) -> None:
    """Generates Link objects for the chosen link pattern among matched nodes.

    Supported Patterns:
      * "mesh": Connect every source node to every target node
                (no self-loops, deduplicate reversed pairs).
      * "one_to_one": Pair each source node with exactly one target node
                      using wrap-around. The larger set size must be
                      a multiple of the smaller set size.

    Link properties are now flat in link_def (capacity, cost, disabled,
    risk_groups, attrs).

    Args:
        ctx: The context with the target network.
        source_selector: Path string or selector object {path, group_by, match}.
        target_selector: Path string or selector object {path, group_by, match}.
        pattern: "mesh" or "one_to_one".
        link_def: Link definition with flat properties.
        count: Number of parallel links to create for each pair.
    """
    source_nodes = _select_link_nodes(ctx.network, source_selector)
    target_nodes = _select_link_nodes(ctx.network, target_selector)

    if not source_nodes or not target_nodes:
        return

    dedup_pairs: Set[tuple[str, str]] = set()

    if pattern == "mesh":
        for sn in source_nodes:
            for tn in target_nodes:
                if sn.name == tn.name:
                    continue
                pair = (min(sn.name, tn.name), max(sn.name, tn.name))
                if pair not in dedup_pairs:
                    dedup_pairs.add(pair)
                    _create_link(ctx.network, sn.name, tn.name, link_def, count)

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
                src_name = source_nodes[i].name
                tgt_name = target_nodes[i % t_count].name
            else:
                src_name = source_nodes[i % s_count].name
                tgt_name = target_nodes[i].name

            if src_name == tgt_name:
                continue

            pair = (min(src_name, tgt_name), max(src_name, tgt_name))
            if pair not in dedup_pairs:
                dedup_pairs.add(pair)
                _create_link(ctx.network, src_name, tgt_name, link_def, count)
    else:
        raise ValueError(f"Unknown link pattern: {pattern}")


def _select_link_nodes(network: Network, selector: Any) -> List[Node]:
    """Select nodes for link creation based on selector.

    Uses the unified selector system. For links, active_only defaults
    to False (links to disabled nodes are created).

    Args:
        network: The network to select from.
        selector: String path or dict with path/group_by/match.

    Returns:
        List of matching nodes (flattened from all groups).
    """
    normalized = normalize_selector(selector, context="adjacency")
    groups = select_nodes(network, normalized, default_active_only=False)
    return [node for nodes in groups.values() for node in nodes]


def _create_link(
    net: Network,
    source: str,
    target: str,
    link_def: Dict[str, Any],
    count: int = 1,
) -> None:
    """Creates and adds one or more Links to the network.

    Link properties are now flat in link_def (capacity, cost, disabled,
    risk_groups, attrs).

    Args:
        net: The network to which the new link(s) will be added.
        source: Source node name for the link.
        target: Target node name for the link.
        link_def: Dict with flat link properties.
        count: Number of parallel links to create between source and target.
    """
    for _ in range(count):
        capacity = link_def.get("capacity", 1.0)
        cost = link_def.get("cost", 1.0)
        attrs = copy.deepcopy(link_def.get("attrs", {}))
        disabled_flag = bool(link_def.get("disabled", False))
        link_rgs = expand_risk_group_refs(link_def.get("risk_groups", []))

        link = Link(
            source=source,
            target=target,
            capacity=capacity,
            cost=cost,
            attrs=attrs,
            disabled=disabled_flag,
        )
        link.risk_groups = link_rgs
        net.add_link(link)


def _process_node_rules(net: Network, network_data: Dict[str, Any]) -> None:
    """Processes the 'node_rules' section of the network DSL, updating
    existing nodes with new attributes in bulk. Rules are applied in order
    if multiple items match the same node.

    Each rule must have {"path"} plus optionally {"attrs", "disabled", "risk_groups"}.

    - If "disabled" is present, we set node.disabled.
    - If "risk_groups" is present, we *replace* the node's risk_groups.
    - Everything else merges into node.attrs.

    Args:
        net: The Network whose nodes will be updated.
        network_data: DSL data possibly containing 'node_rules'.
    """
    node_rules = network_data.get("node_rules", [])
    if not isinstance(node_rules, list):
        return

    for rule in node_rules:
        if not isinstance(rule, dict):
            raise ValueError("Each node_rule must be a dict.")
        _bp_parse.check_no_extra_keys(
            rule,
            allowed={"path", "attrs", "disabled", "risk_groups", "match", "expand"},
            context="node rule",
        )

        # Handle expand block
        expand_spec = ExpansionSpec.from_dict(rule)
        if expand_spec and not expand_spec.is_empty():
            for expanded_rule in expand_block(rule, expand_spec):
                _apply_node_rule(net, expanded_rule)
        else:
            _apply_node_rule(net, rule)


def _apply_node_rule(net: Network, rule: Dict[str, Any]) -> None:
    """Apply a single node rule to matching nodes."""
    path = rule.get("path", ".*")
    match_spec = rule.get("match")
    top_level_disabled = rule.get("disabled", None)
    rule_risk_groups = rule.get("risk_groups", None)

    if "attrs" in rule and not isinstance(rule["attrs"], dict):
        raise ValueError("attrs must be a dict in node rule.")

    attrs_to_set = copy.deepcopy(rule.get("attrs", {}))
    _update_nodes(
        net, path, match_spec, attrs_to_set, top_level_disabled, rule_risk_groups
    )


def _process_link_rules(net: Network, network_data: Dict[str, Any]) -> None:
    """Processes the 'link_rules' section of the network DSL, updating
    existing links with new parameters. Rules are applied in order if
    multiple items match the same link.

    Each rule must contain {"source", "target"} plus optionally
    {"bidirectional", "capacity", "cost", "disabled", "risk_groups", "attrs", "expand"}.

    If risk_groups is given, it *replaces* the link's existing risk_groups.

    Args:
        net: The Network whose links will be updated.
        network_data: DSL data possibly containing 'link_rules'.
    """
    link_rules = network_data.get("link_rules", [])
    if not isinstance(link_rules, list):
        return

    for link_rule in link_rules:
        if not isinstance(link_rule, dict):
            raise ValueError("Each link_rule must be a dict.")
        _bp_parse.check_no_extra_keys(
            link_rule,
            allowed={
                "source",
                "target",
                "bidirectional",
                "capacity",
                "cost",
                "disabled",
                "risk_groups",
                "attrs",
                "expand",
                "link_match",
            },
            context="link rule",
        )

        # Handle expand block
        expand_spec = ExpansionSpec.from_dict(link_rule)
        if expand_spec and not expand_spec.is_empty():
            for expanded_rule in expand_block(link_rule, expand_spec):
                _apply_link_rule(net, expanded_rule)
        else:
            _apply_link_rule(net, link_rule)


def _apply_link_rule(net: Network, rule: Dict[str, Any]) -> None:
    """Apply a single link rule to matching links."""
    source = rule["source"]
    target = rule["target"]
    bidirectional = rule.get("bidirectional", True)

    _update_links(net, source, target, rule, bidirectional)


def _update_links(
    net: Network,
    source: Any,
    target: Any,
    rule: Dict[str, Any],
    bidirectional: bool = True,
) -> None:
    """Updates all Link objects between nodes matching source and target selectors
    with new parameters (capacity, cost, disabled, risk_groups, attrs).

    If bidirectional=True, both (source->target) and (target->source) links
    are updated if present.

    If risk_groups is given, it *replaces* the link's existing risk_groups.

    Args:
        net: The network whose links should be updated.
        source: Selector (string path or dict with path/match) for source nodes.
        target: Selector (string path or dict with path/match) for target nodes.
        rule: Rule dict with flat link properties.
        bidirectional: If True, also update reversed direction links.
    """
    # Use unified selector system for full selector support
    src_sel = normalize_selector(source, context="override")
    tgt_sel = normalize_selector(target, context="override")

    source_node_groups = select_nodes(net, src_sel, default_active_only=False)
    target_node_groups = select_nodes(net, tgt_sel, default_active_only=False)

    source_nodes = {
        node.name for _, nodes in source_node_groups.items() for node in nodes
    }
    target_nodes = {
        node.name for _, nodes in target_node_groups.items() for node in nodes
    }

    new_disabled_val = rule.get("disabled", None)
    new_capacity = rule.get("capacity", None)
    new_cost = rule.get("cost", None)
    new_risk_groups = rule.get("risk_groups", None)
    new_attrs = rule.get("attrs", {})

    # Parse link_match for filtering by link attributes
    link_match_raw = rule.get("link_match")
    link_match = parse_match_spec(link_match_raw) if link_match_raw else None

    for link_id, link in net.links.items():
        forward_match = link.source in source_nodes and link.target in target_nodes
        reverse_match = (
            bidirectional
            and link.source in target_nodes
            and link.target in source_nodes
        )
        if not (forward_match or reverse_match):
            continue

        # Apply link_match filter if specified
        if link_match is not None:
            link_attrs = flatten_link_attrs(link, link_id)
            if not evaluate_conditions(
                link_attrs, link_match.conditions, link_match.logic
            ):
                continue

        # Apply updates
        if new_capacity is not None:
            link.capacity = new_capacity
        if new_cost is not None:
            link.cost = new_cost
        if new_disabled_val is not None:
            link.disabled = bool(new_disabled_val)
        if new_risk_groups is not None:
            link.risk_groups = expand_risk_group_refs(new_risk_groups)
        if new_attrs:
            link.attrs.update(new_attrs)


def _update_nodes(
    net: Network,
    path: str,
    match_spec: Optional[Dict[str, Any]],
    attrs: Dict[str, Any],
    disabled_val: Any = None,
    risk_groups_val: Any = None,
) -> None:
    """Updates attributes on all nodes matching a path pattern and optional match conditions.

    - If 'disabled_val' is not None, sets node.disabled to that boolean value.
    - If 'risk_groups_val' is not None, *replaces* the node's risk_groups with that new set.
    - Everything else in 'attrs' is merged into node.attrs.

    Args:
        net: The network containing the nodes.
        path: A path pattern identifying which node group(s) to modify.
        match_spec: Optional match conditions dict (with 'conditions' and 'logic').
        attrs: A dictionary of new attributes to set/merge.
        disabled_val: Boolean or None for disabling or enabling nodes.
        risk_groups_val: List or set or None for replacing node.risk_groups.
    """
    # Build selector dict with path and optional match
    selector_dict: Dict[str, Any] = {"path": path}
    if match_spec:
        selector_dict["match"] = match_spec

    # Use unified selector system
    normalized = normalize_selector(selector_dict, context="override")
    node_groups = select_nodes(net, normalized, default_active_only=False)

    for _, nodes in node_groups.items():
        for node in nodes:
            if disabled_val is not None:
                node.disabled = bool(disabled_val)
            if risk_groups_val is not None:
                if not isinstance(risk_groups_val, (list, set)):
                    raise ValueError(
                        f"risk_groups override must be list or set, got {type(risk_groups_val)}."
                    )
                node.risk_groups = expand_risk_group_refs(risk_groups_val)
            node.attrs.update(attrs)


def _apply_parameters(
    subgroup_name: str, subgroup_def: Dict[str, Any], params_overrides: Dict[str, Any]
) -> Dict[str, Any]:
    """Applies user-provided parameter overrides to a blueprint subgroup.

    Example:
        If 'spine.node_count' = 6 is in params_overrides,
        it sets 'node_count' = 6 for the 'spine' subgroup.
        If 'spine.attrs.hw_type' = 'Dell', it sets subgroup_def['attrs']['hw_type'] = 'Dell'.

    Args:
        subgroup_name (str): Name of the subgroup in the blueprint.
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
            subpath = parts[1:]
            _apply_nested_path(out, subpath, val)

    return out


def _apply_nested_path(
    node_def: Dict[str, Any], path_parts: List[str], value: Any
) -> None:
    """Recursively applies a path like ["attrs", "role"] to set node_def["attrs"]["role"] = value.
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
