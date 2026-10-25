"""Blueprint and network DSL expansion.

Turns the `blueprints:` and `network:` sections into concrete Node and Link
objects: resolves blueprint instantiation and parameter overrides, expands
bracket patterns and `expand:` variable blocks, applies node and link rules,
and materializes `mesh`/`one_to_one` link patterns.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from functools import partial
from typing import Any, Dict, Iterable, List, Optional, Set

from ngraph.dsl.blueprints import parser as _bp_parse
from ngraph.dsl.expansion import (
    ExpansionSpec,
    expand_block,
    expand_name_patterns,
    expand_risk_group_refs,
)
from ngraph.dsl.expansion.variables import _expand_declaration
from ngraph.model.network import Link, Network, Node
from ngraph.model.selectors import (
    evaluate_conditions,
    flatten_link_attrs,
    normalize_selector,
    parse_match_spec,
    select_nodes,
)
from ngraph.utils.values import _input_error, _shown, flag, frozen_attrs, integer, text
from ngraph.utils.yaml_utils import _declaration_error, check_no_extra_keys, declared


@dataclass
class Blueprint:
    """Reusable blueprint for hierarchical sub-topologies.

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
    """Blueprint definitions and the Network populated during DSL expansion.

    Attributes:
        blueprints: Dictionary of blueprint-name -> Blueprint.
        network: The Network into which expanded nodes/links are inserted.
        pending_bp_links: (link definition, parent path) pairs for blueprint
            links, expanded after node rules run.
    """

    blueprints: Dict[str, Blueprint]
    network: Network
    pending_bp_links: List[tuple[Dict[str, Any], str, str]] = field(
        default_factory=list
    )


def expand_network_dsl(data: Dict[str, Any]) -> Network:
    """Expand a combined blueprint + network DSL into a Network.

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
      - Each structure rejects unrecognized keys.
      - Link properties are flat (capacity, cost, etc. at link level).
      - Node definitions accept count, template, attrs, disabled, risk_groups,
        nodes (nested groups), or blueprint and params (blueprint instances).

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
            check_no_extra_keys(
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

    net = declared(
        "network",
        lambda: Network(
            attrs={
                key: network_data[key]
                for key in ("name", "version")
                if key in network_data
            }
        ),
        "network.attrs",
    )
    # Reject unrecognized top-level fields before anything is expanded
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

    ctx = DSLExpansionContext(blueprints=blueprint_map, network=net)

    # 3) Expand top-level node definitions
    for node_name, node_def in network_data.get("nodes", {}).items():
        if not isinstance(node_def, dict):
            raise ValueError(f"Node definition for '{node_name}' must be a dict.")
        declared(
            f"network.nodes.{node_name}",
            lambda node_name=node_name, node_def=node_def: _expand_node_group(
                ctx, parent_path="", group_name=node_name, group_def=node_def
            ),
            f"node '{node_name}'",
        )

    # 4) Process node rules early so they influence link selection
    _process_node_rules(ctx.network, network_data)

    # 5) Expand deferred blueprint links
    for _link_def, _parent, _location in ctx.pending_bp_links:
        _expand_link(ctx, _link_def, _parent, context=_location)

    # 6) Expand top-level link definitions
    for link_index, link_def in enumerate(network_data.get("links", [])):
        if not isinstance(link_def, dict):
            raise ValueError("Each link entry must be a dictionary.")
        _expand_link(ctx, link_def, context=f"network.links[{link_index}]")

    # 7) Process link rules (in order)
    _process_link_rules(ctx.network, network_data)

    return net


def _node_mapping(value, label):
    if not isinstance(value, dict):
        raise _input_error(label, f"expected a mapping, got {_shown(value)}")
    return value


def _node_attrs(value, label):
    return frozen_attrs(_node_mapping(value, label), label)


def _node_risk_groups(value, label):
    if not isinstance(value, (list, set, tuple)):
        raise _input_error(
            label, f"expected a list/set/tuple of names, got {_shown(value)}"
        )
    names = [text(name, label) for name in value]
    try:
        return expand_risk_group_refs(names)
    except ValueError as exc:
        raise _input_error(label, f"{exc}; got {_shown(value)}") from exc


_NODE_FIELD_CHECKS = {
    "disabled": flag,
    "attrs": _node_attrs,
    "risk_groups": _node_risk_groups,
    "count": partial(integer, minimum=1),
    "template": text,
    "nodes": _node_mapping,
    "blueprint": text,
    "params": _node_mapping,
}


def _check_node_definition(definition, location, sources):
    """Check each supplied field before inheritance, using its own source."""
    if not isinstance(definition, dict):
        raise _declaration_error(
            location, f"{location}: expected a mapping, got {_shown(definition)}"
        )
    allowed = {"disabled", "attrs", "risk_groups"}
    allowed |= (
        {"blueprint", "params"}
        if "blueprint" in definition
        else {"nodes"}
        if "nodes" in definition
        else {"count", "template"}
    )
    checked = {}
    for name, value in definition.items():
        if name not in allowed:
            path = _source_path(sources, (str(name),), location)
            raise _declaration_error(
                path, f"{path}: unrecognized node field, got {_shown(value)}"
            )
        try:
            checked[name] = _NODE_FIELD_CHECKS[name](value, name)
        except (ValueError, TypeError) as exc:
            parts = (name, *getattr(exc, "_input_path", ()))
            path = _source_path(sources, parts, location)
            detail = getattr(exc, "_input_detail", None)
            if detail is None:
                detail = f"{exc}; got {_shown(value)}"
            raise _declaration_error(path, f"{path}: {detail}") from exc
    return checked


def _parent_merge_context(group_def, location, sources, inherited_risk_groups):
    """Check a group and extract its inherited fields without changing its input."""
    checked = _check_node_definition(group_def, location, sources)
    attrs = checked.get("attrs", {})
    disabled = checked.get("disabled", False)
    groups = set(inherited_risk_groups) | checked.get("risk_groups", set())
    return checked, attrs, disabled, groups


def _merge_parent_into_child(
    merged_def, location, sources, parent_attrs, parent_disabled, parent_risk_groups
):
    """Check child fields at their sources before any parent can mask them."""
    checked = _check_node_definition(merged_def, location, sources)
    checked["disabled"] = parent_disabled or checked.get("disabled", False)
    checked["attrs"] = {**parent_attrs, **checked.get("attrs", {})}
    checked["risk_groups"] = parent_risk_groups | checked.get("risk_groups", set())
    merged_def.clear()
    merged_def.update(checked)


def _expand_node_group(
    ctx: DSLExpansionContext,
    parent_path: str,
    group_name: str,
    group_def: Dict[str, Any],
    inherited_risk_groups: Optional[Set[str]] = None,
    location: str | None = None,
    sources: dict[tuple[str, ...], str] | None = None,
) -> None:
    """Expand one node group definition into nodes.

    A 'blueprint' key instantiates that blueprint, a 'nodes' key recurses into
    nested groups, and otherwise nodes are created directly. A group_name with
    bracket expressions like "fa[1-2]" replicates group_def once per expanded
    name.

    For blueprint usage:
      Allowed keys: {"blueprint", "params", "attrs", "disabled", "risk_groups"}.
      The parent's 'attrs', 'disabled', and 'risk_groups' are merged into
      each blueprint node definition.

    For nested nodes:
      Allowed keys: {"nodes", "attrs", "disabled", "risk_groups"}.
      The parent's 'attrs', 'disabled', and 'risk_groups' are merged into
      each nested definition.

    For direct node groups (no 'blueprint', no 'nodes'):
      Allowed keys: {"count", "template", "attrs", "disabled", "risk_groups"}.

    Args:
        ctx: The context containing blueprint info and the Network.
        parent_path: Path of the enclosing group ("" at top level).
        group_name: The current group's name (may have bracket expressions).
        group_def: The node definition (count, template, etc.).
        inherited_risk_groups: Risk groups inherited from a higher-level group.
        location: Source declaration, independent of expanded node names.
        sources: Source paths of fields replaced by parameters.
    """
    location = location or f"network.nodes.{group_name}"
    sources = {} if sources is None else sources
    if inherited_risk_groups is None:
        inherited_risk_groups = set()
    expanded_names = expand_name_patterns(group_name)
    if len(expanded_names) > 1 or expanded_names[0] != group_name:
        for expanded_name in expanded_names:
            _expand_node_group(
                ctx,
                parent_path,
                expanded_name,
                group_def,
                inherited_risk_groups,
                location,
                sources,
            )
        return

    if parent_path:
        effective_path = f"{parent_path}/{group_name}"
    else:
        effective_path = group_name

    group_def, parent_attrs, parent_disabled, parent_risk_groups = (
        _parent_merge_context(group_def, location, sources, inherited_risk_groups)
    )

    if "blueprint" in group_def:
        blueprint_name: str = group_def["blueprint"]
        bp = ctx.blueprints.get(blueprint_name)
        if not bp:
            raise ValueError(
                f"{_source_path(sources, ('blueprint',), location)}: unknown blueprint {_shown(blueprint_name)}"
            )

        param_overrides: Dict[str, Any] = group_def.get("params", {})
        if not isinstance(param_overrides, dict):
            raise ValueError(f"'params' must be a dict in node '{group_name}'.")

        # Validate override keys against the literal (unexpanded) blueprint
        # subgroup names so typos and unsupported deep 'params.*' dotted
        # paths fail loudly instead of silently expanding with defaults.
        # Keys are matched by longest '<group>.' prefix (not first dotted
        # segment) so subgroup names containing dots remain addressable.
        # The resolved key -> group mapping is reused by _apply_parameters.
        override_to_group: Dict[str, str] = {}
        for override_key in param_overrides:
            if "." not in override_key or override_key in bp.nodes:
                raise ValueError(
                    f"params override '{override_key}' in node '{group_name}' "
                    "must be of the form '<group>.<field>'. To override a "
                    "nested blueprint's params, use a dict value, e.g. "
                    "'<group>.params': {'<subgroup>.<field>': value}."
                )
            matched_group = _longest_subgroup_prefix(override_key, bp.nodes)
            if matched_group is None:
                available = ", ".join(sorted(bp.nodes)) or "<none>"
                raise ValueError(
                    f"params override '{override_key}' in node '{group_name}' "
                    f"matches no node group in blueprint '{blueprint_name}' "
                    f"(available: {available})."
                )
            override_to_group[override_key] = matched_group

        for bp_sub_name, bp_sub_def in bp.nodes.items():
            # _apply_parameters returns a deep copy, safe to mutate
            merged_def, merged_sources = _apply_parameters(
                bp_sub_name,
                bp_sub_def,
                param_overrides,
                override_to_group,
                sources,
                location,
            )
            _merge_parent_into_child(
                merged_def,
                f"blueprints.{blueprint_name}.nodes.{bp_sub_name}",
                merged_sources,
                parent_attrs,
                parent_disabled,
                parent_risk_groups,
            )

            _expand_node_group(
                ctx,
                parent_path=effective_path,
                group_name=bp_sub_name,
                group_def=merged_def,
                inherited_risk_groups=merged_def["risk_groups"],
                location=f"blueprints.{blueprint_name}.nodes.{bp_sub_name}",
                sources=merged_sources,
            )

        # Defer blueprint links under this parent's path to run after node rules
        for index, link_def in enumerate(bp.links):
            ctx.pending_bp_links.append(
                (
                    link_def,
                    effective_path,
                    f"blueprints.{blueprint_name}.links[{index}] (instance {effective_path})",
                )
            )

    elif "nodes" in group_def:
        nested_nodes = group_def["nodes"]
        if not isinstance(nested_nodes, dict):
            raise ValueError(f"'nodes' must be a dict in '{group_name}'.")

        for nested_name, nested_def in nested_nodes.items():
            child_location = _source_path(sources, ("nodes", nested_name), location)
            child_sources = _child_sources(sources, ("nodes", nested_name))
            if not isinstance(nested_def, dict):
                raise _declaration_error(
                    child_location,
                    f"{child_location}: expected a mapping, got {_shown(nested_def)}",
                )
            merged_def = dict(nested_def)
            _merge_parent_into_child(
                merged_def,
                child_location,
                child_sources,
                parent_attrs,
                parent_disabled,
                parent_risk_groups,
            )

            _expand_node_group(
                ctx,
                parent_path=effective_path,
                group_name=nested_name,
                group_def=merged_def,
                inherited_risk_groups=merged_def["risk_groups"],
                location=child_location,
                sources=child_sources,
            )

    else:
        combined_attrs, group_disabled, final_risk_groups = (
            parent_attrs,
            parent_disabled,
            parent_risk_groups,
        )

        has_count = "count" in group_def
        has_template = "template" in group_def

        if not has_count and not has_template:
            # Without count or template, the group path is the node name.
            node = Node(
                name=effective_path,
                disabled=group_disabled,
                risk_groups=final_risk_groups,
                attrs=combined_attrs,
            )
            ctx.network.add_node(node)
        else:
            count = group_def.get("count", 1)
            template = group_def.get("template", f"{group_name}-{{n}}")

            for i in range(1, count + 1):
                label = _format_node_template(
                    template, i, _source_path(sources, ("template",), location)
                )
                node_name = f"{effective_path}/{label}" if effective_path else label

                node = Node(
                    name=node_name,
                    disabled=group_disabled,
                    risk_groups=final_risk_groups,
                    attrs=combined_attrs,
                )
                ctx.network.add_node(node)


def _format_node_template(template, number, location):
    """All str.format failures belong to the template's actual declaration."""
    try:
        return template.format(n=number)
    except Exception as exc:
        raise _declaration_error(
            location, f"{location}: invalid template {template!r}: {exc}"
        ) from exc


def _join_parent(base: str, rel: str) -> str:
    """Join a literal parent path with a user-supplied relative regex.

    The parent path is a literal node-name prefix (e.g. a blueprint
    instantiation path), not a regex, so its metacharacters (e.g. '.' in
    group names like 'dc.1') must be escaped before the joined path is
    compiled as a regex. re.escape("") == "" so top-level links (base="")
    are unaffected, and re.escape leaves "/" alone, so multi-level parents
    still join on "/".

    Args:
        base: Literal parent path prefix.
        rel: User-supplied relative path regex.

    Returns:
        Combined path with the parent prefix regex-escaped.
    """
    return _bp_parse.join_paths(re.escape(base), rel)


def _normalize_link_selector(sel: Any, base: str) -> Dict[str, Any]:
    """Normalize a source/target selector for link expansion.

    Args:
        sel: String path or dict with 'path', 'group_by', and/or 'match'.
        base: Parent path to prepend.

    Returns:
        Selector dict with the regex-escaped parent prefix joined onto 'path'.
    """
    normalize_selector(sel, "link")
    if isinstance(sel, str):
        return {"path": _join_parent(base, sel)}
    if isinstance(sel, dict):
        # Selector.__post_init__ validates that at least one of path,
        # group_by, or match is present when the selector is parsed.
        path = sel.get("path")
        out = dict(sel)
        if path is not None:
            if not isinstance(path, str):
                raise ValueError("Selector 'path' must be a string.")
            out["path"] = _join_parent(base, path)
        return out
    raise ValueError(
        "Link 'source'/'target' must be string or object with "
        "'path', 'group_by', or 'match'."
    )


def _expand_link(
    ctx: DSLExpansionContext,
    link_def: Dict[str, Any],
    parent_path: str = "",
    context: str = "top-level link",
) -> None:
    """Expand a link definition into Link objects.

    Used for both top-level 'network.links' entries (parent_path="") and
    deferred blueprint links (parent_path is the blueprint instantiation
    path). If an expand: block is provided, the definition is replicated
    per variable combination.

    Args:
        ctx: The context containing the target network.
        link_def: The link definition dict.
        parent_path: Prepended to source/target paths ("" for top-level
            links, the blueprint base path for blueprint links).
        context: Short description used in error messages.
    """
    location = f"{context} ({link_def.get('source')}->{link_def.get('target')})"
    declared(
        location, lambda: _expand_declared_link(ctx, link_def, parent_path, location)
    )


def _expand_declared_link(ctx, link_def, parent_path, location):
    _bp_parse.check_link_keys(link_def, context=location)

    expand_spec = ExpansionSpec.from_dict(link_def)
    if expand_spec and not expand_spec.is_empty():
        _expand_link_with_variables(ctx, link_def, expand_spec, parent_path, location)
        return

    source_raw = link_def["source"]
    target_raw = link_def["target"]
    pattern = link_def.get("pattern", "mesh")
    count = link_def.get("count", 1)

    src_sel = declared(
        location + ".source",
        lambda: _normalize_link_selector(source_raw, parent_path),
        "selector",
    )
    tgt_sel = declared(
        location + ".target",
        lambda: _normalize_link_selector(target_raw, parent_path),
        "selector",
    )

    _expand_link_pattern(ctx, src_sel, tgt_sel, pattern, link_def, count, location)


def _expand_link_with_variables(
    ctx: DSLExpansionContext,
    link_def: Dict[str, Any],
    expand_spec: ExpansionSpec,
    parent_path: str,
    location: str,
) -> None:
    """Expand a link definition once per combination in its 'expand' block.

    Substitutes $var or ${var} variables in all string fields of the link
    definition (source/target selectors including match condition values,
    attrs, and risk_groups), yielding one full link definition per variable
    combination, as node_rules/link_rules expansion does.

    Args:
        ctx: The DSL expansion context.
        link_def: The link definition including expand block, source, target, etc.
        expand_spec: Parsed expansion spec for link_def (computed by caller).
        parent_path: Prepended to source/target paths.
    """
    # expand_block deep-copies, drops 'expand', and substitutes variables
    # recursively in every string field of the definition.
    for substituted in expand_block(link_def, expand_spec):
        src_sel = declared(
            location + ".source",
            lambda substituted=substituted: _normalize_link_selector(
                substituted["source"], parent_path
            ),
            "selector",
        )
        tgt_sel = declared(
            location + ".target",
            lambda substituted=substituted: _normalize_link_selector(
                substituted["target"], parent_path
            ),
            "selector",
        )
        _expand_link_pattern(
            ctx,
            src_sel,
            tgt_sel,
            substituted.get("pattern", "mesh"),
            substituted,
            substituted.get("count", 1),
            location,
        )


def _expand_link_pattern(
    ctx: DSLExpansionContext,
    source_selector: Any,
    target_selector: Any,
    pattern: str,
    link_def: Dict[str, Any],
    count: int = 1,
    location: str = "link",
) -> None:
    """Create links between the matched nodes using the chosen pattern.

    Supported Patterns:
      * "mesh": Connect every source node to every target node.
      * "one_to_one": Pair each source node with exactly one target node
                      using wrap-around. The larger set size must be
                      a multiple of the smaller set size.

    Both patterns skip self-pairs and deduplicate reversed pairs. That
    deduplication is scoped to a single call: each variable combination of an
    expand: block is an independent link definition, so overlapping selections
    across combinations create parallel links.

    Link properties are flat in link_def (capacity, cost, disabled,
    risk_groups, attrs).

    Args:
        ctx: The context with the target network.
        source_selector: Path string or selector object {path, group_by, match}.
        target_selector: Path string or selector object {path, group_by, match}.
        pattern: "mesh" or "one_to_one".
        link_def: Link definition with flat properties.
        count: Number of parallel links to create for each pair.
    """
    # Validate the declaration before matching, including self-pairs and empty selections.
    _link_properties(link_def, location)
    count = integer(count, location + ".count", minimum=1)
    source_nodes = _select_link_nodes(ctx.network, source_selector)
    target_nodes = _select_link_nodes(ctx.network, target_selector)

    # A link entry whose endpoint matches no node declares nothing: refuse it, naming
    # the entry, so that a mistyped name fails where it is given.
    for end, nodes, selector in (
        ("source", source_nodes, source_selector),
        ("target", target_nodes, target_selector),
    ):
        if not nodes:
            raise ValueError(
                f"link {link_def.get('source')!r} -> {link_def.get('target')!r}: "
                f"{end} {selector.get('path', selector)!r} matches no node"
            )

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
    """Select link endpoint nodes.

    For links, active_only defaults to False (links to disabled nodes are
    created).

    Args:
        network: The network to select from.
        selector: String path or dict with path/group_by/match.

    Returns:
        List of matching nodes (flattened from all groups).
    """
    normalized = normalize_selector(selector, context="link")
    groups = select_nodes(network, normalized, default_active_only=False)
    return [node for nodes in groups.values() for node in nodes]


def _link_properties(definition, location="link"):
    return declared(
        location,
        lambda: Link(
            "<source>",
            "<target>",
            capacity=definition.get("capacity", 1.0),
            cost=definition.get("cost", 1),
            disabled=definition.get("disabled", False),
            attrs=definition.get("attrs", {}),
            risk_groups=expand_risk_group_refs(definition.get("risk_groups", [])),
        ),
        "link <source>-><target>",
    )


def _create_link(
    net: Network,
    source: str,
    target: str,
    link_def: Dict[str, Any],
    count: int = 1,
) -> None:
    """Add `count` parallel links between source and target.

    Args:
        net: The network to which the new link(s) will be added.
        source: Source node name for the link.
        target: Target node name for the link.
        link_def: Flat link properties (capacity, cost, disabled, risk_groups,
            attrs). Capacity defaults to 1.0 and cost to 1.
        count: Number of parallel links to create between source and target
            (the work is linear in it).
    """
    for _ in range(count):
        net.add_link(
            Link(
                source=source,
                target=target,
                capacity=link_def.get("capacity", 1.0),
                cost=link_def.get("cost", 1),
                attrs=link_def.get("attrs", {}),
                disabled=link_def.get("disabled", False),
                risk_groups=expand_risk_group_refs(link_def.get("risk_groups", [])),
            )
        )


def _process_node_rules(net: Network, network_data: Dict[str, Any]) -> None:
    """Apply the 'node_rules' section of the network DSL to existing nodes.

    Rules apply in list order, so a later rule wins where several match the
    same node. Each rule may have {"path", "match", "attrs", "disabled",
    "risk_groups", "expand"}; "path" defaults to every node.

    - "disabled" sets node.disabled.
    - "risk_groups" *replaces* the node's risk_groups.
    - "attrs" merges into node.attrs.

    Args:
        net: The Network whose nodes will be updated.
        network_data: DSL data possibly containing 'node_rules'.
    """
    node_rules = network_data.get("node_rules", [])
    if not isinstance(node_rules, list):
        raise ValueError("'node_rules' must be a list.")

    for index, rule in enumerate(node_rules):
        if not isinstance(rule, dict):
            raise ValueError("Each node_rule must be a dict.")
        check_no_extra_keys(
            rule,
            allowed={"path", "attrs", "disabled", "risk_groups", "match", "expand"},
            context="node rule",
        )

        location = f"network.node_rules[{index}]"
        _, rows = _expand_declaration(rule, location)
        for expanded_rule in rows:
            declared(
                location,
                lambda expanded_rule=expanded_rule, location=location: _apply_node_rule(
                    net, expanded_rule, location
                ),
            )


def _apply_node_rule(net: Network, rule: Dict[str, Any], location="node rule") -> None:
    """Apply a single node rule to matching nodes."""
    declared(
        location,
        lambda: Node(
            "<node>",
            disabled=rule.get("disabled", False),
            attrs=rule.get("attrs", {}),
            risk_groups=expand_risk_group_refs(rule.get("risk_groups", [])),
        ),
        "node <node>",
    )
    path = rule.get("path", ".*")
    match_spec = rule.get("match")
    top_level_disabled = rule.get("disabled", None)
    rule_risk_groups = rule.get("risk_groups", None)

    if "attrs" in rule and not isinstance(rule["attrs"], dict):
        raise ValueError("attrs must be a dict in node rule.")

    attrs_to_set = rule.get("attrs", {})
    _update_nodes(
        net,
        path,
        match_spec,
        attrs_to_set,
        top_level_disabled,
        rule_risk_groups,
        location,
    )


def _process_link_rules(net: Network, network_data: Dict[str, Any]) -> None:
    """Apply the 'link_rules' section of the network DSL to existing links.

    Rules apply in list order, so a later rule wins where several match the
    same link. Each rule must contain {"source", "target"} plus optionally
    {"bidirectional", "capacity", "cost", "disabled", "risk_groups", "attrs",
    "expand", "link_match"}.

    If risk_groups is given, it *replaces* the link's existing risk_groups.

    Args:
        net: The Network whose links will be updated.
        network_data: DSL data possibly containing 'link_rules'.
    """
    link_rules = network_data.get("link_rules", [])
    if not isinstance(link_rules, list):
        raise ValueError("'link_rules' must be a list.")

    for index, link_rule in enumerate(link_rules):
        if not isinstance(link_rule, dict):
            raise ValueError("Each link_rule must be a dict.")
        check_no_extra_keys(
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
        if "source" not in link_rule or "target" not in link_rule:
            raise ValueError("Each link_rule must include 'source' and 'target'.")

        location = f"network.link_rules[{index}]"
        _, rows = _expand_declaration(link_rule, location)
        for expanded_rule in rows:
            declared(
                location,
                lambda expanded_rule=expanded_rule, location=location: _apply_link_rule(
                    net, expanded_rule, location
                ),
            )


def _apply_link_rule(net: Network, rule: Dict[str, Any], location="link rule") -> None:
    """Apply a single link rule to matching links."""
    _link_properties(rule, location)
    source = rule["source"]
    target = rule["target"]
    bidirectional = flag(rule.get("bidirectional", True), "link rule.bidirectional")

    _update_links(net, source, target, rule, bidirectional, location)


def _update_links(
    net: Network,
    source: Any,
    target: Any,
    rule: Dict[str, Any],
    bidirectional: bool = True,
    location: str = "link rule",
) -> None:
    """Update links between nodes selected by source and target.

    Sets capacity, cost, disabled, risk_groups, and attrs from the rule. If
    bidirectional=True, links in both directions are updated. A 'link_match'
    in the rule further filters links by their attributes. If risk_groups is
    given, it *replaces* the link's existing risk_groups.

    Args:
        net: The network whose links should be updated.
        source: Selector (string path or dict with path/match) for source nodes.
        target: Selector (string path or dict with path/match) for target nodes.
        rule: Rule dict with flat link properties.
        bidirectional: If True, also update reversed direction links.
    """
    src_sel = declared(
        location + ".source",
        lambda: normalize_selector(source, context="rule"),
        "selector",
    )
    tgt_sel = declared(
        location + ".target",
        lambda: normalize_selector(target, context="rule"),
        "selector",
    )

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

        if link_match is not None:
            link_attrs = flatten_link_attrs(link, link_id)
            if not evaluate_conditions(
                link_attrs, link_match.conditions, link_match.logic
            ):
                continue

        changes: Dict[str, Any] = {}
        if new_capacity is not None:
            # A rule's capacity is labelled by the link it updates.
            changes["capacity"] = new_capacity
        if new_cost is not None:
            changes["cost"] = new_cost
        if new_disabled_val is not None:
            changes["disabled"] = flag(new_disabled_val, "link rule.disabled")
        if new_risk_groups is not None:
            changes["risk_groups"] = expand_risk_group_refs(new_risk_groups)
        if new_attrs:
            changes["attrs"] = {**link.attrs, **new_attrs}
        if changes:
            net.replace_link(link_id, **changes)


def _update_nodes(
    net: Network,
    path: str,
    match_spec: Optional[Dict[str, Any]],
    attrs: Dict[str, Any],
    disabled_val: Any = None,
    risk_groups_val: Any = None,
    location: str = "node rule",
) -> None:
    """Update nodes matching a path pattern and optional match conditions.

    Args:
        net: The network containing the nodes.
        path: A path pattern identifying which node group(s) to modify.
        match_spec: Optional match conditions dict (with 'conditions' and 'logic').
        attrs: Attributes merged into node.attrs.
        disabled_val: New node.disabled value, or None to leave it unchanged.
        risk_groups_val: Names that *replace* node.risk_groups, or None to
            leave them unchanged.
    """
    selector_dict: Dict[str, Any] = {"path": path}
    if match_spec:
        selector_dict["match"] = match_spec

    normalized = declared(
        location, lambda: normalize_selector(selector_dict, context="rule"), "selector"
    )
    node_groups = select_nodes(net, normalized, default_active_only=False)

    changes: Dict[str, Any] = {}
    if disabled_val is not None:
        changes["disabled"] = flag(disabled_val, location + ".disabled")
    if risk_groups_val is not None:
        changes["risk_groups"] = expand_risk_group_refs(risk_groups_val)
    for _, nodes in node_groups.items():
        for node in nodes:
            current = net.nodes[node.name]
            net.replace_node(node.name, **changes, attrs={**current.attrs, **attrs})


def _longest_subgroup_prefix(key: str, group_names: Iterable[str]) -> Optional[str]:
    """Return the longest group name prefixing key as '<group>.<field...>'.

    Subgroup names may themselves contain dots, so override keys are matched
    against literal group names by longest prefix rather than by splitting on
    the first dot. Equal-length distinct names cannot both prefix the same
    key, so the longest match is unique.

    Args:
        key: Dotted params override key (e.g. 'rack.a.count').
        group_names: Literal blueprint subgroup names.

    Returns:
        The longest matching group name, or None if no group name prefixes key.
    """
    matches = [name for name in group_names if key.startswith(name + ".")]
    return max(matches, key=len) if matches else None


def _render_source_path(base, parts):
    return base + "".join(
        f"[{part}]" if isinstance(part, int) else f".{part}" for part in parts
    )


def _source_path(sources, parts, location):
    for size in range(len(parts), -1, -1):
        if parts[:size] in sources:
            return _render_source_path(sources[parts[:size]], parts[size:])
    return _render_source_path(location, parts)


def _child_sources(sources, parts):
    return {
        key[len(parts) :]: path
        for key, path in sources.items()
        if key[: len(parts)] == parts
    }


def _apply_parameters(
    subgroup_name: str,
    subgroup_def: Dict[str, Any],
    params_overrides: Dict[str, Any],
    override_to_group: Dict[str, str],
    parent_sources: dict[tuple[str, ...], str],
    location: str,
) -> tuple[Dict[str, Any], dict[tuple[str, ...], str]]:
    """Apply blueprint `params` overrides to one subgroup definition.

    Example:
        If 'spine.count' = 6 is in params_overrides,
        it sets 'count' = 6 for the 'spine' subgroup.
        If 'spine.attrs.hw_type' = 'Dell', it sets subgroup_def['attrs']['hw_type'] = 'Dell'.

    Args:
        subgroup_name (str): Name of the subgroup in the blueprint.
        subgroup_def (Dict[str, Any]): The default definition of that subgroup.
        params_overrides (Dict[str, Any]): Overrides in the form of
            {'spine.count': 6, 'spine.attrs.hw_type': 'Dell'}.
        override_to_group (Dict[str, str]): Override key -> subgroup name,
            resolved once by the caller via `_longest_subgroup_prefix` so a
            key applies to subgroup 'rack.a' rather than 'rack' when both
            exist and the key starts with 'rack.a.'.
        parent_sources: Overrides that supplied this instance's parameter fields.
        location: Source declaration of this instance.

    Returns:
        The copied definition and the source paths of its overridden fields.
        Source metadata stays separate from node definitions.
    """
    out = copy.deepcopy(subgroup_def)
    sources = {}

    for key, val in params_overrides.items():
        if override_to_group.get(key) == subgroup_name:
            subpath = key[len(subgroup_name) + 1 :].split(".")
            label = _source_path(parent_sources, ("params", key), location)
            if subpath == ["disabled"]:
                val = flag(val, label)
            elif subpath == ["template"]:
                val = text(val, label)
            # A later subtree assignment replaces any earlier descendant source;
            # a later field assignment keeps the ancestor source for its siblings.
            parts = tuple(subpath)
            sources = {
                p: origin for p, origin in sources.items() if p[: len(parts)] != parts
            }
            sources[parts] = label
            _apply_nested_path(out, subpath, val)

    return out, sources


def _apply_nested_path(
    node_def: Dict[str, Any], path_parts: List[str], value: Any
) -> None:
    """Set a nested field, e.g. ["attrs", "role"] sets node_def["attrs"]["role"].

    Creates intermediate dicts as needed, replacing non-dict values on the path.

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
