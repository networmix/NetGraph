import pytest

from ngraph.components import Component, ComponentsLibrary


def test_component_totals_with_count_and_children() -> None:
    """Total metrics include children and respect count multiplicity.

    Build a small tree with counts and verify cost, power (typical and max),
    and capacity accumulation across the hierarchy.
    """
    child_a = Component(
        name="ChildA",
        capex=10.0,
        power_watts=2.0,
        power_watts_max=3.0,
        capacity=5.0,
        count=3,
    )
    child_b = Component(
        name="ChildB",
        capex=4.0,
        power_watts=1.0,
        power_watts_max=1.5,
        capacity=2.0,
        count=1,
    )
    parent = Component(
        name="Parent",
        capex=20.0,
        power_watts=5.0,
        power_watts_max=7.0,
        capacity=11.0,
        count=2,
        children={"A": child_a, "B": child_b},
    )

    # Single-instance child totals
    child_a_cost = 10.0 * 3
    child_a_power = 2.0 * 3
    child_a_power_max = 3.0 * 3
    child_a_capacity = 5.0 * 3

    child_b_cost = 4.0 * 1
    child_b_power = 1.0 * 1
    child_b_power_max = 1.5 * 1
    child_b_capacity = 2.0 * 1

    # Single-instance parent aggregate (without parent count)
    agg_cost = 20.0 + child_a_cost + child_b_cost
    agg_power = 5.0 + child_a_power + child_b_power
    agg_power_max = 7.0 + child_a_power_max + child_b_power_max
    agg_capacity = 11.0 + child_a_capacity + child_b_capacity

    # Apply parent count multiplicity
    assert parent.total_capex() == agg_cost * 2
    assert parent.total_power() == agg_power * 2
    assert parent.total_power_max() == agg_power_max * 2
    assert parent.total_capacity() == agg_capacity * 2


def test_component_total_cost_and_power_no_children() -> None:
    """
    Test total_cost and total_power with no child components.
    """
    comp = Component(name="Solo", capex=200.0, power_watts=10.0)
    assert comp.total_capex() == 200.0
    assert comp.total_power() == 10.0


def test_component_total_cost_and_power_with_children() -> None:
    """
    Test total_cost and total_power with nested child components.
    """
    child1 = Component(name="Child1", capex=50.0, power_watts=5.0)
    child2 = Component(name="Child2", capex=20.0, power_watts=2.0)
    parent = Component(
        name="Parent",
        capex=100.0,
        power_watts=10.0,
        children={"Child1": child1, "Child2": child2},
    )

    assert parent.total_capex() == 100.0 + 50.0 + 20.0
    assert parent.total_power() == 10.0 + 5.0 + 2.0


def test_component_as_dict() -> None:
    """
    Test that as_dict returns a dictionary with correct fields,
    and that we can exclude child data if desired.
    """
    child = Component(name="Child", capex=10.0)
    parent = Component(
        name="Parent",
        capex=100.0,
        power_watts=25.0,
        children={"Child": child},
        attrs={"location": "rack1"},
    )

    # Include children
    parent_dict_incl = parent.as_dict(include_children=True)
    assert parent_dict_incl["name"] == "Parent"
    assert parent_dict_incl["capex"] == 100.0
    assert parent_dict_incl["power_watts"] == 25.0
    assert parent_dict_incl["attrs"]["location"] == "rack1"
    assert "children" in parent_dict_incl
    assert len(parent_dict_incl["children"]) == 1
    assert parent_dict_incl["children"]["Child"]["name"] == "Child"
    assert parent_dict_incl["children"]["Child"]["capex"] == 10.0

    # Exclude children
    parent_dict_excl = parent.as_dict(include_children=False)
    assert parent_dict_excl["name"] == "Parent"
    assert "children" not in parent_dict_excl


def test_components_library_from_yaml_attrs_and_leftovers() -> None:
    """Unknown component fields are merged into attrs; YAML path covered."""
    yaml_str = """
components:
  Mod:
    component_type: module
    cost: 3
    attrs:
      vendor: acme
    custom_field: value
    """
    lib = ComponentsLibrary.from_yaml(yaml_str)
    comp = lib.get("Mod")
    assert comp is not None
    assert comp.attrs["vendor"] == "acme"
    assert comp.attrs["custom_field"] == "value"


def test_components_library_merge_override_true() -> None:
    """
    Test merging two libraries with override=True.
    Components with duplicate names in 'other' should overwrite the original.
    """
    original_comp = Component("Overlap", capex=100.0)
    lib1 = ComponentsLibrary(
        components={
            "Overlap": original_comp,
            "UniqueLib1": Component("UniqueLib1", capex=50.0),
        }
    )

    new_comp = Component("Overlap", capex=200.0)
    lib2 = ComponentsLibrary(
        components={
            "Overlap": new_comp,
            "UniqueLib2": Component("UniqueLib2", capex=75.0),
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
    original_comp = Component("Overlap", capex=100.0)
    lib1 = ComponentsLibrary(
        components={
            "Overlap": original_comp,
            "UniqueLib1": Component("UniqueLib1", capex=50.0),
        }
    )

    new_comp = Component("Overlap", capex=200.0)
    lib2 = ComponentsLibrary(
        components={
            "Overlap": new_comp,
            "UniqueLib2": Component("UniqueLib2", capex=75.0),
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
    comp_a = Component("CompA", capex=10.0)
    comp_b = Component("CompB", capex=20.0)
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
            "capex": 20000,
            "power_watts": 1000,
            "children": {
                "LC-48x10G": {
                    "component_type": "linecard",
                    "capex": 5000,
                    "power_watts": 300,
                    "ports": 48,
                }
            },
        },
        "400G-LR4": {"component_type": "optic", "capex": 2000, "power_watts": 10},
    }

    lib = ComponentsLibrary.from_dict(data)
    assert "BigSwitch" in lib.components
    assert "400G-LR4" in lib.components

    big_switch = lib.get("BigSwitch")
    assert big_switch is not None
    assert big_switch.component_type == "chassis"
    assert big_switch.total_capex() == 20000 + 5000
    assert big_switch.total_power() == 1000 + 300
    assert "LC-48x10G" in big_switch.children

    optic = lib.get("400G-LR4")
    assert optic is not None
    assert optic.component_type == "optic"
    assert optic.capex == 2000
    assert optic.power_watts == 10


def test_components_library_from_yaml_valid() -> None:
    """
    Test building a ComponentsLibrary from a valid YAML string.
    """
    yaml_str = """
components:
  MyChassis:
    component_type: chassis
    capex: 5000
    power_watts: 300
  MyOptic:
    component_type: optic
    capex: 200
    power_watts: 5
    """
    lib = ComponentsLibrary.from_yaml(yaml_str)
    assert lib.get("MyChassis") is not None
    assert lib.get("MyOptic") is not None
    chassis = lib.get("MyChassis")
    optic = lib.get("MyOptic")
    assert chassis and chassis.capex == 5000
    assert chassis.power_watts == 300
    assert optic and optic.capex == 200
    assert optic.power_watts == 5


def test_components_library_from_yaml_no_components_key() -> None:
    """
    Test that from_yaml() can parse top-level YAML data without
    a 'components' key.
    """
    yaml_str = """
MyChassis:
  component_type: chassis
  capex: 4000
  power_watts: 250
"""
    lib = ComponentsLibrary.from_yaml(yaml_str)
    chassis = lib.get("MyChassis")
    assert chassis is not None
    assert chassis.capex == 4000
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


def test_components_library_yaml_boolean_keys():
    """Test that YAML boolean keys are converted to string representations for component names."""
    yaml_str = """
components:
  # Regular string key
  MyChassis:
    component_type: chassis
    capex: 1000
    power_watts: 100

  # YAML 1.1 boolean keys - these get parsed as Python booleans
  true:
    component_type: optic
    capex: 200
    power_watts: 5
  false:
    component_type: linecard
    capex: 500
    power_watts: 25
  yes:
    component_type: switch
    capex: 800
    power_watts: 40
  no:
    component_type: router
    capex: 1200
    power_watts: 60
  on:
    component_type: module
    capex: 300
    power_watts: 15
  off:
    component_type: port
    capex: 150
    power_watts: 8
"""

    lib = ComponentsLibrary.from_yaml(yaml_str)

    # All YAML boolean values collapse to just True/False, then converted to strings
    component_names = set(lib.components.keys())
    assert component_names == {"MyChassis", "True", "False"}

    # Regular string key
    my_chassis = lib.get("MyChassis")
    assert my_chassis is not None
    assert my_chassis.capex == 1000

    # All true-like YAML values become "True" component (last one wins)
    # NOTE: When multiple YAML keys collapse to the same boolean value,
    # only the last one wins (standard YAML/dict behavior)
    true_comp = lib.get("True")
    assert true_comp is not None
    assert true_comp.component_type == "module"  # from 'on:', the last true-like key
    assert true_comp.capex == 300

    # All false-like YAML values become "False" component (last one wins)
    false_comp = lib.get("False")
    assert false_comp is not None
    assert false_comp.component_type == "port"  # from 'off:', the last false-like key
    assert false_comp.capex == 150


def test_components_library_yaml_boolean_child_keys():
    """Test that YAML boolean keys in child components are handled correctly."""
    yaml_str = """
components:
  ParentChassis:
    component_type: chassis
    capex: 2000
    power_watts: 200
    children:
      LineCard1:
        component_type: linecard
        capex: 500
        power_watts: 25
      true:
        component_type: optic
        capex: 100
        power_watts: 5
      false:
        component_type: module
        capex: 200
        power_watts: 10
      yes:
        component_type: switch
        capex: 150
        power_watts: 8
      no:
        component_type: port
        capex: 75
        power_watts: 3
"""

    lib = ComponentsLibrary.from_yaml(yaml_str)
    parent = lib.get("ParentChassis")
    assert parent is not None

    # Child component names should be converted too
    child_names = set(parent.children.keys())
    assert child_names == {"LineCard1", "True", "False"}

    # Regular string child key
    assert parent.children["LineCard1"].capex == 500

    # Boolean child keys converted to strings
    true_child = parent.children["True"]
    assert true_child.component_type == "switch"  # from 'yes:', the last true-like key
    assert true_child.capex == 150

    false_child = parent.children["False"]
    assert false_child.component_type == "port"  # from 'no:', the last false-like key
    assert false_child.capex == 75


def test_helper_resolve_and_totals_with_multiplier() -> None:
    """Helpers return component and apply hw_count multiplier correctly."""
    from ngraph.components import resolve_hw_component, totals_with_multiplier

    lib = ComponentsLibrary()
    lib.components["box"] = Component(
        name="box", capex=5.0, power_watts=2.0, capacity=10.0
    )
    attrs = {"hw_component": "box", "hw_count": 3}
    comp, count = resolve_hw_component(attrs, lib)
    assert comp is not None and comp.name == "box"
    assert count == 3
    capex, power, capacity = totals_with_multiplier(comp, count)
    assert capex == 15.0
    assert power == 6.0
    assert capacity == 30.0
