"""Risk-group declarations and the shared, typed membership resolver."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    cast,
)

from ngraph.logging import get_logger
from ngraph.model.selectors import (
    EntityScope,
    MatchSpec,
    flatten_link_attrs,
    flatten_node_attrs,
    flatten_risk_group_attrs,
    link_path_key,
    match_entity_ids,
    parse_match_spec,
    resolve_attr_path,
)
from ngraph.utils.values import (
    _shown,
    collection,
    flag,
    frozen_attrs,
    frozen_json,
    optional_pattern,
    own,
    text,
)
from ngraph.utils.yaml_utils import (
    check_no_extra_keys,
    declared,
    normalize_yaml_dict_keys,
)

if TYPE_CHECKING:
    from ngraph.model.network import Network

_logger = get_logger(__name__)


@dataclass(frozen=True)
class RiskGroup:
    """A named failure domain with optional nested, unregistered descendants.

    ``attrs`` holds finite JSON metadata, checked and stored read-only at
    construction.
    """

    name: str
    children: Sequence[RiskGroup] = ()
    disabled: bool = False
    attrs: dict[str, Any] = field(default_factory=dict)
    _membership_raw: dict[str, Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        name = text(self.name, "risk group.name")
        label = f"risk group {name}"
        children = collection(self.children, f"{label}.children")
        if not all(isinstance(child, RiskGroup) for child in children):
            raise TypeError(
                f"{label}.children: expected RiskGroup values, got {self.children!r}"
            )
        own(
            self,
            name=name,
            children=children,
            disabled=flag(self.disabled, f"{label}.disabled"),
            attrs=frozen_attrs(self.attrs, f"{label}.attrs"),
            _membership_raw=frozen_json(self._membership_raw, f"{label}.membership"),
        )


@dataclass(frozen=True)
class Members:
    nodes: frozenset[str]
    links: frozenset[str]


@dataclass(frozen=True)
class MembershipIndex:
    """One immutable resolution of the current editable network.

    Node and link identifiers occupy separate namespaces. Mutation callers
    build a fresh index; prepared analyses retain their owned snapshot.
    """

    groups: Mapping[str, RiskGroup]
    direct: Mapping[str, Members]
    transitive: Mapping[str, Members]
    node_groups: Mapping[str, frozenset[str]]
    link_groups: Mapping[str, frozenset[str]]

    @classmethod
    def build(cls, network: Network) -> MembershipIndex:
        groups: dict[str, RiskGroup] = {}
        colors: dict[str, int] = {}
        stack: list[str] = []
        order: list[str] = []
        first_paths: dict[str, tuple[str, ...]] = {}
        signatures: dict[int, tuple] = {}

        def inline_signature(
            group: RiskGroup, path: tuple[str, ...], ancestors: tuple[int, ...] = ()
        ) -> tuple:
            if group.name in network.risk_groups:
                return ("registered", group.name)
            identity = id(group)
            if identity in ancestors:
                raise ValueError("risk group cycle: " + " -> ".join(path))
            if identity not in signatures:
                signatures[identity] = (
                    group.name,
                    group.disabled,
                    group.attrs,
                    group._membership_raw,
                    tuple(
                        inline_signature(
                            child, (*path, child.name), (*ancestors, identity)
                        )
                        for child in group.children
                    ),
                )
            return signatures[identity]

        def visit(group: RiskGroup, path: tuple[str, ...]) -> None:
            name = group.name  # a nonempty name, checked by the group
            # A child naming a registered group refers to its top-level declaration.
            # Inline descendants without a registered declaration retain their own tree.
            group = network.risk_groups.get(name, group)
            previous = groups.get(name)
            if previous is not None and previous is not group:
                first_path = first_paths[name]
                if inline_signature(previous, first_path) != inline_signature(
                    group, path
                ):
                    raise ValueError(
                        f"risk group {name}: conflicting inline declarations at "
                        f"{' -> '.join(first_path)} and {' -> '.join(path)}"
                    )
                group = previous
            groups[name] = group
            first_paths.setdefault(name, path)
            if colors.get(name) == 1:
                start = stack.index(name)
                raise ValueError(
                    "risk group cycle: " + " -> ".join((*stack[start:], name))
                )
            if colors.get(name) == 2:
                return
            colors[name] = 1
            stack.append(name)
            for child in group.children:
                visit(child, (*path, child.name))
            stack.pop()
            colors[name] = 2
            order.append(name)

        for key, group in network.risk_groups.items():
            if key != group.name:
                raise ValueError(
                    f"risk group {key}: key differs from name {group.name}"
                )
            visit(group, (key,))

        node_groups: dict[str, frozenset[str]] = {}
        link_groups: dict[str, frozenset[str]] = {}
        direct_nodes: dict[str, set[str]] = {name: set() for name in groups}
        direct_links: dict[str, set[str]] = {name: set() for name in groups}
        undefined: list[str] = []
        for kind, entities, inverse, direct in (
            ("node", network.nodes, node_groups, direct_nodes),
            ("link", network.links, link_groups, direct_links),
        ):
            for identifier, entity in entities.items():
                names = frozenset(entity.risk_groups)
                unknown = names.difference(groups)
                if unknown:
                    owner = (
                        f"Node {identifier!r}"
                        if kind == "node"
                        else f"Link '{network.links[identifier].source}->{network.links[identifier].target}' ({identifier})"
                    )
                    undefined.extend(
                        f"{owner}: unknown risk groups {name!r}"
                        for name in sorted(unknown)
                    )
                inverse[identifier] = names
                for name in names.difference(unknown):
                    direct[name].add(identifier)
        if undefined:
            details = "; ".join(undefined[:10])
            if len(undefined) > 10:
                details += "; ..."
            raise ValueError(
                f"{len(undefined)} undefined risk group references: {details}. "
                "Define the risk_groups or remove their references."
            )
        direct = {
            name: Members(frozenset(direct_nodes[name]), frozenset(direct_links[name]))
            for name in sorted(groups)
        }
        transitive: dict[str, Members] = {}
        for name in order:
            nodes = set(direct[name].nodes)
            links = set(direct[name].links)
            for child in groups[name].children:
                nodes.update(transitive[child.name].nodes)
                links.update(transitive[child.name].links)
            transitive[name] = Members(frozenset(nodes), frozenset(links))
        return cls(
            MappingProxyType(groups),
            MappingProxyType(direct),
            MappingProxyType(transitive),
            MappingProxyType(node_groups),
            MappingProxyType(link_groups),
        )

    def members(self, group: str, recursive: bool = True) -> Members:
        try:
            return (self.transitive if recursive else self.direct)[group]
        except KeyError:
            raise ValueError(f"unknown risk group {group}") from None

    def expand(
        self, nodes: set[str], links: set[str], groups: set[str], *, shared: bool
    ) -> Members:
        """Expand explicit group causes, then optional shared direct membership."""
        nodes = set(nodes)
        links = set(links)
        for name in sorted(groups):
            members = self.members(name)
            nodes.update(members.nodes)
            links.update(members.links)
        if shared:
            pending = [("node", name) for name in nodes]
            pending.extend(("link", name) for name in links)
            visited: set[tuple[str, str]] = set()
            expanded: set[str] = set()
            while pending:
                kind, identifier = pending.pop()
                key = (kind, identifier)
                if key in visited:
                    continue
                visited.add(key)
                memberships = self.node_groups if kind == "node" else self.link_groups
                for name in sorted(memberships.get(identifier, ())):
                    if name in expanded:
                        continue
                    expanded.add(name)
                    # Sharing a group expands its direct members. Descendants
                    # are reached only by an explicitly failed group cause.
                    members = self.direct[name]
                    pending.extend(("node", n) for n in members.nodes.difference(nodes))
                    pending.extend(("link", n) for n in members.links.difference(links))
                    nodes.update(members.nodes)
                    links.update(members.links)
        return Members(frozenset(nodes), frozenset(links))


@dataclass
class GenerateSpec:
    """Parsed generate block specification.

    Attributes:
        scope: Type of entities to group ("node" or "link").
        path: Optional regex pattern to filter entities by name.
        group_by: Attribute name to group by (supports dot-notation).
        name: Template for generated group names. Use ${value}
            as placeholder for the attribute value.
        attrs: Optional static attributes for generated groups.
    """

    scope: Literal["node", "link"]
    group_by: str
    name: str
    path: Optional[str] = None
    attrs: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        scope = text(self.scope, "generate.scope")
        if scope not in ("node", "link"):
            raise ValueError(
                f"generate.scope: expected node or link, got {self.scope!r}"
            )
        name = text(self.name, "generate.name")
        if "${value}" not in name:
            raise ValueError(
                f"generate.name: must contain '${{value}}', got {self.name!r}"
            )
        own(
            self,
            scope=scope,
            group_by=text(self.group_by, "generate.group_by"),
            name=name,
            path=optional_pattern(self.path, "generate.path", empty=True),
            attrs=frozen_attrs(self.attrs, "generate.attrs"),
        )


def generate_risk_groups(network: "Network", spec: GenerateSpec) -> List[RiskGroup]:
    """Generate risk groups from unique attribute values.

    For each unique value of the specified attribute, creates a new risk
    group and adds its name to the `risk_groups` of every matching entity,
    replacing those records in the network. The caller registers the
    returned groups.

    Args:
        network: Network with nodes and links populated.
        spec: Generation specification.

    Returns:
        List of newly created RiskGroup objects.

    Raises:
        ValueError: If `group_by` resolves to an unhashable value, its value
            cannot be rendered as a group name, or the name template renders
            the same group name for two distinct values.
    """
    path_pattern = re.compile(spec.path) if spec.path else None

    # (entity id, entity, flattened attrs) triples for the target scope
    if spec.scope == "node":
        entities = [
            (node.name, node, flatten_node_attrs(node))
            for node in network.nodes.values()
        ]
    else:
        entities = [
            (link_id, link, flatten_link_attrs(link, link_id))
            for link_id, link in network.links.items()
        ]

    # Nodes match `path` against the node name, links against link_path_key.
    if path_pattern:
        if spec.scope == "node":
            entities = [
                (eid, entity, attrs)
                for eid, entity, attrs in entities
                if path_pattern.match(eid)
            ]
        else:
            entities = [
                (eid, entity, attrs)
                for eid, entity, attrs in entities
                if path_pattern.match(link_path_key(attrs))
            ]

    # Entities lacking the attribute, or holding None, join no group.
    groups: Dict[Any, List] = defaultdict(list)
    for entity_id, entity, attrs in entities:
        found, value = resolve_attr_path(attrs, spec.group_by)
        if found and value is not None:
            try:
                groups[value].append((entity_id, entity))
            except TypeError as exc:
                raise ValueError(
                    f"generate.group_by: {spec.group_by!r} resolved to an "
                    f"unhashable {type(value).__name__} on entity "
                    f"'{entity_id}'; group_by requires scalar attribute values, got {_shown(value)}"
                ) from exc

    result: List[RiskGroup] = []
    seen_names: Dict[str, Any] = {}
    joined: Dict[str, Set[str]] = defaultdict(set)
    for value, members in groups.items():
        try:
            rendered = str(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(
                f"generate.group_by: cannot render a group name from {_shown(value)}"
            ) from exc
        name = spec.name.replace("${value}", rendered)
        if name in seen_names:
            # Distinct group_by values (e.g. int 1 and str "1") can render to
            # the same string; a silent merge or a generic downstream conflict
            # error would hide the real cause.
            raise ValueError(
                f"generate.name: template {spec.name!r} renders the same "
                f"group name '{name}' for distinct group_by values "
                f"{_shown(seen_names[name])} and {_shown(value)}"
            )
        seen_names[name] = value

        rg = RiskGroup(name=name, attrs=dict(spec.attrs))

        for entity_id, _entity in members:
            joined[entity_id].add(name)

        result.append(rg)
    _join_groups(network, spec.scope, joined)

    _logger.debug(
        "Generated %d risk groups from %s.%s",
        len(result),
        spec.scope,
        spec.group_by,
    )

    return result


def parse_generate_spec(raw: Dict[str, Any]) -> GenerateSpec:
    """Parse raw generate dict into a GenerateSpec.

    Args:
        raw: Raw generate dict from YAML.

    Returns:
        Parsed GenerateSpec.

    Raises:
        ValueError: If the block carries an unrecognized key, 'scope' is
            missing or is neither 'node' nor 'link', 'group_by' or 'name' is
            missing, or 'name' omits the '${value}' placeholder.
    """
    check_no_extra_keys(
        raw, {"scope", "path", "group_by", "name", "attrs"}, "generate block"
    )
    return GenerateSpec(
        scope=cast(Any, raw.get("scope")),
        group_by=cast(Any, raw.get("group_by")),
        name=cast(Any, raw.get("name")),
        path=raw.get("path"),
        attrs=raw.get("attrs", {}),
    )


@dataclass
class MembershipSpec:
    """Parsed membership rule specification.

    Attributes:
        scope: Type of entities to match ("node", "link", or "risk_group").
        path: Optional regex pattern. For node and risk_group scope it is
            matched against the entity ID; for link scope it is matched
            against the "source|target" key, not the link ID.
        match: Match specification with conditions.
    """

    scope: EntityScope
    path: Optional[str] = None
    match: Optional[MatchSpec] = None

    def __post_init__(self) -> None:
        scope = text(self.scope, "membership.scope")
        if scope not in ("node", "link", "risk_group"):
            raise ValueError(
                f"membership.scope: expected node, link or risk_group, got {self.scope!r}"
            )
        if self.match is not None and not isinstance(self.match, MatchSpec):
            raise TypeError(
                f"membership.match: expected MatchSpec or None, got {self.match!r}"
            )
        own(
            self,
            scope=scope,
            path=optional_pattern(self.path, "membership.path", empty=True),
        )


def resolve_membership_rules(
    network: "Network", locations: Dict[str, str] | None = None
) -> None:
    """Apply membership rules to populate entity risk_groups sets.

    For each risk group with a `_membership_raw` specification:
    - If scope is "node" or "link": adds the risk group name to each
      matched entity's risk_groups set.
    - If scope is "risk_group": adds matched risk groups as children
      of this risk group (hierarchical membership).

    Replaces the affected records in the network. Call after all risk groups
    are registered but before validation.

    Args:
        network: Network with risk_groups, nodes, and links populated.
    """
    # Flattened attribute maps are shared by all membership rules; build each
    # lazily once instead of re-flattening every entity per rule.
    flat_maps: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _flat(scope: str) -> Dict[str, Dict[str, Any]]:
        cached = flat_maps.get(scope)
        if cached is not None:
            return cached
        if scope == "node":
            built = {
                node.name: flatten_node_attrs(node) for node in network.nodes.values()
            }
        elif scope == "link":
            built = {
                link_id: flatten_link_attrs(link, link_id)
                for link_id, link in network.links.items()
            }
        else:
            built = {
                rg.name: flatten_risk_group_attrs(rg)
                for rg in network.risk_groups.values()
            }
        flat_maps[scope] = built
        return built

    for rg_name in list(network.risk_groups):
        rg = network.risk_groups[rg_name]
        membership_raw = rg._membership_raw
        if membership_raw is None:
            continue

        location = (locations or {}).get(rg_name, f"risk group {rg_name}.membership")
        spec = declared(
            location,
            lambda raw=membership_raw: _parse_membership_spec(raw),
            "membership",
        )

        matched_count = 0
        if spec.scope == "risk_group":
            matched_rgs = _select_risk_groups(network, spec, _flat("risk_group"))
            children = list(rg.children)
            for matched_rg in matched_rgs:
                # A group never becomes its own child (a one-node cycle).
                if matched_rg.name != rg_name:
                    if matched_rg not in children:
                        children.append(matched_rg)
                        matched_count += 1
            if matched_count:
                network.risk_groups[rg_name] = replace(rg, children=tuple(children))
        else:
            matched_ids = _select_entity_ids(spec, _flat(spec.scope))
            matched_count = len(matched_ids)
            _join_groups(
                network, spec.scope, {entity_id: {rg_name} for entity_id in matched_ids}
            )

        _logger.debug(
            "Resolved membership for '%s': scope=%s, matched=%d",
            rg_name,
            spec.scope,
            matched_count,
        )


def _parse_membership_spec(raw: Dict[str, Any]) -> MembershipSpec:
    """Parse raw membership dict into a MembershipSpec.

    Args:
        raw: Raw membership dict from YAML.

    Returns:
        Parsed MembershipSpec.

    Raises:
        ValueError: If the rule carries an unrecognized key, 'scope' is
            missing or is not one of node/link/risk_group, or neither 'path'
            nor 'match' is given.
    """
    check_no_extra_keys(raw, {"scope", "path", "match"}, "membership rule")
    scope = raw.get("scope")
    if not scope:
        raise ValueError(
            "membership requires 'scope' field (node, link, or risk_group)"
        )
    if scope not in ("node", "link", "risk_group"):
        raise ValueError(
            f"scope must be 'node', 'link', or 'risk_group', got '{scope}'"
        )

    path = optional_pattern(raw.get("path"), "membership.path", empty=True)
    match_raw = raw.get("match")

    if path is None and match_raw is None:
        raise ValueError(
            f"membership: expected at least 'path' or 'match', got {raw!r}"
        )

    match_spec = None
    if match_raw is not None:
        # Unlike failure rules, membership rules default to "and" logic and
        # need at least one condition.
        match_spec = parse_match_spec(
            match_raw,
            default_logic="and",
            require_conditions=True,
            context="membership.match",
        )

    return MembershipSpec(scope=scope, path=path, match=match_spec)


def _match_spec_ids(
    entity_attrs: Dict[str, Dict[str, Any]],
    spec: MembershipSpec,
    path_key: Callable[[str, Dict[str, Any]], str],
) -> Set[str]:
    """Return entity IDs passing the spec's path filter and match conditions.

    Args:
        entity_attrs: Mapping of entity_id -> flattened attribute dict.
        spec: Membership specification with path and match.
        path_key: Maps (entity_id, attrs) to the string the path regex
            matches against (the ID for nodes/risk groups, the
            "source|target" form for links).

    Returns:
        Set of matching entity IDs.
    """
    if spec.path:
        path_pattern = re.compile(spec.path)
        candidate_ids = {
            eid
            for eid, attrs in entity_attrs.items()
            if path_pattern.match(path_key(eid, attrs))
        }
    else:
        candidate_ids = set(entity_attrs.keys())

    if spec.match:
        filtered_attrs = {k: v for k, v in entity_attrs.items() if k in candidate_ids}
        return match_entity_ids(filtered_attrs, spec.match.conditions, spec.match.logic)
    return candidate_ids


def _select_entity_ids(
    spec: MembershipSpec,
    entity_attrs: Dict[str, Dict[str, Any]],
) -> Set[str]:
    """Select node names or link ids based on path and/or match conditions.

    Args:
        spec: Membership specification with scope ("node" or "link"),
            path, and match.
        entity_attrs: Pre-flattened attribute map for the spec's scope.

    Returns:
        Matched node names or link ids.
    """
    if spec.scope == "node":
        return _match_spec_ids(entity_attrs, spec, lambda eid, attrs: eid)
    return _match_spec_ids(entity_attrs, spec, lambda eid, attrs: link_path_key(attrs))


def _join_groups(
    network: "Network", scope: str, joined: Mapping[str, Set[str]]
) -> None:
    """Replace each named node or link by a copy that also joins the groups."""
    for entity_id, names in joined.items():
        if scope == "node":
            node = network.nodes[entity_id]
            network.replace_node(entity_id, risk_groups=node.risk_groups | names)
        else:
            link = network.links[entity_id]
            network.replace_link(entity_id, risk_groups=link.risk_groups | names)


def _select_risk_groups(
    network: "Network",
    spec: MembershipSpec,
    entity_attrs: Dict[str, Dict[str, Any]],
) -> List["RiskGroup"]:
    """Select risk groups based on path and/or match conditions.

    Args:
        network: Network with risk_groups.
        spec: Membership specification with path and match.
        entity_attrs: Pre-flattened risk-group attribute map.

    Returns:
        List of matched RiskGroup objects.
    """
    matched_ids = _match_spec_ids(entity_attrs, spec, lambda eid, attrs: eid)
    return [network.risk_groups[rg_name] for rg_name in matched_ids]


_RG_KEYS = frozenset({"name", "attrs", "children", "disabled", "membership"})


_RG_CHILD_KEYS = frozenset({"name", "attrs", "children"})


def build_risk_groups(
    rg_data: List[Any],
) -> tuple[List[RiskGroup], List[Dict[str, Any]]]:
    """Build RiskGroup objects from raw config data.

    Supports:
    - String shorthand: "GroupName" is equivalent to {name: "GroupName"}
    - Bracket expansion: {name: "DC[1-3]_Power"} creates DC1_Power, DC2_Power, DC3_Power
    - Children are also expanded recursively
    - Generate blocks: {generate: {...}} for dynamic group creation

    'membership', 'disabled', and 'generate' are only honored on top-level
    entries: only top-level groups are registered in network.risk_groups, so
    these keys would be silently inert on nested children. Child entries
    carrying them are rejected with ValueError.

    Args:
        rg_data: List of risk group definitions (strings or dicts).

    Returns:
        Tuple of (explicit_risk_groups, generate_specs_raw):
        - explicit_risk_groups: List of RiskGroup objects with names expanded.
        - generate_specs_raw: List of raw generate block dicts for deferred processing.

    Raises:
        ValueError: If an entry is neither a string nor a dict, lacks a name,
            carries an unrecognized key, or is a child entry with
            'membership', 'disabled' or 'generate'.
    """
    from ngraph.dsl.expansion import expand_name_patterns

    def normalize_entry(entry: Any, location: str) -> Dict[str, Any]:
        """Normalize entry to dict format, handling string shorthand."""
        if isinstance(entry, str):
            return {"name": entry}
        if isinstance(entry, dict):
            return entry
        raise ValueError(
            f"{location}: RiskGroup entry must be a string or dict, got {entry!r}"
        )

    def build_one(d: Dict[str, Any], location: str) -> RiskGroup:
        """Build a single RiskGroup (name already expanded)."""
        name = d["name"]
        disabled = d.get("disabled", False)
        children_list = d.get("children", [])
        child_objs = expand_and_build(
            children_list, location + ".children", in_children=True
        )
        attrs = normalize_yaml_dict_keys(d.get("attrs", {}))
        # Resolved later by resolve_membership_rules, once all groups exist.
        membership_raw = d.get("membership")
        return declared(
            location,
            lambda: RiskGroup(
                name=name,
                disabled=disabled,
                children=child_objs,
                attrs=attrs,
                _membership_raw=membership_raw,
            ),
            f"risk group {name}",
        )

    def expand_and_build(
        entries: List[Any],
        path: str = "risk_groups",
        *,
        in_children: bool = False,
        positions: List[int] | None = None,
    ) -> List[RiskGroup]:
        """Expand names and build RiskGroups for a list of entries."""
        result: List[RiskGroup] = []
        for index, entry in enumerate(entries):
            position = positions[index] if positions is not None else index
            location = f"{path}[{position}]"
            normalized = normalize_entry(entry, location)
            if "generate" in normalized:
                raise ValueError(
                    f"{location}: 'generate' blocks not allowed in children, got {entry!r}"
                )
            if in_children:
                # Only top-level groups are registered in network.risk_groups,
                # so membership rules and disabled flags on nested children
                # would be silently ignored. Reject them instead.
                if "membership" in normalized:
                    raise ValueError(
                        f"{location} = {entry!r}: 'membership' rules not allowed in children; define "
                        "the group at top level and reference it as a child"
                    )
                if "disabled" in normalized:
                    raise ValueError(
                        f"{location} = {entry!r}: 'disabled' not allowed in children; define the group "
                        "at top level and reference it as a child"
                    )
            name = normalized.get("name", "")
            if not name:
                raise ValueError(
                    f"{location}: RiskGroup entry missing 'name' field, got {entry!r}"
                )
            check_no_extra_keys(
                normalized,
                _RG_CHILD_KEYS if in_children else _RG_KEYS,
                f"risk group '{name}'",
            )
            expanded_names = expand_name_patterns(name)
            for exp_name in expanded_names:
                modified = dict(normalized)
                modified["name"] = exp_name
                result.append(build_one(modified, location))
        return result

    # Generate blocks need the built network, so they are returned unprocessed.
    explicit_entries: List[Any] = []
    explicit_positions: List[int] = []
    generate_specs: List[Dict[str, Any]] = []

    for position, entry in enumerate(rg_data):
        if isinstance(entry, dict) and "generate" in entry:
            check_no_extra_keys(entry, {"generate"}, "risk group generate entry")
            generate_specs.append(entry["generate"])
        else:
            explicit_entries.append(entry)
            explicit_positions.append(position)

    return expand_and_build(
        explicit_entries, positions=explicit_positions
    ), generate_specs
