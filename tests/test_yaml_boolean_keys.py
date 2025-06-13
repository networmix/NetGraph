"""Test YAML boolean key handling - both utility functions and integration tests."""

import textwrap

from ngraph.scenario import Scenario
from ngraph.yaml_utils import normalize_yaml_dict_keys

# =============================================================================
# Unit Tests for normalize_yaml_dict_keys utility function
# =============================================================================


def test_normalize_yaml_dict_keys_boolean_keys():
    """Test that boolean keys are converted to string representations."""
    input_dict = {
        True: "true_value",
        False: "false_value",
        "normal_key": "normal_value",
        123: "numeric_key",
    }

    result = normalize_yaml_dict_keys(input_dict)

    expected = {
        "True": "true_value",
        "False": "false_value",
        "normal_key": "normal_value",
        "123": "numeric_key",
    }

    assert result == expected


def test_normalize_yaml_dict_keys_all_strings():
    """Test that dictionary with all string keys is unchanged."""
    input_dict = {
        "key1": "value1",
        "key2": "value2",
        "key3": "value3",
    }

    result = normalize_yaml_dict_keys(input_dict)

    assert result == input_dict


def test_normalize_yaml_dict_keys_empty_dict():
    """Test that empty dictionary is handled correctly."""
    result = normalize_yaml_dict_keys({})
    assert result == {}


def test_normalize_yaml_dict_keys_preserves_values():
    """Test that values are preserved exactly as they are."""
    input_dict = {
        True: {"nested": "dict"},
        False: [1, 2, 3],
        "string_key": None,
        42: True,  # Value is boolean but key gets normalized
    }

    result = normalize_yaml_dict_keys(input_dict)

    expected = {
        "True": {"nested": "dict"},
        "False": [1, 2, 3],
        "string_key": None,
        "42": True,
    }

    assert result == expected


# =============================================================================
# Integration Tests for traffic_matrix_set boolean key handling
# =============================================================================


def test_yaml_boolean_keys_converted_to_strings():
    """Test that YAML boolean keys are converted to string representations.

    Per YAML 1.1 spec, keys like 'true', 'false', 'yes', 'no', 'on', 'off'
    are parsed as Python boolean values, which need to be converted back to strings.
    """
    yml = textwrap.dedent("""
    network:
      name: test
    traffic_matrix_set:
      # Regular string key
      peak:
        - source_path: "^A$"
          sink_path: "^B$"
          demand: 100

      # YAML 1.1 boolean keys - these get parsed as Python booleans
      true:
        - source_path: "^C$"
          sink_path: "^D$"
          demand: 200
      false:
        - source_path: "^E$"
          sink_path: "^F$"
          demand: 50
      yes:
        - source_path: "^G$"
          sink_path: "^H$"
          demand: 25
      no:
        - source_path: "^I$"
          sink_path: "^J$"
          demand: 75
      on:
        - source_path: "^K$"
          sink_path: "^L$"
          demand: 150
      off:
        - source_path: "^M$"
          sink_path: "^N$"
          demand: 125
    """)

    scenario = Scenario.from_yaml(yml)
    matrices = scenario.traffic_matrix_set.matrices

    # All YAML boolean values collapse to just True/False, then converted to strings
    assert set(matrices.keys()) == {"peak", "True", "False"}

    # Regular string key
    assert matrices["peak"][0].demand == 100

    # All true-like YAML values become "True" matrix
    # NOTE: When multiple YAML keys collapse to the same boolean value,
    # only the last one wins (standard YAML/dict behavior)
    true_demands = {d.demand for d in matrices["True"]}
    assert true_demands == {150}  # from 'on:', the last true-like key

    # All false-like YAML values become "False" matrix
    false_demands = {d.demand for d in matrices["False"]}
    assert false_demands == {125}  # from 'off:', the last false-like key


def test_quoted_boolean_keys_remain_strings():
    """Test that quoted boolean-like keys remain as strings."""
    yml = textwrap.dedent("""
    network:
      name: test
    traffic_matrix_set:
      "true":
        - source_path: "^A$"
          sink_path: "^B$"
          demand: 100
      "false":
        - source_path: "^C$"
          sink_path: "^D$"
          demand: 200
      "off":
        - source_path: "^E$"
          sink_path: "^F$"
          demand: 300
    """)

    scenario = Scenario.from_yaml(yml)
    matrices = scenario.traffic_matrix_set.matrices

    # Quoted keys should remain as strings, not be converted to booleans
    assert set(matrices.keys()) == {"true", "false", "off"}
    assert matrices["true"][0].demand == 100
    assert matrices["false"][0].demand == 200
    assert matrices["off"][0].demand == 300
