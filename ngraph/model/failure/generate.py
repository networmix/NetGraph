"""Dynamic risk group generation from entity attributes.

Creates one risk group per unique value of a chosen node or link attribute.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional

from ngraph.logging import get_logger
from ngraph.model.network import RiskGroup
from ngraph.model.selectors import (
    flatten_link_attrs,
    flatten_node_attrs,
    link_path_key,
    resolve_attr_path,
)

if TYPE_CHECKING:
    from ngraph.model.network import Network

_logger = get_logger(__name__)


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


def generate_risk_groups(network: "Network", spec: GenerateSpec) -> List[RiskGroup]:
    """Generate risk groups from unique attribute values.

    For each unique value of the specified attribute, creates a new risk
    group and adds all matching entities to it.

    Args:
        network: Network with nodes and links populated.
        spec: Generation specification.

    Returns:
        List of newly created RiskGroup objects.

    Raises:
        ValueError: If `group_by` resolves to an unhashable value, or if the
            name template renders the same group name for two distinct values.

    Note:
        Modifies entity risk_groups sets in place.
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

    # Apply path filter if specified
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

    # Group by attribute value
    groups: Dict[Any, List] = defaultdict(list)
    for entity_id, entity, attrs in entities:
        found, value = resolve_attr_path(attrs, spec.group_by)
        if found and value is not None:
            try:
                groups[value].append((entity_id, entity))
            except TypeError as exc:
                raise ValueError(
                    f"generate block group_by '{spec.group_by}' resolved to an "
                    f"unhashable {type(value).__name__} on entity "
                    f"'{entity_id}'; group_by requires scalar attribute values"
                ) from exc

    # Create risk groups
    result: List[RiskGroup] = []
    seen_names: Dict[str, Any] = {}
    for value, members in groups.items():
        name = spec.name.replace("${value}", str(value))
        if name in seen_names:
            # Distinct group_by values (e.g. int 1 and str "1") can render to
            # the same string; a silent merge or a generic downstream conflict
            # error would hide the real cause.
            raise ValueError(
                f"generate block name template '{spec.name}' renders the same "
                f"group name '{name}' for distinct group_by values "
                f"{seen_names[name]!r} and {value!r}"
            )
        seen_names[name] = value

        rg = RiskGroup(name=name, attrs=dict(spec.attrs))

        for _entity_id, entity in members:
            entity.risk_groups.add(name)

        result.append(rg)

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
        ValueError: If 'scope' is missing or is neither 'node' nor 'link', if
            'group_by' or 'name' is missing, or if 'name' omits the '${value}'
            placeholder.
    """
    scope = raw.get("scope")
    if not scope:
        raise ValueError("generate requires 'scope' field (node or link)")
    if scope not in ("node", "link"):
        raise ValueError(f"generate scope must be 'node' or 'link', got '{scope}'")

    path = raw.get("path")

    group_by = raw.get("group_by")
    if not group_by:
        raise ValueError("generate requires 'group_by' field")

    name = raw.get("name")
    if not name:
        raise ValueError("generate requires 'name' field")

    if "${value}" not in name:
        raise ValueError("generate name must contain '${value}' placeholder")

    attrs = raw.get("attrs", {})

    return GenerateSpec(
        scope=scope,
        group_by=group_by,
        name=name,
        path=path,
        attrs=attrs,
    )
