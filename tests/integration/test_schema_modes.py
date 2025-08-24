import yaml


def test_schema_allows_modes_and_weight_by() -> None:
    import json as _json
    from importlib import resources as res

    import jsonschema

    with (
        res.files("ngraph.schemas")
        .joinpath("scenario.json")
        .open("r", encoding="utf-8") as _f
    ):
        schema = _json.load(_f)

    yaml_doc = """
network:
  name: x
  nodes: {A: {}, B: {}}
  links:
    - source: A
      target: B
      link_params: {capacity: 10, cost: 2}

failure_policy_set:
  p1:
    modes:
      - weight: 1.0
        rules:
          - entity_scope: link
            rule_type: choice
            count: 1
            weight_by: cost

workflow:
  - step_type: BuildGraph
    name: build
"""
    data = yaml.safe_load(yaml_doc)
    jsonschema.validate(data, schema)
