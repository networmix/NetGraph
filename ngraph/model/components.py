"""Component and ComponentsLibrary classes for hardware capex/power modeling."""

from __future__ import annotations

import math
import numbers
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

from ngraph.utils.values import (
    _shown,
    flag,
    frozen_attrs,
    integer,
    own,
    owned_dict,
    physical,
    text,
)
from ngraph.utils.yaml_load import _load_yaml
from ngraph.utils.yaml_utils import declared, normalize_yaml_dict_keys

_COUNT_LIMIT = int(sys.float_info.max) + int(math.ulp(sys.float_info.max)) // 2


@dataclass(frozen=True)
class Component:
    """Hardware component such as a chassis, line card, or optic.

    Components can nest children, each with its own capex, power, and count.

    Attributes:
        name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
        component_type (str): Free-form label (e.g., "chassis", "linecard", "optic").
        description (str): Free-form human-readable description.
        capex (float): Monetary capex of a single instance of this component.
        power_watts (float): Typical power usage (watts) for one instance.
        power_watts_max (float): Maximum/peak power usage (watts) for one instance.
        capacity (float): A generic capacity measure (e.g., platform capacity).
        ports (int): Number of ports if relevant for this component.
        count (int): How many identical copies of this component are present; a positive
            integer whose conversion to float is finite.
        attrs (Dict[str, Any]): Finite JSON metadata, checked and stored
            read-only at construction.
        children (Dict[str, Component]): Nested child components (e.g., line cards
            inside a chassis), keyed by child name; read-only.
    """

    name: str
    component_type: str = "generic"
    description: str = ""
    capex: float = 0.0

    power_watts: float = 0.0
    power_watts_max: float = 0.0

    capacity: float = 0.0
    ports: int = 0
    count: int = 1

    attrs: Dict[str, Any] = field(default_factory=dict)
    children: Dict[str, Component] = field(default_factory=dict)

    def __post_init__(self) -> None:
        name = text(self.name, "component.name")
        label = f"component {name}"
        if not _components(self.children):
            raise TypeError(
                f"{label}.children: expected Component values by name, got {self.children!r}"
            )
        own(
            self,
            name=name,
            component_type=text(
                self.component_type, f"{label}.component_type", empty=True
            ),
            description=text(self.description, f"{label}.description", empty=True),
            capex=physical(self.capex, f"{label}.capex"),
            power_watts=physical(self.power_watts, f"{label}.power_watts"),
            power_watts_max=physical(self.power_watts_max, f"{label}.power_watts_max"),
            capacity=physical(self.capacity, f"{label}.capacity"),
            ports=integer(self.ports, f"{label}.ports", minimum=0),
            count=integer(
                self.count,
                f"{label}.count",
                minimum=1,
                maximum=_COUNT_LIMIT,
            ),
            attrs=frozen_attrs(self.attrs, f"{label}.attrs"),
            children=owned_dict(self.children, f"{label}.children"),
        )

    def total_capex(self) -> float:
        """Return capex of this component and all descendants, times ``count``.

        Raises:
            ValueError: If the total exceeds the finite float range.
        """
        single_instance_capex = self.capex
        for child in self.children.values():
            single_instance_capex += child.total_capex()
        return physical(
            single_instance_capex * self.count, f"component {self.name}.capex"
        )

    def total_power(self) -> float:
        """Computes *typical* power for this component and all descendants.

        Returns:
            float: Typical power in watts, summed over children and multiplied
                by this component's ``count``.

        Raises:
            ValueError: If the total exceeds the finite float range.
        """
        single_instance_power = self.power_watts
        for child in self.children.values():
            single_instance_power += child.total_power()
        return physical(
            single_instance_power * self.count, f"component {self.name}.power_watts"
        )

    def total_power_max(self) -> float:
        """Computes *peak* power for this component and all descendants.

        Returns:
            float: Maximum (peak) power in watts, summed over children and
                multiplied by this component's ``count``.

        Raises:
            ValueError: If the total exceeds the finite float range.
        """
        single_instance_power_max = self.power_watts_max
        for child in self.children.values():
            single_instance_power_max += child.total_power_max()
        return physical(
            single_instance_power_max * self.count,
            f"component {self.name}.power_watts_max",
        )

    def total_capacity(self) -> float:
        """Computes capacity for this component and all descendants.

        Returns:
            float: Capacity summed over children and multiplied by this
                component's ``count``, in dimensionless or user-defined units.

        Raises:
            ValueError: If the total exceeds the finite float range.
        """
        single_instance_capacity = self.capacity
        for child in self.children.values():
            single_instance_capacity += child.total_capacity()
        return physical(
            single_instance_capacity * self.count, f"component {self.name}.capacity"
        )

    def as_dict(self, include_children: bool = True) -> Dict[str, Any]:
        """Returns a dictionary containing all properties of this component.

        Args:
            include_children (bool): If True, recursively includes children.

        Returns:
            Dict[str, Any]: One key per field, with ``attrs`` shallow-copied and
                a ``children`` key present only when ``include_children``.
        """
        include_children = flag(include_children, "Component.as_dict.include_children")
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
            "attrs": dict(self.attrs),
        }
        if include_children:
            data["children"] = {
                child_name: child.as_dict(True)
                for child_name, child in self.children.items()
            }
        return data


@dataclass(frozen=True)
class ComponentsLibrary:
    """Named Component templates for capex, power, and capacity lookups.

    Each entry is a top-level template and may have nested children. The
    ``components`` dict stays editable; ``prepare`` keeps a read-only view.

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

    def __post_init__(self) -> None:
        if not _components(self.components):
            raise TypeError(
                f"components: expected Component values by name, got {self.components!r}"
            )
        for key, component in self.components.items():
            text(key, "components key")
            if key != component.name:
                raise ValueError(
                    f"components.{key}: name/key disagreement, got {component.name!r}"
                )

    def snapshot(self) -> ComponentsLibrary:
        """Return a read-only view sharing this library's immutable components."""
        return ComponentsLibrary(owned_dict(self.components, "components"))

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
        override = flag(override, "ComponentsLibrary.merge.override")
        for comp_name, comp_obj in other.components.items():
            if override or comp_name not in self.components:
                self.components[comp_name] = comp_obj
        return self

    def clone(self) -> ComponentsLibrary:
        """Creates an independent copy of this ComponentsLibrary.

        Returns:
            ComponentsLibrary: Copy with its own dict; components are
                immutable and shared.
        """
        return ComponentsLibrary(components=dict(self.components))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ComponentsLibrary:
        """Constructs a ComponentsLibrary from raw component definitions.

        Args:
            data (Dict[str, Any]): Mapping of component name -> definition dict.

        Returns:
            ComponentsLibrary: A newly constructed library.

        Raises:
            ValueError: If a definition has an unrecognized key or a ``name``
                that disagrees with its mapping key.
        """
        # Normalize dictionary keys to handle YAML boolean keys
        if not isinstance(data, Mapping):
            raise ValueError(f"components: expected a mapping, got {_shown(data)}")
        normalized_data = normalize_yaml_dict_keys(data)
        components_map: Dict[str, Component] = {}
        for comp_name, comp_def in normalized_data.items():
            components_map[comp_name] = cls._build_component(comp_name, comp_def)
        return ComponentsLibrary(components=components_map)

    @classmethod
    def _build_component(
        cls, name: str, definition_data: Dict[str, Any], path: str | None = None
    ) -> Component:
        """Recursively constructs a single Component from a dictionary definition.

        Args:
            name (str): Name to give the constructed component.
            definition_data (Dict[str, Any]): Component definition; custom
                data belongs under ``attrs``.

        Returns:
            Component: The constructed Component instance.

        Raises:
            ValueError: If the definition has keys other than the component
                fields.
        """
        path = path or f"components.{name}"
        if not isinstance(definition_data, dict):
            raise ValueError(
                f"{path}: expected a mapping, got {_shown(definition_data)}"
            )
        comp_type = definition_data.get("component_type", "generic")
        capex = definition_data.get("capex", 0.0)
        power = definition_data.get("power_watts", 0.0)
        power_max = definition_data.get("power_watts_max", 0.0)
        capacity = definition_data.get("capacity", 0.0)
        ports = definition_data.get("ports", 0)
        count = definition_data.get("count", 1)

        child_definitions = definition_data.get("children", {})
        # Normalize child dictionary keys to handle YAML boolean keys
        if not isinstance(child_definitions, Mapping):
            raise ValueError(
                f"{path}.children: expected a mapping, got {_shown(child_definitions)}"
            )
        normalized_children = normalize_yaml_dict_keys(child_definitions)
        children_map: Dict[str, Component] = {}
        for child_name, child_data in normalized_children.items():
            children_map[child_name] = cls._build_component(
                child_name, child_data, f"{path}.children.{child_name}"
            )

        recognized_keys = {
            "name",
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
        # ``as_dict`` output carries the name; it must agree with the mapping key.
        if definition_data.get("name", name) != name:
            raise ValueError(
                f"{path}.name: mismatched name; expected {_shown(name)}, got {_shown(definition_data['name'])}"
            )
        unknown = sorted(str(k) for k in definition_data if k not in recognized_keys)
        if unknown:
            hint = " Use 'capex' for monetary cost." if "cost" in unknown else ""
            raise ValueError(
                f"{path} = {_shown(definition_data)}: unrecognized key(s): {', '.join(unknown)}. "
                f"Put custom data under 'attrs'.{hint}"
            )
        # Normalize attrs keys to handle YAML boolean keys
        attrs = definition_data.get("attrs", {})
        if isinstance(attrs, Mapping):
            attrs = normalize_yaml_dict_keys(attrs)

        return declared(
            path,
            lambda: Component(
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
            ),
            f"component {name}",
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ComponentsLibrary:
        """Constructs a ComponentsLibrary from a YAML string.

        If the YAML has a top-level 'components' key, its value is used;
        otherwise the whole top level is treated as component definitions.

        Args:
            yaml_str (str): A YAML-formatted string of component definitions.

        Returns:
            ComponentsLibrary: A newly built components library.

        Raises:
            ValueError: If the top-level is not a dictionary or if the 'components'
                key is present but not a dictionary.
        """
        data = _load_yaml(yaml_str, "components")
        if not isinstance(data, dict):
            raise ValueError(f"components = {_shown(data)}: expected a mapping")

        if "components" in data:
            # Presence-based dispatch: an explicit empty/null 'components'
            # mapping yields an empty library, not phantom components.
            components_data = {} if data["components"] is None else data["components"]
        else:
            components_data = data
        if not isinstance(components_data, dict):
            raise ValueError(
                f"components = {_shown(components_data)}: expected a mapping"
            )

        return cls.from_dict(components_data)


# ----------------------------- Helper utilities -----------------------------
def _positive_count(value: Any) -> float:
    """Return a hardware ``count`` as a finite positive float.

    Raises:
        ValueError: If ``value`` is not a finite number greater than zero,
            including an integer too large for a float.
    """
    try:
        count = (
            float(value)
            if isinstance(value, numbers.Real) and not isinstance(value, bool)
            else float("nan")
        )
    except OverflowError:
        count = float("inf")
    if not (count > 0 and math.isfinite(count)):
        text = repr(
            int(value)
            if isinstance(value, int) and not isinstance(value, bool)
            else value
        )
        raise ValueError(
            f"Hardware 'count' must be a finite positive number, got {text}"
        )
    return count


def _require_mapping(value: Any) -> Dict[str, Any]:
    """Return a ``hardware`` value that is a mapping.

    Raises:
        ValueError: If ``value`` is not a mapping.
    """
    if not isinstance(value, dict):
        raise ValueError(f"hardware must be a mapping, got {value!r}")
    return value


def resolve_node_hardware(
    attrs: Dict[str, Any], library: ComponentsLibrary
) -> Tuple[Optional[Component], float]:
    """Resolve node hardware from ``attrs['hardware']``.

    Expects the mapping: ``{"hardware": {"component": NAME, "count": N}}``.
    ``count`` defaults to 1. If ``component`` is missing or unknown, the
    component is None; an absent or null ``hardware`` has none.

    Args:
        attrs: Node attributes mapping.
        library: Component library used for lookups.

    Returns:
        Tuple of (component or None, positive multiplier).

    Raises:
        ValueError: If ``hardware`` is not a mapping or ``count`` is not a
            finite positive number.
    """
    hw = attrs.get("hardware")
    if hw is None:
        return None, 1.0

    name_raw = _require_mapping(hw).get("component")
    comp = library.get(str(name_raw)) if name_raw else None
    return comp, _positive_count(hw.get("count", 1))


def totals_with_multiplier(
    comp: Component, hw_count: float
) -> Tuple[float, float, float]:
    """Return (capex, power_watts, capacity) totals multiplied by ``hw_count``.

    Args:
        comp: Component definition (may include nested children and internal ``count``).
        hw_count: External multiplier (e.g., number of modules used for a link or node).

    Returns:
        Tuple of total capex, total power (typical), and total capacity as floats.

    Raises:
        ValueError: If a total exceeds the finite float range.
    """
    capex = physical(comp.total_capex() * hw_count, f"component {comp.name}.capex")
    power = physical(
        comp.total_power() * hw_count, f"component {comp.name}.power_watts"
    )
    capacity = physical(
        comp.total_capacity() * hw_count, f"component {comp.name}.capacity"
    )
    return capex, power, capacity


def resolve_link_end(
    spec: Dict[str, Any], library: ComponentsLibrary
) -> Tuple[Optional[Component], float, bool]:
    """Resolve one link end's hardware: ``{"component": NAME, "count": N}``.

    ``count`` defaults to 1. An optional ``exclusive: true`` marks unsharable
    use; the bill of materials rounds such an end's count up to an integer.

    Returns:
        (component or None when the name is absent or unknown, count, exclusive).

    Raises:
        ValueError: If ``spec`` is not a mapping, ``count`` is not a finite
            positive number, or ``exclusive`` is not a boolean.
    """
    comp_name = _require_mapping(spec).get("component")
    comp = library.get(str(comp_name)) if comp_name is not None else None
    return (
        comp,
        _positive_count(spec.get("count", 1)),
        flag(spec.get("exclusive", False), "hardware.exclusive"),
    )


def _components(values: object) -> bool:
    """Whether a value maps names to components."""
    return isinstance(values, Mapping) and all(
        isinstance(key, str) and isinstance(value, Component)
        for key, value in values.items()
    )
