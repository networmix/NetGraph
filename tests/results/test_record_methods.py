"""Result records retain value behavior without redundant generated methods."""

import copy
import dataclasses
import inspect
import pickle
import subprocess
import sys
from types import MappingProxyType

import pytest

from ngraph import results
from ngraph.utils.values import _FrozenDict, _FrozenList


def test_records_share_value_methods_and_keep_frozen_field_metadata():
    records = [
        kind
        for name, kind in vars(results).items()
        if not name.startswith("_")
        and isinstance(kind, type)
        and kind.__module__ == results.__name__
        and dataclasses.is_dataclass(kind)
    ]
    assert len(records) == 62
    for kind in records:
        assert kind.__dataclass_params__.frozen
        names = tuple(field.name for field in dataclasses.fields(kind))
        assert names == kind.__match_args__
        if kind is results.FailurePattern:
            # Failure masks are hot dict keys; preserve their compiled methods.
            assert "__eq__" in vars(kind) and "__hash__" in vars(kind)
        else:
            assert {"__eq__", "__repr__", "__hash__"}.isdisjoint(vars(kind))


def test_shared_record_values_copies_hashes_and_refusals():
    value = results.ExactAlpha(0.5, 1, 2)
    same = results.ExactAlpha(value=0.5, numerator=1, denominator=2)
    assert value == same and value is not same
    assert value != results.ExactAlpha(0.5, 2, 4)
    assert value.__eq__((0.5, 1, 2)) is NotImplemented
    assert hash(value) == hash((0.5, 1, 2))
    assert {value: "present"}[same] == "present"
    assert repr(value) == "ExactAlpha(value=0.5, numerator=1, denominator=2)"
    assert dataclasses.asdict(value) == {
        "value": 0.5,
        "numerator": 1,
        "denominator": 2,
    }
    assert dataclasses.replace(value, numerator=3).numerator == 3
    for duplicate in (
        copy.copy(value),
        copy.deepcopy(value),
        pickle.loads(pickle.dumps(value)),
    ):
        assert duplicate == value and duplicate is not value
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.numerator = 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        del value.numerator
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.other = 3
    with pytest.raises(TypeError):
        results.ExactAlpha(0.5, 1)
    with pytest.raises(TypeError):
        results.ExactAlpha(0.5, 1, 2, unknown=True)
    with pytest.raises(TypeError):
        hash(results.StepOutput({"x": 1}, None))
    recursive = results.StepOutput({}, None)
    object.__setattr__(recursive, "result", recursive)
    assert repr(recursive).endswith("result=...)")


def test_record_post_init_and_generic_constructors_still_run():
    graph = {"nodes": ["a"]}
    value = results.BuildGraphResult(False, 1, 0, graph)
    graph["nodes"].append("b")
    assert value.graph == {"nodes": ["a"]}
    assert type(value.graph) is _FrozenDict
    assert type(value.graph["nodes"]) is _FrozenList
    costs = results.CostPowerResult(False, 1, {2: (), 0: ()})
    assert tuple(costs.levels) == (0, 2)
    prior = {}
    context = results.StepContext(None, prior, "custom", 0, None, "none")
    prior["new"] = object()
    assert not context.prior_results
    assert isinstance(context.prior_results, MappingProxyType)
    state = results.CaseState[int]((1, 2), None)
    assert state.rows == (1, 2)
    for kind in (
        results.BuildGraphResult,
        results.CostPowerResult,
        results.StepContext,
    ):
        names = tuple(field.name for field in dataclasses.fields(kind))
        assert tuple(inspect.signature(kind).parameters) == names


def test_record_import_does_not_inspect_constructor_signatures():
    code = """
import dataclasses
import importlib
from unittest.mock import patch
import ngraph.results as results
generator = 'dataclasses._FuncBuilder.add_fn' if hasattr(dataclasses, '_FuncBuilder') else 'dataclasses._create_fn'
with patch('inspect.signature', side_effect=AssertionError('signature inspection at import')), patch(generator, side_effect=AssertionError('method generation at import')):
    importlib.reload(results)
assert results.ExactAlpha(.5, 1, 2).numerator == 1
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code], capture_output=True, text=True, timeout=20
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize(
    "kind",
    [
        kind
        for name, kind in vars(results).items()
        if not name.startswith("_")
        and isinstance(kind, type)
        and kind.__module__ == results.__name__
        and dataclasses.is_dataclass(kind)
        and "__post_init__" not in vars(kind)
    ],
)
def test_static_constructor_assigns_each_declared_argument(kind):
    fields = dataclasses.fields(kind)
    values = {field.name: object() for field in fields}
    for value in (kind(**values), kind(*values.values())):
        assert all(getattr(value, name) is item for name, item in values.items())
        assert tuple(inspect.signature(kind).parameters) == tuple(values)
    for field in fields:
        parameter = inspect.signature(kind).parameters[field.name]
        if field.default is not dataclasses.MISSING:
            assert parameter.default == field.default
        else:
            assert parameter.default is inspect.Parameter.empty


def test_frozen_record_subclass_can_add_fields_but_cannot_edit_base_fields():
    class Derived(results.ExactAlpha):
        pass

    value = Derived(0.5, 1, 2)
    value.extra = 3
    assert value.extra == 3
    del value.extra
    assert not hasattr(value, "extra")
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.numerator = 3
    with pytest.raises(dataclasses.FrozenInstanceError):
        del value.numerator
