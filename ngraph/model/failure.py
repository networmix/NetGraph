"""Failure declarations and one YAML construction path."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from ngraph.model.selectors import Condition, EntityScope, parse_match_spec
from ngraph.utils.seed_manager import SeedManager
from ngraph.utils.values import (
    collection,
    flag,
    frozen_attrs,
    integer,
    optional_integer,
    optional_pattern,
    optional_text,
    own,
    physical,
)
from ngraph.utils.yaml_utils import (
    check_no_extra_keys,
    declared,
    normalize_yaml_dict_keys,
)


@dataclass(frozen=True)
class FailureRule:
    """One failure rule: the entities it matches, and how it fails them: all, ``count``
    chosen at random, or each with ``probability``.
    """

    scope: EntityScope
    conditions: Sequence[Condition] = ()
    logic: Literal["and", "or"] = "or"
    mode: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1
    weight_by: str | None = None
    path: str | None = None

    def __post_init__(self) -> None:
        for name, allowed in (
            ("scope", ("node", "link", "risk_group")),
            ("logic", ("and", "or")),
            ("mode", ("all", "random", "choice")),
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(
                    f"failure rule {name}: expected {', '.join(allowed)}, got {value!r}"
                )
        probability = physical(self.probability, "failure rule probability")
        if probability > 1:
            raise ValueError(
                f"failure rule probability: expected [0,1], got {self.probability!r}"
            )
        conditions = collection(self.conditions, "failure rule conditions")
        if not all(isinstance(condition, Condition) for condition in conditions):
            raise TypeError(
                f"failure rule conditions: expected Condition values, got {self.conditions!r}"
            )
        own(
            self,
            scope=str.__str__(self.scope),
            logic=str.__str__(self.logic),
            mode=str.__str__(self.mode),
            probability=probability,
            count=integer(self.count, "failure rule count", minimum=1),
            weight_by=optional_text(self.weight_by, "failure rule weight_by"),
            # An empty path matches every name, as a selector's does.
            path=optional_pattern(self.path, "failure rule path", empty=True),
            conditions=conditions,
        )


@dataclass(frozen=True)
class FailureMode:
    """One weighted alternative of a failure policy: a draw picks one mode by weight,
    then applies its rules.
    """

    weight: float
    rules: Sequence[FailureRule] = ()
    attrs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "weight", physical(self.weight, "failure mode weight"))
        rules = collection(self.rules, "failure mode rules")
        if not all(isinstance(rule, FailureRule) for rule in rules):
            raise TypeError(
                f"failure mode rules: expected FailureRule values, got {self.rules!r}"
            )
        object.__setattr__(self, "rules", rules)
        object.__setattr__(
            self, "attrs", frozen_attrs(self.attrs, "failure mode attrs")
        )


@dataclass(frozen=True)
class FailurePolicy:
    """Failure modes drawn by weight; at least one mode has a positive weight.

    "No failures" is no policy, not an empty one.
    """

    attrs: dict[str, Any] = field(default_factory=dict)
    expand_groups: bool = False
    seed: int | None = None
    modes: Sequence[FailureMode] = field(kw_only=True)

    def __post_init__(self) -> None:
        modes = collection(self.modes, "failure policy modes")
        if not all(isinstance(mode, FailureMode) for mode in modes):
            raise TypeError(
                f"failure policy modes: expected FailureMode values, got {self.modes!r}"
            )
        if not any(mode.weight > 0 for mode in modes):
            raise ValueError(
                "failure policy modes: at least one mode must have positive weight"
            )
        own(
            self,
            expand_groups=flag(self.expand_groups, "failure policy expand_groups"),
            seed=optional_integer(self.seed, "failure policy seed", minimum=None),
            modes=modes,
            attrs=frozen_attrs(self.attrs, "failure policy attrs"),
        )


def build_failure_policies(
    raw: dict[str, Any], master_seed: int | None
) -> dict[str, FailurePolicy]:
    """Construct named policies; seeded YAML keeps the established composed hash.

    Policy name ``n`` uses SHA256("<master>:failure_policy:failure_policy:<n>"),
    first four bytes big-endian masked to31 bits. Step seeds use their own
    workflow_step component and never pass through this policy derivation.
    """
    if not isinstance(raw, dict):
        raise ValueError("failures: expected mapping of names to policies")
    policies = {}
    manager = SeedManager(master_seed)
    for name, value in normalize_yaml_dict_keys(raw).items():
        if not isinstance(name, str) or not name or not isinstance(value, dict):
            raise ValueError("failures: expected nonempty names and policy mappings")
        check_no_extra_keys(
            value, {"modes", "attrs", "expand_groups"}, f"failures.{name}"
        )
        modes = []
        raw_modes = value.get("modes", [])
        if not isinstance(raw_modes, list):
            raise ValueError(f"failure policy {name}: modes must be a list")
        for mode_index, raw_mode in enumerate(raw_modes):
            if not isinstance(raw_mode, dict):
                raise ValueError(
                    f"failure policy {name} mode {mode_index}: expected mapping"
                )
            check_no_extra_keys(
                raw_mode,
                {"weight", "rules", "attrs"},
                f"failures.{name}.modes[{mode_index}]",
            )
            raw_rules = raw_mode.get("rules", [])
            if not isinstance(raw_rules, list):
                raise ValueError(
                    f"failure policy {name} mode {mode_index}: rules must be a list"
                )
            rules = []
            for rule_index, raw_rule in enumerate(raw_rules):
                if not isinstance(raw_rule, dict):
                    raise ValueError(
                        f"failure policy {name} rule {rule_index}: expected mapping"
                    )
                check_no_extra_keys(
                    raw_rule,
                    {
                        "scope",
                        "match",
                        "mode",
                        "probability",
                        "count",
                        "weight_by",
                        "path",
                    },
                    f"failure policy {name} rule {rule_index}",
                )
                match = parse_match_spec(
                    raw_rule.get("match") or {},
                    context=f"failure policy {name} rule {rule_index}",
                )
                rules.append(
                    declared(
                        f"failures.{name}.modes[{mode_index}].rules[{rule_index}]",
                        lambda raw_rule=raw_rule, match=match: FailureRule(
                            scope=cast(EntityScope, raw_rule.get("scope")),
                            conditions=match.conditions,
                            logic=match.logic,
                            mode=raw_rule.get("mode", "all"),
                            probability=raw_rule.get("probability", 1.0),
                            count=raw_rule.get("count", 1),
                            weight_by=raw_rule.get("weight_by"),
                            path=raw_rule.get("path"),
                        ),
                        "failure rule",
                    )
                )
            modes.append(
                declared(
                    f"failures.{name}.modes[{mode_index}]",
                    lambda raw_mode=raw_mode, rules=rules: FailureMode(
                        raw_mode.get("weight", 0),
                        rules,
                        normalize_yaml_dict_keys(raw_mode.get("attrs", {})),
                    ),
                    "failure mode",
                )
            )
        policies[name] = declared(
            f"failures.{name}",
            lambda value=value, modes=modes, name=name: FailurePolicy(
                attrs=normalize_yaml_dict_keys(value.get("attrs", {})),
                expand_groups=value.get("expand_groups", False),
                seed=manager.derive_seed("failure_policy", "failure_policy", name),
                modes=modes,
            ),
            "failure policy",
        )
    return policies
