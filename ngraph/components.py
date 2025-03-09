from __future__ import annotations

import yaml
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Dict, Any, Optional


@dataclass(slots=True)
class Component:
    """
    A generic component with a name, cost, power, and optional children.

    This can represent items such as chassis, line cards, optic modules, etc.

    Attributes:
        name (str): Name of the component (e.g., "SpineChassis" or "400G-LR4").
        component_type (str): An optional string label ("chassis", "linecard", "optic", etc.).
        cost (float): Base capex cost for the component.
        power_watts (float): Power consumption of the component in watts.
        ports (int): Number of ports if relevant for this component.
        children (Dict[str, Component]): Child components keyed by their names.
    """

    name: str
    component_type: str = "generic"
    cost: float = 0.0
    power_watts: float = 0.0
    ports: int = 0
    children: Dict[str, Component] = field(default_factory=dict)

    def total_cost(self) -> float:
        """
        Calculates the total cost including all nested children.

        Returns:
            float: Recursive sum of costs for this component and its children.
        """
        total = self.cost
        for child in self.children.values():
            total += child.total_cost()
        return total

    def total_power(self) -> float:
        """
        Calculates the total power consumption including all nested children.

        Returns:
            float: Recursive sum of power for this component and its children.
        """
        total = self.power_watts
        for child in self.children.values():
            total += child.total_power()
        return total


@dataclass(slots=True)
class ComponentsLibrary:
    """
    Holds a collection of named Components. Each entry is a top-level "template"
    that can be referenced for cost/power lookups, possibly with nested children.

    Example:
        components:
          BigSwitch:
            component_type: chassis
            cost: 20000
            power_watts: 1000
            children:
              LC-48x10G:
                component_type: linecard
                cost: 5000
                power_watts: 300
                ports: 48
          400G-LR4:
            component_type: optic
            cost: 2000
            power_watts: 15

    Attributes:
        components (Dict[str, Component]): A dictionary of component name -> Component.
    """

    components: Dict[str, Component] = field(default_factory=dict)

    def get(self, name: str) -> Optional[Component]:
        """
        Retrieves a Component by its name.

        Args:
            name (str): Name of the component.

        Returns:
            Optional[Component]: The requested Component or None if not found.
        """
        return self.components.get(name)

    def merge(
        self, other: ComponentsLibrary, override: bool = True
    ) -> ComponentsLibrary:
        """
        Merges another ComponentsLibrary into this one. By default (override=True),
        duplicate components in `other` overwrite those in the current library.

        Args:
            other (ComponentsLibrary): Another library to merge into this one.
            override (bool): Whether components in `other` override existing ones.

        Returns:
            ComponentsLibrary: This instance, updated in place.
        """
        for comp_name, comp_obj in other.components.items():
            if override or comp_name not in self.components:
                self.components[comp_name] = comp_obj
        return self

    def clone(self) -> ComponentsLibrary:
        """
        Creates a deep copy of this ComponentsLibrary.

        Returns:
            ComponentsLibrary: A new, cloned library instance.
        """
        return ComponentsLibrary(components=deepcopy(self.components))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ComponentsLibrary:
        """
        Constructs a ComponentsLibrary from a dictionary of raw component definitions.

        Args:
            data (Dict[str, Any]): Raw component definitions.

        Returns:
            ComponentsLibrary: A newly constructed library.
        """
        components_map: Dict[str, Component] = {}
        for comp_name, comp_def in data.items():
            components_map[comp_name] = cls._build_component(comp_name, comp_def)
        return cls(components=components_map)

    @classmethod
    def _build_component(cls, name: str, definition_data: Dict[str, Any]) -> Component:
        """
        Recursively constructs a single Component from a dictionary definition.

        Args:
            name (str): Name of the component.
            definition_data (Dict[str, Any]): Dictionary data for the component definition.

        Returns:
            Component: The constructed Component instance.
        """
        comp_type = definition_data.get("component_type", "generic")
        cost = float(definition_data.get("cost", 0.0))
        power = float(definition_data.get("power_watts", 0.0))
        ports = int(definition_data.get("ports", 0))

        children_map: Dict[str, Component] = {}
        child_definitions = definition_data.get("children", {})
        for child_name, child_data in child_definitions.items():
            children_map[child_name] = cls._build_component(child_name, child_data)

        return Component(
            name=name,
            component_type=comp_type,
            cost=cost,
            power_watts=power,
            ports=ports,
            children=children_map,
        )

    @classmethod
    def from_yaml(cls, yaml_str: str) -> ComponentsLibrary:
        """
        Constructs a ComponentsLibrary from a YAML string. If the YAML contains
        a top-level 'components' key, that key is used; otherwise the entire
        top-level of the YAML is treated as component definitions.

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

        components_data = data.get("components") or data
        if not isinstance(components_data, dict):
            raise ValueError("'components' must be a dict if present.")

        return cls.from_dict(components_data)
