import pytest
from copy import deepcopy
from typing import Dict

from ngraph.components import Component, ComponentsLibrary


def test_component_creation() -> None:
    """
    Test that a Component can be created with the correct attributes.
    """
    comp = Component(
        name="TestComp",
        component_type="linecard",
        cost=100.0,
        power_watts=50.0,
        ports=24,
    )
    assert comp.name == "TestComp"
    assert comp.component_type == "linecard"
    assert comp.cost == 100.0
    assert comp.power_watts == 50.0
    assert comp.ports == 24
    assert comp.children == {}


def test_component_total_cost_and_power_no_children() -> None:
    """
    Test total_cost and total_power with no child components.
    """
    comp = Component(name="Solo", cost=200.0, power_watts=10.0)
    assert comp.total_cost() == 200.0
    assert comp.total_power() == 10.0


def test_component_total_cost_and_power_with_children() -> None:
    """
    Test total_cost and total_power with nested child components.
    """
    child1 = Component(name="Child1", cost=50.0, power_watts=5.0)
    child2 = Component(name="Child2", cost=20.0, power_watts=2.0)
    parent = Component(
        name="Parent",
        cost=100.0,
        power_watts=10.0,
        children={"Child1": child1, "Child2": child2},
    )

    assert parent.total_cost() == 100.0 + 50.0 + 20.0
    assert parent.total_power() == 10.0 + 5.0 + 2.0


def test_component_as_dict() -> None:
    """
    Test that as_dict returns a dictionary with correct fields,
    and that we can exclude child data if desired.
    """
    child = Component(name="Child", cost=10.0)
    parent = Component(
        name="Parent",
        cost=100.0,
        power_watts=25.0,
        children={"Child": child},
        attrs={"location": "rack1"},
    )

    # Include children
    parent_dict_incl = parent.as_dict(include_children=True)
    assert parent_dict_incl["name"] == "Parent"
    assert parent_dict_incl["cost"] == 100.0
    assert parent_dict_incl["power_watts"] == 25.0
    assert parent_dict_incl["attrs"]["location"] == "rack1"
    assert "children" in parent_dict_incl
    assert len(parent_dict_incl["children"]) == 1
    assert parent_dict_incl["children"]["Child"]["name"] == "Child"
    assert parent_dict_incl["children"]["Child"]["cost"] == 10.0

    # Exclude children
    parent_dict_excl = parent.as_dict(include_children=False)
    assert parent_dict_excl["name"] == "Parent"
    assert "children" not in parent_dict_excl


def test_components_library_empty() -> None:
    """
    Test initializing an empty ComponentsLibrary.
    """
    lib = ComponentsLibrary()
    assert isinstance(lib.components, dict)
    assert len(lib.components) == 0


def test_components_library_get() -> None:
    """
    Test that retrieving a component by name returns the correct component,
    or None if not found.
    """
    comp_a = Component("CompA", cost=10.0)
    comp_b = Component("CompB", cost=20.0)
    lib = ComponentsLibrary(components={"CompA": comp_a, "CompB": comp_b})

    assert lib.get("CompA") is comp_a
    assert lib.get("CompB") is comp_b
    assert lib.get("Missing") is None


def test_components_library_merge_override_true() -> None:
    """
    Test merging two libraries with override=True.
    Components with duplicate names in 'other' should overwrite the original.
    """
    original_comp = Component("Overlap", cost=100.0)
    lib1 = ComponentsLibrary(
        components={
            "Overlap": original_comp,
            "UniqueLib1": Component("UniqueLib1", cost=50.0),
        }
    )

    new_comp = Component("Overlap", cost=200.0)
    lib2 = ComponentsLibrary(
        components={
            "Overlap": new_comp,
            "UniqueLib2": Component("UniqueLib2", cost=75.0),
        }
    )

    lib1.merge(lib2, override=True)
    # The "Overlap" component should now be the one from lib2 (cost=200).
    assert lib1.get("Overlap") is new_comp
    # The new library should also include the previously missing component.
    assert "UniqueLib2" in lib1.components
    # The old unique component remains.
    assert "UniqueLib1" in lib1.components


def test_components_library_merge_override_false() -> None:
    """
    Test merging two libraries with override=False.
    Original components should remain in case of a name clash.
    """
    original_comp = Component("Overlap", cost=100.0)
    lib1 = ComponentsLibrary(
        components={
            "Overlap": original_comp,
            "UniqueLib1": Component("UniqueLib1", cost=50.0),
        }
    )

    new_comp = Component("Overlap", cost=200.0)
    lib2 = ComponentsLibrary(
        components={
            "Overlap": new_comp,
            "UniqueLib2": Component("UniqueLib2", cost=75.0),
        }
    )

    lib1.merge(lib2, override=False)
    # The "Overlap" component should remain the original_comp (cost=100).
    assert lib1.get("Overlap") is original_comp
    # The new library should also include the previously missing component.
    assert "UniqueLib2" in lib1.components


def test_components_library_clone() -> None:
    """
    Test that clone() creates a deep copy of the library.
    """
    comp_a = Component("CompA", cost=10.0)
    comp_b = Component("CompB", cost=20.0)
    original = ComponentsLibrary(components={"CompA": comp_a, "CompB": comp_b})
    clone_lib = original.clone()

    assert clone_lib is not original
    assert clone_lib.components is not original.components
    # The components should be deep-copied, meaning not the same references
    assert clone_lib.get("CompA") is not original.get("CompA")
    assert clone_lib.get("CompB") is not original.get("CompB")


def test_components_library_from_dict() -> None:
    """
    Test building a ComponentsLibrary from a dictionary structure,
    including nested child components.
    """
    data = {
        "BigSwitch": {
            "component_type": "chassis",
            "cost": 20000,
            "power_watts": 1000,
            "children": {
                "LC-48x10G": {
                    "component_type": "linecard",
                    "cost": 5000,
                    "power_watts": 300,
                    "ports": 48,
                }
            },
        },
        "400G-LR4": {"component_type": "optic", "cost": 2000, "power_watts": 10},
    }

    lib = ComponentsLibrary.from_dict(data)
    assert "BigSwitch" in lib.components
    assert "400G-LR4" in lib.components

    big_switch = lib.get("BigSwitch")
    assert big_switch is not None
    assert big_switch.component_type == "chassis"
    assert big_switch.total_cost() == 20000 + 5000
    assert big_switch.total_power() == 1000 + 300
    assert "LC-48x10G" in big_switch.children

    optic = lib.get("400G-LR4")
    assert optic is not None
    assert optic.component_type == "optic"
    assert optic.cost == 2000
    assert optic.power_watts == 10


def test_components_library_from_yaml_valid() -> None:
    """
    Test building a ComponentsLibrary from a valid YAML string.
    """
    yaml_str = """
components:
  MyChassis:
    component_type: chassis
    cost: 5000
    power_watts: 300
  MyOptic:
    component_type: optic
    cost: 200
    power_watts: 5
    """
    lib = ComponentsLibrary.from_yaml(yaml_str)
    assert lib.get("MyChassis") is not None
    assert lib.get("MyOptic") is not None
    chassis = lib.get("MyChassis")
    optic = lib.get("MyOptic")
    assert chassis and chassis.cost == 5000
    assert chassis.power_watts == 300
    assert optic and optic.cost == 200
    assert optic.power_watts == 5


def test_components_library_from_yaml_no_components_key() -> None:
    """
    Test that from_yaml() can parse top-level YAML data without
    a 'components' key.
    """
    yaml_str = """
MyChassis:
  component_type: chassis
  cost: 4000
  power_watts: 250
"""
    lib = ComponentsLibrary.from_yaml(yaml_str)
    chassis = lib.get("MyChassis")
    assert chassis is not None
    assert chassis.cost == 4000
    assert chassis.power_watts == 250


def test_components_library_from_yaml_invalid_top_level() -> None:
    """
    Test that from_yaml() raises an error if the top-level is not a dict.
    """
    yaml_str = """
- name: NotADict
  cost: 100
"""
    with pytest.raises(ValueError) as exc:
        _ = ComponentsLibrary.from_yaml(yaml_str)
    assert "Top-level must be a dict" in str(exc.value)


def test_components_library_from_yaml_invalid_components_type() -> None:
    """
    Test that from_yaml() raises an error if 'components' is present
    but is not a dict.
    """
    yaml_str = """
components:
  - NotAValidDict: 1
"""
    with pytest.raises(ValueError) as exc:
        _ = ComponentsLibrary.from_yaml(yaml_str)
    assert "'components' must be a dict if present." in str(exc.value)
