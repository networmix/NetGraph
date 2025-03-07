from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal
from random import random, sample
from collections import defaultdict, deque


@dataclass
class FailureCondition:
    """
    A single condition for matching an entity's attribute with an operator and value.

    Example usage (YAML):

      conditions:
        - attr: "capacity"
          operator: "<"
          value: 100

    Attributes:
        attr (str):
            The name of the attribute to inspect (e.g., "type", "capacity").
        operator (str):
            The comparison operator: "==", "!=", "<", "<=", ">", ">=", "contains",
            "not_contains", "any_value", or "no_value".
        value (Any):
            The value to compare against (e.g., "node", 100, True, etc.).
    """

    attr: str
    operator: str
    value: Any


@dataclass
class FailureRule:
    """
    Defines how to match entities and then select them for failure.

    Attributes:
        conditions (List[FailureCondition]):
            A list of conditions to filter matching entities.
        logic (Literal["and", "or", "any"]):
            - "and": All conditions must be true for a match.
            - "or": At least one condition is true for a match.
            - "any": Skip condition checks and match all entities.
        rule_type (Literal["random", "choice", "all"]):
            The selection strategy among the matched set:
              - "random": Each matched entity is chosen with probability=`probability`.
              - "choice": Pick exactly `count` items (random sample).
              - "all": Select every matched entity.
        probability (float):
            Probability in [0,1], used if `rule_type="random"`.
        count (int):
            Number of entities to pick if `rule_type="choice"`.
    """

    conditions: List[FailureCondition] = field(default_factory=list)
    logic: Literal["and", "or", "any"] = "and"
    rule_type: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1

    def __post_init__(self) -> None:
        """
        Validate the probability if rule_type is 'random'.
        """
        if self.rule_type == "random":
            if not 0.0 <= self.probability <= 1.0:
                raise ValueError(
                    f"probability={self.probability} must be within [0,1] "
                    f"for rule_type='random'."
                )


@dataclass
class FailurePolicy:
    """
    A container for multiple FailureRules plus optional metadata in `attrs`.

    The main entry point is `apply_failures`, which:
      1) Merges all nodes and links into a single entity dictionary.
      2) Applies each FailureRule, collecting a set of failed entity IDs.
      3) Optionally expands failures to include entities sharing a
         'shared_risk_group' with any entity that failed.

    Attributes:
        rules (List[FailureRule]):
            A list of FailureRules to apply.
        attrs (Dict[str, Any]):
            Arbitrary metadata about this policy (e.g. "name", "description").
            If `fail_shared_risk_groups=True`, then shared-risk expansion is used.
    """

    rules: List[FailureRule] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def apply_failures(
        self,
        nodes: Dict[str, Dict[str, Any]],
        links: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        """
        Identify which entities fail given the defined rules, then optionally
        expand by shared-risk groups.

        Args:
            nodes: Dict[node_name, node_attributes]. Must have 'type'="node".
            links: Dict[link_id, link_attributes]. Must have 'type'="link".

        Returns:
            A list of failed entity IDs (union of all rule matches).
        """
        all_entities = {**nodes, **links}
        failed_entities = set()

        # 1) Collect matched failures from each rule
        for rule in self.rules:
            matched = self._match_entities(all_entities, rule.conditions, rule.logic)
            selected = self._select_entities(matched, all_entities, rule)
            failed_entities.update(selected)

        # 2) Optionally expand failures by shared-risk group
        if self.attrs.get("fail_shared_risk_groups", False):
            self._expand_shared_risk_groups(failed_entities, all_entities)

        return list(failed_entities)

    def _match_entities(
        self,
        all_entities: Dict[str, Dict[str, Any]],
        conditions: List[FailureCondition],
        logic: str,
    ) -> List[str]:
        """
        Return all entity IDs matching the given conditions based on 'and'/'or'/'any' logic.

        Args:
            all_entities: {entity_id: attributes}.
            conditions: List of FailureCondition to evaluate.
            logic: "and", "or", or "any".

        Returns:
            A list of matching entity IDs.
        """
        if logic == "any":
            # Skip condition checks; everything matches.
            return list(all_entities.keys())

        if not conditions:
            # If zero conditions, we match nothing unless logic='any'.
            return []

        matched = []
        for entity_id, attr_dict in all_entities.items():
            if self._evaluate_conditions(attr_dict, conditions, logic):
                matched.append(entity_id)
        return matched

    @staticmethod
    def _evaluate_conditions(
        entity_attrs: Dict[str, Any],
        conditions: List[FailureCondition],
        logic: str,
    ) -> bool:
        """
        Evaluate multiple conditions on a single entity. All or any condition(s)
        must pass, depending on 'logic'.

        Args:
            entity_attrs: Attribute dict for one entity.
            conditions: List of FailureCondition to test.
            logic: "and" or "or".

        Returns:
            True if conditions pass, else False.
        """
        if logic not in ("and", "or"):
            raise ValueError(f"Unsupported logic: {logic}")

        results = [_evaluate_condition(entity_attrs, c) for c in conditions]
        return all(results) if logic == "and" else any(results)

    @staticmethod
    def _select_entities(
        entity_ids: List[str],
        all_entities: Dict[str, Dict[str, Any]],
        rule: FailureRule,
    ) -> List[str]:
        """
        From the matched IDs, pick which entities fail under the given rule_type.

        Args:
            entity_ids: Matched entity IDs from _match_entities.
            all_entities: Full entity map (unused now, but available if needed).
            rule: The FailureRule specifying 'random', 'choice', or 'all'.

        Returns:
            A list of selected entity IDs to fail.
        """
        if not entity_ids:
            return []

        if rule.rule_type == "random":
            return [eid for eid in entity_ids if random() < rule.probability]
        elif rule.rule_type == "choice":
            count = min(rule.count, len(entity_ids))
            return sample(sorted(entity_ids), k=count)
        elif rule.rule_type == "all":
            return entity_ids
        else:
            raise ValueError(f"Unsupported rule_type: {rule.rule_type}")

    def _expand_shared_risk_groups(
        self, failed_entities: set[str], all_entities: Dict[str, Dict[str, Any]]
    ) -> None:
        """
        Expand the 'failed_entities' set so that if an entity has
        shared_risk_group=X, all other entities with the same group also fail.

        This is done iteratively until no new failures are found.

        Args:
            failed_entities: Set of entity IDs already marked as failed.
            all_entities: Map of entity_id -> attributes (which may contain 'shared_risk_group').
        """
        # Pre-compute SRG -> entity IDs mapping for efficiency
        srg_map = defaultdict(set)
        for eid, attrs in all_entities.items():
            srg = attrs.get("shared_risk_group")
            if srg:
                srg_map[srg].add(eid)

        queue = deque(failed_entities)
        while queue:
            current = queue.popleft()
            current_srg = all_entities[current].get("shared_risk_group")
            if not current_srg:
                continue

            # All entities in the same SRG should fail
            for other_eid in srg_map[current_srg]:
                if other_eid not in failed_entities:
                    failed_entities.add(other_eid)
                    queue.append(other_eid)


def _evaluate_condition(entity: Dict[str, Any], cond: FailureCondition) -> bool:
    """
    Evaluate a single FailureCondition against an entity's attributes.

    Operators supported:
      ==, !=, <, <=, >, >=, contains, not_contains, any_value, no_value

    Args:
        entity: Entity attributes (e.g., node.attrs or link.attrs).
        cond: FailureCondition specifying (attr, operator, value).

    Returns:
        True if the condition passes, else False.
    """
    has_attr = cond.attr in entity
    derived_value = entity.get(cond.attr, None)
    op = cond.operator

    if op == "==":
        return derived_value == cond.value
    elif op == "!=":
        return derived_value != cond.value
    elif op == "<":
        return (derived_value is not None) and (derived_value < cond.value)
    elif op == "<=":
        return (derived_value is not None) and (derived_value <= cond.value)
    elif op == ">":
        return (derived_value is not None) and (derived_value > cond.value)
    elif op == ">=":
        return (derived_value is not None) and (derived_value >= cond.value)
    elif op == "contains":
        if derived_value is None:
            return False
        return cond.value in derived_value
    elif op == "not_contains":
        if derived_value is None:
            return True
        return cond.value not in derived_value
    elif op == "any_value":
        # Pass if the attribute key exists, even if the value is None
        return has_attr
    elif op == "no_value":
        # Pass if the attribute key is missing or the value is None
        return (not has_attr) or (derived_value is None)
    else:
        raise ValueError(f"Unsupported operator: {op}")
