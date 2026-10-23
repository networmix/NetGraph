"""A YAML declaration's identity is declared data, so an edited copy keeps it."""

import io
import json
from dataclasses import dataclass, replace

import pytest

from ngraph import (
    DemandSet,
    Scenario,
    StepOutput,
    WorkflowStep,
    prepare,
    register_workflow_step,
    run,
    write_json,
)

YAML = """
seed: 42
network:
  nodes: {A: {}, B: {}, C: {}}
  links:
    - {source: A, target: B, capacity: 10}
    - {source: A, target: C, capacity: 10}
demands:
  d:
    - source: "^A$"
      target: "^${t}$"
      volume: 1
      expand: {vars: {t: [B, C]}}
workflow:
  - {type: MaxFlow, name: cap, source: "^A$", target: "^B$", workers: 1}
"""
LOSSY = (
    "volume: 1\n      model: {routing: {type: centralized_te, "
    "source_allocation: optimized}, admission: lossy}"
)


def ids(scenario):
    template = prepare(scenario, demand_sets=("d",)).demand_sets["d"]
    return [parent.base_id for parent in template.expansion_template]


def edited(scenario, **changes):
    specs = scenario.demand_sets["d"].demands
    rows = tuple(replace(spec, **changes) for spec in specs)
    return replace(scenario, demand_sets={"d": DemandSet("d", rows)})


def test_an_edited_expanded_demand_keeps_its_id_and_declaration():
    scenario = Scenario.from_yaml(YAML)
    assert ids(scenario) == ids(edited(scenario, volume=2)) == ["d|0|0", "d|0|1"]
    spec = edited(scenario, volume=2).demand_sets["d"].demands[1]
    assert (spec.yaml_label, spec.declaration_ordinal, spec.expand_leaf_index) == (
        "demands.d[0]",
        0,
        1,
    )


@pytest.mark.parametrize("expand", [True, False])
def test_an_edited_yaml_demand_keeps_its_refusal_label(expand):
    text = YAML.replace("volume: 1", LOSSY)
    if not expand:
        text = text.replace("      expand: {vars: {t: [B, C]}}\n", "")
        text = text.replace("${t}", "B")
    message = (
        r"^demands\.d\[0\]: CentralizedTE without tunnel_count requires "
        "admission=LOSSLESS$"
    )
    scenario = Scenario.from_yaml(text)
    for value in (scenario, edited(scenario)):
        with pytest.raises(ValueError, match=message):
            prepare(value, demand_sets=("d",))


def provenance(scenario):
    out = io.StringIO()
    write_json(run(prepare(scenario)), out)
    step = json.loads(out.getvalue())["steps"][0]
    return step["step_seed"], step["seed_source"]


def test_an_edited_yaml_step_keeps_its_label_and_derived_seed():
    scenario = Scenario.from_yaml(YAML)
    step = scenario.workflow[0]
    derived = provenance(scenario)
    assert derived[1] == "scenario-derived" and derived[0] == step.seed
    copy = replace(step, workers=2)
    assert copy.yaml_label == "workflow step cap"
    assert provenance(replace(scenario, workflow=(copy,))) == derived
    # A seed the caller chooses is the step's own.
    chosen = replace(scenario, workflow=(replace(step, seed=5),))
    assert provenance(chosen) == (5, "explicit-step")


@register_workflow_step("ProvenanceProbe")
@dataclass
class ProvenanceProbe(WorkflowStep):
    def run(self, context):
        return StepOutput({}, None)


@pytest.mark.parametrize("key", ["yaml_label: x", "derived_seed: 1"])
def test_provenance_fields_are_not_yaml_keys(key):
    text = YAML.replace(
        '- {type: MaxFlow, name: cap, source: "^A$", target: "^B$", workers: 1}',
        f"- {{type: ProvenanceProbe, name: probe, {key}}}",
    )
    assert text != YAML
    with pytest.raises(ValueError, match="workflow step 'probe'"):
        Scenario.from_yaml(text)
    plain = Scenario.from_yaml(text.replace(f", {key}", ""))
    assert plain.workflow[0].yaml_label == "workflow step probe"
