"""Load converts construction refusals; preparation keeps extension exceptions."""

import pytest

from ngraph import Scenario
from ngraph.workflow import BuildGraph


@pytest.mark.parametrize("boundary", ["yaml_arguments", "__post_init__"])
@pytest.mark.parametrize("base", [ValueError, TypeError, KeyError, RuntimeError])
@pytest.mark.parametrize("extended", [False, True])
def test_load_refusal_is_located_and_chained(monkeypatch, boundary, base, extended):
    class Refusal(base):
        def __init__(self, field, value):
            self.field, self.value = field, value
            super().__init__(f"{field} = {value}: reserved")

    original = Refusal("count", 3) if extended else base("count = 3: reserved")

    def refuse(*args, **kwargs):
        raise original

    source = "network: {}\nworkflow:\n- {type: BuildGraph, name: bad}\n"
    converted = base is not RuntimeError
    with monkeypatch.context() as patch:
        patch.setattr(BuildGraph, boundary, refuse)
        with pytest.raises(ValueError if converted else type(original)) as error:
            Scenario.from_yaml(source)
        if converted:
            assert type(error.value) is ValueError
            reason = (
                "'count = 3: reserved'" if base is KeyError else "count = 3: reserved"
            )
            assert str(error.value) == (
                "workflow[0] (name 'bad') = {'type': 'BuildGraph', 'name': 'bad'}: "
                + reason
            )
            assert error.value.__cause__ is original
        else:
            assert error.value is original
            assert str(error.value) == "count = 3: reserved"
            assert error.value.__cause__ is None
        if extended:
            assert original.field == "count" and original.value == 3
    assert Scenario.from_yaml(source).workflow[0].name == "bad"
