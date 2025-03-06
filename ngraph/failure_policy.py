from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal
from random import random, sample


@dataclass
class FailureCondition:
    """
    A single condition for matching an entity's attribute with an operator and value.

    Example usage (YAML-ish):

    .. code-block:: yaml

        conditions:
          - attr: "capacity"
            operator: "<"
            value: 100

    Attributes:
        attr (str):
            The name of the attribute to inspect (e.g. "type", "capacity").
        operator (str):
            The comparison operator: "==", "!=", "<", "<=", ">", ">=".
        value (Any):
            The value to compare against (e.g. "node", 100, True, etc.).
    """

    attr: str
    operator: str
    value: Any


@dataclass
class FailureRule:
    """
    A single rule defining how to match entities and then select them for failure.

    * conditions: list of conditions
    * logic: how to combine conditions ("and", "or", "any")
    * rule_type: how to pick from matched entities ("random", "choice", "all")
    * probability: used by "random" (a float in [0,1])
    * count: used by "choice" (e.g. pick 2)

    When multiple FailureRules appear in a FailurePolicy, the final
    set of failures is the **union** of all entities selected by each rule.

    Attributes:
        conditions (List[FailureCondition]):
            A list of conditions to filter matching entities.
        logic (Literal["and", "or", "any"]):
            - "and": All conditions must be true.
            - "or": At least one condition is true.
            - "any": Skip condition checks; everything is matched.
        rule_type (Literal["random", "choice", "all"]):
            The selection strategy among the matched set:
              - "random": Each matched entity is chosen independently
                with probability = `probability`.
              - "choice": Pick exactly `count` items from the matched set
                (randomly sampled).
              - "all": Select every matched entity.
        probability (float):
            Probability in [0,1], used only if `rule_type="random"`.
        count (int):
            Number of matched entities to pick, used only if `rule_type="choice"`.
    """

    conditions: List[FailureCondition] = field(default_factory=list)
    logic: Literal["and", "or", "any"] = "and"
    rule_type: Literal["random", "choice", "all"] = "all"
    probability: float = 1.0
    count: int = 1

    def __post_init__(self) -> None:
        """
        Validate certain fields after initialization.
        """
        if self.rule_type == "random":
            if not (0.0 <= self.probability <= 1.0):
                raise ValueError(
                    f"probability={self.probability} must be within [0,1] for rule_type='random'."
                )


@dataclass
class FailurePolicy:
    """
    A container for multiple FailureRules and arbitrary metadata in `attrs`.

    The method :meth:`apply_failures` merges nodes and links into a single
    dictionary (by their unique ID), then applies each rule in turn. The final
    result is the union of all failures from each rule.

    Attributes:
        rules (List[FailureRule]):
            A list of FailureRules to apply.
        attrs (Dict[str, Any]):
            Arbitrary metadata about this policy (e.g. "name", "description").
    """

    rules: List[FailureRule] = field(default_factory=list)
    attrs: Dict[str, Any] = field(default_factory=dict)

    def apply_failures(
        self,
        nodes: Dict[str, Dict[str, Any]],
        links: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        """
        Identify which entities (nodes or links) fail, given the defined rules.
        Returns a combined list (union) of all entity IDs that fail.

        Args:
            nodes: A mapping of node_name -> node.attrs (must have "type"="node").
            links: A mapping of link_id -> link.attrs (must have "type"="link").

        Returns:
            A list of failed entity IDs (node names or link IDs).
        """
        # Merge nodes and links into a single map of entity_id -> entity_attrs
        # Example: { "SEA": {...}, "SEA-DEN-xxx": {...} }
        all_entities = {**nodes, **links}

        failed_entities = set()

        # Apply each rule, union all selected entities
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
        Find which entity IDs satisfy the given conditions
        combined by 'and'/'or' logic (or 'any' to skip checks).

        Args:
            all_entities: Mapping of entity_id -> attribute dict.
            conditions: List of FailureCondition to apply.
            logic: "and", "or", or "any".

        Returns:
            A list of entity IDs that match according to the logic.
        """
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
        Check if the given entity meets all or any of the conditions, or if logic='any'.

        Args:
            entity_attrs: Attributes dict for one entity (node or link).
            conditions: List of FailureCondition.
            logic: "and", "or", or "any".

        Returns:
            True if conditions pass, else False.
        """
        if logic == "any":
            # 'any' means skip condition checks and always match
            return True
        if not conditions:
            # If we have zero conditions, we treat this as no match unless logic='any'
            return False

        # Evaluate each condition
        results = [_evaluate_condition(entity_attrs, c) for c in conditions]

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
        From the matched set, pick which entities fail according to rule_type.

        Args:
            entity_ids: IDs that matched the rule's conditions.
            all_entities: Full entity dictionary (for potential future use).
            rule: The FailureRule specifying random/choice/all selection.

        Returns:
            The final list of entity IDs that fail under this rule.
        """
        if rule.rule_type == "random":
            # Each entity is chosen with probability=rule.probability
            return [ent_id for ent_id in entity_ids if random() < rule.probability]
        elif rule.rule_type == "choice":
            # Sample exactly 'count' from the matched set (or fewer if matched < count)
            count = min(rule.count, len(entity_ids))
            # Use sorted(...) for deterministic results
            return sample(sorted(entity_ids), k=count)
        elif rule.rule_type == "all":
            return entity_ids
        else:
            raise ValueError(f"Unsupported rule_type: {rule.rule_type}")


def _evaluate_condition(entity: Dict[str, Any], cond: FailureCondition) -> bool:
    """
    Evaluate one FailureCondition (attr, operator, value) against entity attributes.

    Args:
        entity: The entity's attributes (e.g., node.attrs or link.attrs).
        cond: FailureCondition specifying (attr, operator, value).

    Returns:
        True if the condition passes, else False.

    Raises:
        ValueError: If the operator is not recognized.
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
