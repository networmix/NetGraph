"""Guards for non-string values leaking out of native-type variable substitution.

Whole-string ``${var}`` placeholders substitute the variable's native type
(so match conditions compare correctly against numeric attrs). String-only
positions must reject non-string values with a clear ValueError instead of
crashing later with a context-free TypeError.
"""

import pytest

from ngraph.dsl.blueprints.expand import expand_network_dsl
from ngraph.dsl.expansion.brackets import expand_risk_group_refs
from ngraph.dsl.selectors import normalize_selector
from ngraph.model.demand.builder import build_demand_set
from ngraph.model.selectors import NodeSelector


class TestSelectorPathGuard:
    """Selector 'path' must be a string."""

    def test_node_selector_rejects_non_string_path(self):
        with pytest.raises(ValueError, match="Selector 'path' must be a string"):
            NodeSelector(path=1)  # type: ignore[arg-type]

    def test_normalize_selector_dict_rejects_non_string_path(self):
        with pytest.raises(ValueError, match="Selector 'path' must be a string"):
            normalize_selector({"path": 1}, "demand")

    def test_node_rule_native_var_path_raises_value_error(self):
        """A bare placeholder bound to an int var fails loudly, not TypeError."""
        data = {
            "nodes": {"A": {}},
            "node_rules": [
                {
                    "path": "${p}",
                    "attrs": {"tier": 1},
                    "expand": {"vars": {"p": [1, 2]}},
                }
            ],
        }
        with pytest.raises(ValueError, match="Selector 'path' must be a string"):
            expand_network_dsl({"network": data})


class TestRiskGroupRefGuard:
    """Risk group references must be strings."""

    def test_non_string_ref_rejected(self):
        with pytest.raises(ValueError, match="Risk group reference must be a string"):
            expand_risk_group_refs(["RG1", 1])  # type: ignore[list-item]

    def test_native_var_risk_group_raises_value_error(self):
        """An int-typed var in a link risk_groups list fails loudly."""
        data = {
            "nodes": {"A": {}, "B": {}},
            "links": [
                {
                    "source": "A",
                    "target": "B",
                    "risk_groups": ["${rg}"],
                    "expand": {"vars": {"rg": [1]}},
                }
            ],
        }
        with pytest.raises(ValueError, match="Risk group reference must be a string"):
            expand_network_dsl({"network": data})


class TestDemandSourceTargetGuard:
    """Demand source/target must be a string or selector dict at build time."""

    def test_int_source_rejected_with_set_context(self):
        with pytest.raises(
            ValueError, match="Demand 'source' in set 'tm' must be a string"
        ):
            build_demand_set({"tm": [{"source": 1, "target": "^B$"}]})

    def test_native_var_source_rejected_at_build(self):
        """Expansion substituting an int source fails at build, not analysis."""
        demands = {
            "tm": [
                {
                    "source": "${s}",
                    "target": "^B$",
                    "volume": 1.0,
                    "expand": {"vars": {"s": [1]}},
                }
            ]
        }
        with pytest.raises(
            ValueError, match="Demand 'source' in set 'tm' must be a string"
        ):
            build_demand_set(demands)
