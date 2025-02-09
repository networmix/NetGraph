from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal
from random import random, sample


@dataclass
class FailureCondition:
    """
    A single condition for matching an entity's attribute with an operator and value.

    Example usage:

    .. code-block:: yaml

        conditions:
          - attr: "capacity"
            operator: "<"
            value: 100

    :param attr:
        The name of the attribute to inspect, e.g. "type", "capacity".
    :param operator:
        The comparison operator: "==", "!=", "<", "<=", ">", ">=".
    :param value:
        The value to compare against, e.g. "node", 100, True, etc.
    """

    attr: str  # e.g. "type", "capacity", "region"
    operator: str  # "==", "!=", "<", "<=", ">", ">="
    value: Any  # e.g. "node", 100, "east_coast"


@dataclass
class FailureRule:
    """
    A single rule defining how to match entities and then select them for failure.

    - conditions: list of conditions
    - logic: how to combine conditions ("and", "or", "any")
    - rule_type: how to pick from matched entities ("random", "choice", "all")
    - probability: used by "random" (a float in [0,1])
    - count: used by "choice" (e.g. pick 2)

    :param conditions:
        A list of :class:`FailureCondition` to filter matching entities.
    :param logic:
        How to combine the conditions for matching: "and", "or", or "any".
          - "and": all conditions must be true
          - "or": at least one condition is true
          - "any": skip condition checks; everything is matched
    :param rule_type:
        The selection strategy. One of:
          - "random": pick each matched entity with `probability`
          - "choice": pick exactly `count` from matched
          - "all": pick all matched
    :param probability:
        Probability of selecting any matched entity (used only if rule_type="random").
    :param count:
        Number of matched entities to pick (used only if rule_type="choice").
    """

    conditions: List[FailureCondition] = field(default_factory=list)
    logic: Literal["and", "or", "any"] = "and"
    rule_type: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1


@dataclass
class FailurePolicy:
    """
    A container for multiple FailureRules and arbitrary metadata in `attrs`.

    The method :meth:`apply_failures` merges nodes and links into a single
    dictionary (by their unique ID), and then applies each rule in turn,
    building a union of all failed entities.

    :param rules:
        A list of :class:`FailureRule` objects to apply.
    :param attrs:
        A dictionary for storing policy-wide metadata (e.g. "name", "description").
    """

    rules: List[FailureRule] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def apply_failures(
        self, nodes: Dict[str, Dict[str, Any]], links: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """
        Identify which entities (nodes or links) fail according to the
        defined rules.

        :param nodes:
            A mapping of node_name -> node.attrs, where node.attrs has at least
            a "type" = "node".
        :param links:
            A mapping of link_id -> link.attrs, where link.attrs has at least
            a "type" = "link".
        :returns:
            A list of failed entity IDs. For nodes, that ID is typically the
            node's name. For links, it's the link's ID.
        """
        # Merge nodes and links into a single map of entity_id -> entity_attrs
        # e.g. { "SEA": { "type": "node", ...}, "SEA-DEN-xxx": { "type": "link", ...} }
        all_entities = {**nodes, **links}

        failed_entities = set()

        # Evaluate each rule to find matched entities and union them
        for rule in self.rules:
            matched = self._match_entities(all_entities, rule.conditions, rule.logic)
            selected = self._select_entities(matched, all_entities, rule)
            failed_entities.update(selected)

        return list(failed_entities)

    def _match_entities(
        self,
        all_entities: Dict[str, Dict[str, Any]],
        conditions: List[FailureCondition],
        logic: str,
    ) -> List[str]:
        """
        Find which entities (by ID) satisfy the given list of conditions
        combined by 'and'/'or' logic (or 'any' to skip checks).

        :param all_entities:
            Mapping of entity_id -> attribute dict.
        :param conditions:
            List of :class:`FailureCondition` to apply.
        :param logic:
            "and", "or", or "any".
        :returns:
            A list of entity IDs that match.
        """
        matched = []
        for entity_id, attr_dict in all_entities.items():
            if self._evaluate_conditions(attr_dict, conditions, logic):
                matched.append(entity_id)
        return matched

    @staticmethod
    def _evaluate_conditions(
        entity_attrs: Dict[str, Any], conditions: List[FailureCondition], logic: str
    ) -> bool:
        """
        Check if the given entity (via entity_attrs) meets all/any of the conditions.

        :param entity_attrs:
            The dictionary of attributes for a single entity (node or link).
        :param conditions:
            A list of conditions to evaluate.
        :param logic:
            "and" -> all must be true
            "or"  -> at least one true
            "any" -> skip condition checks (always true)
        :returns:
            True if conditions pass for the specified logic, else False.
        """
        if logic == "any":
            return True  # means "select everything"
        if not conditions:
            return False  # no conditions => no match, unless logic='any'

        results = []
        for cond in conditions:
            results.append(_evaluate_condition(entity_attrs, cond))

        if logic == "and":
            return all(results)
        elif logic == "or":
            return any(results)
        else:
            raise ValueError(f"Unsupported logic: {logic}")

    @staticmethod
    def _select_entities(
        entity_ids: List[str],
        all_entities: Dict[str, Dict[str, Any]],
        rule: FailureRule,
    ) -> List[str]:
        """
        Select which entity IDs will fail from the matched set, based on rule_type.

        :param entity_ids:
            IDs that matched the rule's conditions.
        :param all_entities:
            The full entity dictionary (not strictly needed for some rule_types).
        :param rule:
            The FailureRule specifying how to pick the final subset.
        :returns:
            The final list of entity IDs that fail from this rule.
        """
        if rule.rule_type == "random":
            return [e for e in entity_ids if random() < rule.probability]
        elif rule.rule_type == "choice":
            count = min(rule.count, len(entity_ids))
            # Use sorted(...) to ensure consistent picks when testing
            return sample(sorted(entity_ids), k=count)
        elif rule.rule_type == "all":
            return entity_ids
        else:
            raise ValueError(f"Unsupported rule_type: {rule.rule_type}")


def _evaluate_condition(entity: Dict[str, Any], cond: FailureCondition) -> bool:
    """
    Evaluate one condition (attr, operator, value) against an entity's attrs.

    :param entity:
        The entity's attribute dictionary (node.attrs or link.attrs).
    :param cond:
        A single :class:`FailureCondition` specifying 'attr', 'operator', 'value'.
    :returns:
        True if the condition passes, else False.
    :raises ValueError:
        If the condition's operator is not recognized.
    """
    derived_value = entity.get(cond.attr, None)
    op = cond.operator
    if op == "==":
        return derived_value == cond.value
    elif op == "!=":
        return derived_value != cond.value
    elif op == "<":
        return derived_value < cond.value
    elif op == "<=":
        return derived_value <= cond.value
    elif op == ">":
        return derived_value > cond.value
    elif op == ">=":
        return derived_value >= cond.value
    else:
        raise ValueError(f"Unsupported operator: {op}")
