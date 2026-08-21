"""Component and ComponentsLibrary classes for hardware capex/power modeling."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

import yaml

from ngraph.logging import get_logger
from ngraph.utils.yaml_utils import normalize_yaml_dict_keys

LOGGER = get_logger(__name__)


@dataclass
class Component:
    """A generic component that can represent chassis, line cards, optics, etc.
    Components can have nested children, each with their own capex, power, etc.

    Attributes:
        name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
        component_type (str): A string label (e.g., "chassis", "linecard", "optic").
        description (str): A human-readable description of this component.
        capex (float): Monetary capex of a single instance of this component.
        power_watts (float): Typical/nominal power usage (watts) for one instance.
        power_watts_max (float): Maximum/peak power usage (watts) for one instance.
        capacity (float): A generic capacity measure (e.g., platform capacity).
        ports (int): Number of ports if relevant for this component.
        count (int): How many identical copies of this component are present.
        attrs (Dict[str, Any]): Arbitrary key-value attributes for extra metadata.
        children (Dict[str, Component]): Nested child components (e.g., line cards
            inside a chassis), keyed by child name.
    """

    name: str
    component_type: str = "generic"
    description: str = ""
    capex: float = 0.0

    power_watts: float = 0.0  # Typical power usage
    power_watts_max: float = 0.0  # Peak power usage

    capacity: float = 0.0
    ports: int = 0
    count: int = 1

    attrs: Dict[str, Any] = field(default_factory=dict)
    children: Dict[str, Component] = field(default_factory=dict)

    def total_capex(self) -> float:
        """Computes total capex including children, multiplied by count."""
        single_instance_capex = self.capex
        for child in self.children.values():
            single_instance_capex += child.total_capex()
        return single_instance_capex * self.count

    def total_power(self) -> float:
        """Computes *typical* power for this component and all descendants.

        Returns:
            float: Typical power in watts, summed over children and multiplied
                by this component's ``count``.
        """
        single_instance_power = self.power_watts
        for child in self.children.values():
            single_instance_power += child.total_power()
        return single_instance_power * self.count

    def total_power_max(self) -> float:
        """Computes *peak* power for this component and all descendants.

        Returns:
            float: Maximum (peak) power in watts, summed over children and
                multiplied by this component's ``count``.
        """
        single_instance_power_max = self.power_watts_max
        for child in self.children.values():
            single_instance_power_max += child.total_power_max()
        return single_instance_power_max * self.count

    def total_capacity(self) -> float:
        """Computes capacity for this component and all descendants.

        Returns:
            float: Capacity summed over children and multiplied by this
                component's ``count``, in dimensionless or user-defined units.
        """
        single_instance_capacity = self.capacity
        for child in self.children.values():
            single_instance_capacity += child.total_capacity()
        return single_instance_capacity * self.count

    def as_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """Returns a dictionary containing all properties of this component.

        Args:
            include_children (bool): If True, recursively includes children.

        Returns:
            Dict[str, Any]: One key per field, with ``attrs`` shallow-copied and
                a ``children`` key present only when ``include_children``.
        """
        data = {
            "name": self.name,
            "component_type": self.component_type,
            "description": self.description,
            "capex": self.capex,
            "power_watts": self.power_watts,
            "power_watts_max": self.power_watts_max,
            "capacity": self.capacity,
            "ports": self.ports,
            "count": self.count,
            "attrs": dict(self.attrs),  # shallow copy
        }
        if include_children:
            data["children"] = {
                child_name: child.as_dict(True)
                for child_name, child in self.children.items()
            }
        return data


@dataclass
class ComponentsLibrary:
    """Holds a collection of named Components. Each entry is a top-level "template"
    that can be referenced for cost/power/capacity lookups, possibly with nested children.

    Example (YAML-like):
        components:
          BigSwitch:
            component_type: chassis
            capex: 20000
            power_watts: 1750
            capacity: 25600
            children:
              PIM16Q-16x200G:
                component_type: linecard
                capex: 1000
                power_watts: 10
                ports: 16
                count: 8
          200G-FR4:
            component_type: optic
            capex: 2000
            power_watts: 6
            power_watts_max: 6.5
    """

    components: Dict[str, Component] = field(default_factory=dict)

    def get(self, name: str) -> Optional[Component]:
        """Retrieves a Component by its name from the library.

        Args:
            name (str): Top-level component name as registered in the library.

        Returns:
            Optional[Component]: The requested Component, or None if the name
                is not registered.
        """
        return self.components.get(name)

    def merge(
        self, other: ComponentsLibrary, override: bool = True
    ) -> ComponentsLibrary:
        """Merges another ComponentsLibrary into this one.

        Component objects are shared, not copied: both libraries then reference
        the same instances.

        Args:
            other (ComponentsLibrary): Library whose components are merged in.
            override (bool): If True (default), duplicate names in `other`
                replace the existing entries; if False, existing entries win.

        Returns:
            ComponentsLibrary: This instance, updated in place.
        """
        for comp_name, comp_obj in other.components.items():
            if override or comp_name not in self.components:
                self.components[comp_name] = comp_obj
        return self

    def clone(self) -> ComponentsLibrary:
        """Creates a deep copy of this ComponentsLibrary.

        Returns:
            ComponentsLibrary: A new, cloned library instance.
        """
        return ComponentsLibrary(components=deepcopy(self.components))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ComponentsLibrary:
        """Constructs a ComponentsLibrary from raw component definitions.

        Args:
            data (Dict[str, Any]): Mapping of component name -> definition dict.

        Returns:
            ComponentsLibrary: A newly constructed library.
        """
        # Normalize dictionary keys to handle YAML boolean keys
        normalized_data = normalize_yaml_dict_keys(data)
        components_map: Dict[str, Component] = {}
        for comp_name, comp_def in normalized_data.items():
            components_map[comp_name] = cls._build_component(comp_name, comp_def)
        return ComponentsLibrary(components=components_map)

    @classmethod
    def _build_component(cls, name: str, definition_data: Dict[str, Any]) -> Component:
        """Recursively constructs a single Component from a dictionary definition.

        Args:
            name (str): Name to give the constructed component.
            definition_data (Dict[str, Any]): Component definition. Recognized
                keys map to fields; anything else is folded into ``attrs``.

        Returns:
            Component: The constructed Component instance.
        """
        comp_type = definition_data.get("component_type", "generic")
        capex = float(definition_data.get("capex", 0.0))
        power = float(definition_data.get("power_watts", 0.0))
        power_max = float(definition_data.get("power_watts_max", 0.0))
        capacity = float(definition_data.get("capacity", 0.0))
        ports = int(definition_data.get("ports", 0))
        count = int(definition_data.get("count", 1))

        child_definitions = definition_data.get("children", {})
        # Normalize child dictionary keys to handle YAML boolean keys
        normalized_children = normalize_yaml_dict_keys(child_definitions)
        children_map: Dict[str, Component] = {}
        for child_name, child_data in normalized_children.items():
            children_map[child_name] = cls._build_component(child_name, child_data)

        recognized_keys = {
            "component_type",
            "capex",
            "power_watts",
            "power_watts_max",
            "capacity",
            "ports",
            "children",
            "attrs",
            "count",
            "description",
        }
        attrs: Dict[str, Any] = dict(definition_data.get("attrs", {}))
        # Normalize attrs keys to handle YAML boolean keys
        attrs = normalize_yaml_dict_keys(attrs)
        leftover_keys = {
            k: v for k, v in definition_data.items() if k not in recognized_keys
        }
        # Normalize leftover keys too
        leftover_keys = normalize_yaml_dict_keys(leftover_keys)
        if "cost" in leftover_keys:
            # Likely confusion with link 'cost'; without 'capex' the component
            # contributes 0 to capex totals.
            LOGGER.warning(
                "Component '%s' defines unrecognized key 'cost'; it is stored "
                "in attrs and ignored by capex calculations. Use 'capex' for "
                "monetary cost.",
                name,
            )
        attrs.update(leftover_keys)

        return Component(
            name=name,
            component_type=comp_type,
            description=definition_data.get("description", ""),
            capex=capex,
            power_watts=power,
            power_watts_max=power_max,
            capacity=capacity,
            ports=ports,
            count=count,
            attrs=attrs,
            children=children_map,
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ComponentsLibrary:
        """Constructs a ComponentsLibrary from a YAML string. If the YAML contains
        a top-level 'components' key, that key is used; otherwise the entire
        top-level is treated as component definitions.

        Args:
            yaml_str (str): A YAML-formatted string of component definitions.

        Returns:
            ComponentsLibrary: A newly built components library.

        Raises:
            ValueError: If the top-level is not a dictionary or if the 'components'
                key is present but not a dictionary.
        """
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict):
            raise ValueError("Top-level must be a dict in Components YAML.")

        if "components" in data:
            # Presence-based dispatch: an explicit empty/null 'components'
            # mapping yields an empty library, not phantom components.
            components_data = data["components"] or {}
        else:
            components_data = data
        if not isinstance(components_data, dict):
            raise ValueError("'components' must be a dict if present.")

        return cls.from_dict(components_data)


# ----------------------------- Helper utilities -----------------------------
def resolve_node_hardware(
    attrs: Dict[str, Any], library: ComponentsLibrary
) -> Tuple[Optional[Component], float]:
    """Resolve node hardware from ``attrs['hardware']``.

    Expects the mapping: ``{"hardware": {"component": NAME, "count": N}}``.
    ``count`` defaults to 1 if missing or invalid. If ``component`` is missing
    or unknown, returns ``(None, 1.0)``.

    Args:
        attrs: Node attributes mapping.
        library: Component library used for lookups.

    Returns:
        Tuple of (component or None, positive multiplier).
    """
    hw = attrs.get("hardware")
    if not isinstance(hw, dict):
        return None, 1.0

    name_raw = hw.get("component")
    name = str(name_raw) if name_raw is not None else None
    raw_count = hw.get("count", 1)

    try:
        hw_count = float(raw_count)
    except Exception:
        hw_count = 1.0

    if hw_count <= 0:
        hw_count = 1.0

    comp = library.get(name) if name else None
    return comp, hw_count


def totals_with_multiplier(
    comp: Component, hw_count: float
) -> Tuple[float, float, float]:
    """Return (capex, power_watts, capacity) totals multiplied by ``hw_count``.

    Args:
        comp: Component definition (may include nested children and internal ``count``).
        hw_count: External multiplier (e.g., number of modules used for a link or node).

    Returns:
        Tuple of total capex, total power (typical), and total capacity as floats.
    """
    capex = comp.total_capex() * hw_count
    power = comp.total_power() * hw_count
    capacity = comp.total_capacity() * hw_count
    return capex, power, capacity


# ------------------------- Link endpoint HW helpers -------------------------
def _coerce_positive_float(value: Any, default: float = 1.0) -> float:
    """Return ``value`` coerced to a positive float, else ``default``.

    Args:
        value: Arbitrary value to parse as float.
        default: Returned when parsing fails or the result is <= 0.

    Returns:
        The parsed float when it is > 0, otherwise ``default`` (so the result
        is strictly positive only when ``default`` is).
    """
    try:
        out = float(value)
    except Exception:
        return default
    return out if out > 0 else default


def resolve_link_end_components(
    attrs: Dict[str, Any],
    library: ComponentsLibrary,
) -> tuple[
    tuple[Optional[Component], float, bool],
    tuple[Optional[Component], float, bool],
    bool,
]:
    """Resolve per-end hardware components for a link.

    Input format inside ``link.attrs`` is a structured mapping under the
    ``hardware`` key only:
      ``{"hardware": {"source": {"component": NAME, "count": N},
                       "target": {"component": NAME, "count": N}}}``
    An optional ``exclusive: true`` per end indicates unsharable usage; for
    exclusive ends, validation and BOM counting round counts up to integers.

    Args:
        attrs: Link attributes mapping.
        library: Components library for lookups.

    Returns:
        ((src_comp, src_count, src_exclusive), (dst_comp, dst_count, dst_exclusive), per_end_specified)
        where components may be ``None`` if name is absent/unknown. ``per_end_specified``
        is True when a structured per-end mapping is present.
    """

    def _from_mapping(
        mapping: Dict[str, Any],
    ) -> tuple[Optional[Component], float, bool]:
        comp_name = mapping.get("component")
        count_val = mapping.get("count", 1)
        exclusive = bool(mapping.get("exclusive", False))
        comp = library.get(str(comp_name)) if comp_name is not None else None
        return comp, _coerce_positive_float(count_val, 1.0), exclusive

    # 1) Structured under "hardware": {source: {...}, target: {...}}
    hw_struct = attrs.get("hardware")
    if isinstance(hw_struct, dict):
        src_map = hw_struct.get("source", {})
        dst_map = hw_struct.get("target", {})
        return _from_mapping(src_map), _from_mapping(dst_map), True

    # Only structured source/target format is supported.
    return (None, 1.0, False), (None, 1.0, False), False
