"""Preparation retains one owner per input and one path for relabelling it."""

import ast
import inspect

from ngraph.analysis import preparation


def test_input_refusals_share_one_owner_only_handler():
    tree = ast.parse(inspect.getsource(preparation.prepare_scenario))
    owners = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Subscript)
            and isinstance(t.value, ast.Name)
            and t.value.id == "input_sources"
            for t in n.targets
        )
    ]
    assert len(owners) == 1
    assert isinstance(owners[0].value, ast.Tuple)
    assert len(owners[0].value.elts) == 2
    handlers = [
        n
        for n in tree.body[0].body
        if isinstance(n, ast.FunctionDef)
        and any(
            isinstance(x, ast.Name) and x.id == "input_sources" for x in ast.walk(n)
        )
    ]
    assert len(handlers) == 1
    assert any(
        isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Subscript)
        and isinstance(n.value.value, ast.Name)
        and n.value.value.id == "inputs"
        for n in ast.walk(handlers[0])
    )
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.ExceptHandler)
        and any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id == handlers[0].name
            for c in ast.walk(n)
        )
    ]
    assert len(calls) == 2


def test_pool_collision_uses_the_common_step_location():
    tree = ast.parse(inspect.getsource(preparation._step_pools))
    names = [
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "workflow_location" not in names
    assert names.count("_labelled") == 2


def test_pool_collision_reports_the_owning_step():
    import pytest

    from ngraph import Network, Node, Scenario, Selector
    from ngraph.analysis.preparation import StepNeeds
    from ngraph.workflow import BuildGraph, MaxFlow

    step = MaxFlow(name="bad")
    scenario = Scenario(
        Network(nodes={n: Node(n) for n in ("A", "B", "C")}),
        (BuildGraph(name="g"), step),
    )
    needs = StepNeeds(pool_endpoints=(Selector("^A$"), Selector("^B$")))
    with pytest.raises(ValueError) as error:
        preparation._step_pools(
            scenario, [(step, "bad", needs)], {"workflow.bad.pair[0]": ("C",)}
        )
    assert (
        str(error.value)
        == "workflow[1] (name 'bad'): pool 'workflow.bad.pair[0]' is also a demand id"
    )
    pools = {}
    preparation._step_pools(scenario, [(step, "bad", needs)], pools)
    assert pools == {"workflow.bad.pair[0]": ("A",)}
