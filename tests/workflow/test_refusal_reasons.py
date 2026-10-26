"""Only labels owned by the current construction boundary become locations."""

import pytest

from ngraph import Scenario
from ngraph.utils.values import text
from ngraph.workflow import BuildGraph

SOURCE = "network: {}\nworkflow: [{type: BuildGraph, name: bad}]\n"
ENTRY = "workflow[0] (name 'bad') = {'type': 'BuildGraph', 'name': 'bad'}: "


@pytest.mark.parametrize("stage", ["yaml_arguments", "__post_init__"])
@pytest.mark.parametrize(
    "reason",
    [
        "reserved",
        "BuildGraph: reserved",
        "BuildGraph: BuildGraph: reserved",
        "msd: reserved",
        "tunnel_counts: reserved",
        "workflow step bad: reserved",
    ],
)
def test_reason_loses_only_the_boundary_record_once(monkeypatch, stage, reason):
    original = ValueError(reason)

    def refuse(*args, **kwargs):
        raise original

    record = "workflow step bad" if stage == "yaml_arguments" else "BuildGraph"
    expected = reason.removeprefix(record + ": ")
    with monkeypatch.context() as patch:
        patch.setattr(BuildGraph, stage, refuse)
        with pytest.raises(ValueError) as error:
            Scenario.from_yaml(SOURCE)
        assert str(error.value) == ENTRY + expected
        assert error.value.__cause__ is original
    assert Scenario.from_yaml(SOURCE).workflow[0].name == "bad"


@pytest.mark.parametrize("stage", ["yaml_arguments", "__post_init__"])
@pytest.mark.parametrize(
    "label",
    [
        "custom.label",
        "BuildGraph[0]",
        "BuildGraph.extra",
        "workflow.bad.extra",
        "workflow step bad.extra",
        "msd.extra",
        "tunnel_counts.extra",
        "name",
    ],
)
def test_only_an_owned_validator_label_becomes_a_field(monkeypatch, stage, label):
    original = None

    def refuse(*args, **kwargs):
        nonlocal original
        try:
            text(3, label)
        except ValueError as exc:
            original = exc
            raise

    owned = (
        label == "name"
        or label == "workflow step bad.extra"
        or (
            stage == "__post_init__"
            and label in {"BuildGraph.extra", "workflow.bad.extra"}
        )
    )
    field = "name" if label == "name" else "extra"
    if owned:
        raw = "'bad'" if label == "name" else "3"
        expected = f"workflow[0] (name 'bad').{field} = {raw}: expected text, got 3"
    else:
        expected = ENTRY + f"{label}: expected text, got 3"
    with monkeypatch.context() as patch:
        patch.setattr(BuildGraph, stage, refuse)
        with pytest.raises(ValueError) as error:
            Scenario.from_yaml(SOURCE)
        assert str(error.value) == expected
        assert error.value.__cause__ is original
    assert Scenario.from_yaml(SOURCE).workflow[0].name == "bad"
