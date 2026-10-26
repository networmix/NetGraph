"""Safe YAML construction with source positions for failed scalar conversions."""

from typing import Any

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode

from ngraph.utils.values import _shown


class _InputLoader(yaml.SafeLoader):
    def __init__(self, stream):
        super().__init__(stream)
        self.failed_scalar: ScalarNode | None = None

    def construct_object(self, node, deep=False):
        try:
            return super().construct_object(node, deep)
        except (ValueError, TypeError, OverflowError, KeyError, AttributeError):
            if isinstance(node, ScalarNode) and self.failed_scalar is None:
                self.failed_scalar = node
            raise


def _scalar_path(root, target):
    pending: list[tuple[Any, tuple[str | int, ...], Any]] = [(root, (), None)]
    visited = set()
    while pending:
        node, path, entry = pending.pop()
        if node is target:
            return path, entry
        if node in visited:
            continue
        visited.add(node)
        if isinstance(node, MappingNode):
            pending.extend(
                (value, (*path, key.value), entry)
                for key, value in reversed(node.value)
            )
        elif isinstance(node, SequenceNode):
            pending.extend(
                (value, (*path, index), value if path == ("workflow",) else entry)
                for index, value in reversed(list(enumerate(node.value)))
            )
    return (), None


def _load_yaml(source: str, context: str) -> Any:
    """Use the same refusal boundary for YAML syntax and scalar conversion."""
    loader = None
    try:
        loader = _InputLoader(source)
        root = loader.get_single_node()
        try:
            return loader.construct_document(root) if root is not None else None
        except (ValueError, TypeError, OverflowError, KeyError, AttributeError) as exc:
            node = loader.failed_scalar
            if node is None:
                raise ValueError(
                    f"{context} = {_shown(source)}: invalid YAML: {exc}"
                ) from exc
            parts, entry = _scalar_path(root, node)
            if context == "components" and (not parts or parts[0] != "components"):
                parts = ("components", *parts)
            path = (
                "".join(
                    f"[{p}]" if isinstance(p, int) else "." + p for p in parts
                ).lstrip(".")
                or context
            )
            workflow_entry = False
            if (
                context == "scenario"
                and isinstance(root, MappingNode)
                and len(parts) >= 2
                and parts[0] == "workflow"
                and isinstance(parts[1], int)
            ):
                workflow_entry = True
                from ngraph.workflow.diagnostics import workflow_location

                name_node = (
                    next(
                        (
                            value
                            for key, value in reversed(entry.value)
                            if key.value == "name"
                        ),
                        None,
                    )
                    if isinstance(entry, MappingNode)
                    else None
                )
                name = (
                    name_node.value
                    if isinstance(name_node, ScalarNode)
                    and name_node is not node
                    and name_node.tag == "tag:yaml.org,2002:str"
                    else None
                )
                path = workflow_location(parts[1], name) + "".join(
                    f"[{part}]" if isinstance(part, int) else "." + part
                    for part in parts[2:]
                )
            lexical = node.value.replace("_", "").lstrip("+-")
            size = (
                f"an integer of {len(lexical)} digits"
                if node.tag == "tag:yaml.org,2002:int" and lexical.isdecimal()
                else f"{_shown(node.value)} ({len(node.value)} characters)"
            )
            mark = node.start_mark
            if workflow_entry:
                message = f"{path} = {size}: invalid YAML scalar at line {mark.line + 1}, column {mark.column + 1}"
            else:
                message = f"{path}: invalid YAML scalar at line {mark.line + 1}, column {mark.column + 1}: {size}"
            raise ValueError(message) from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{context} = {_shown(source)}: invalid YAML: {exc}") from exc
    finally:
        if loader is not None:
            loader.dispose()
