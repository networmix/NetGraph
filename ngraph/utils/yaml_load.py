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
    pending: list[tuple[Any, tuple[str | int, ...]]] = [(root, ())]
    visited = set()
    while pending:
        node, path = pending.pop()
        if node is target:
            return path
        if node in visited:
            continue
        visited.add(node)
        if isinstance(node, MappingNode):
            pending.extend(
                (value, (*path, key.value)) for key, value in reversed(node.value)
            )
        elif isinstance(node, SequenceNode):
            pending.extend(
                (value, (*path, index))
                for index, value in reversed(list(enumerate(node.value)))
            )
    return ()


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
            parts = _scalar_path(root, node)
            if context == "components" and (not parts or parts[0] != "components"):
                parts = ("components", *parts)
            path = (
                "".join(
                    f"[{p}]" if isinstance(p, int) else "." + p for p in parts
                ).lstrip(".")
                or context
            )
            lexical = node.value.replace("_", "").lstrip("+-")
            size = (
                f"an integer of {len(lexical)} digits"
                if node.tag == "tag:yaml.org,2002:int" and lexical.isdecimal()
                else f"{_shown(node.value)} ({len(node.value)} characters)"
            )
            mark = node.start_mark
            raise ValueError(
                f"{path}: invalid YAML scalar at line {mark.line + 1}, column {mark.column + 1}: {size}"
            ) from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"{context} = {_shown(source)}: invalid YAML: {exc}") from exc
    finally:
        if loader is not None:
            loader.dispose()
