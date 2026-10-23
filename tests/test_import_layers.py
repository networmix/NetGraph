"""Modules import what they use at the top; an inner import never breaks a cycle."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "ngraph"


def _modules():
    found = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        name = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        found[name.removesuffix(".__init__")] = path
    return found


MODULES = _modules()


def _owner(name):
    while name and name not in MODULES:
        name = name.rpartition(".")[0]
    return name


def _top_level(name):
    """Modules one module imports when it loads, with its parent packages."""
    imported = set()

    def visit(body):
        for node in body:
            if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                continue
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
                imported.update(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, (ast.If, ast.Try)):
                visit(node.body)
                visit(node.orelse)
                for handler in getattr(node, "handlers", ()):
                    visit(handler.body)

    visit(ast.parse(MODULES[name].read_text()).body)
    parts = name.split(".")
    parents = {".".join(parts[:i]) for i in range(1, len(parts))}
    return {_owner(value) for value in imported} - {""} | (parents & MODULES.keys())


GRAPH = {name: _top_level(name) for name in MODULES}


def _reaches(start, goal):
    seen, pending = set(), [start]
    while pending:
        for module in GRAPH[pending.pop()]:
            if module == goal:
                return True
            if module not in seen:
                seen.add(module)
                pending.append(module)
    return False


def _inner_imports():
    for name, path in MODULES.items():
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(node):
                    if (
                        isinstance(inner, ast.ImportFrom)
                        and inner.module
                        and inner.module.startswith("ngraph")
                    ):
                        yield name, inner.lineno, _owner(inner.module)


def test_no_function_level_import_breaks_an_import_cycle():
    inner = list(_inner_imports())
    # Lazy loads remain (YAML parsing, routes, cost reports); they are not cycles.
    assert any(target == "ngraph.analysis.programs" for _, _, target in inner)
    cycles = [
        f"{name}:{line} -> {target}"
        for name, line, target in inner
        if target == name or _reaches(target, name)
    ]
    assert cycles == []


def test_the_cycle_check_sees_a_cycle_through_top_level_imports():
    # Control: the exporter loads with the workflow base, which imports it.
    assert _reaches("ngraph.workflow.base", "ngraph.export")
    assert not _reaches("ngraph.export", "ngraph.workflow.base")
