"""The packaged results schema is generated from the record declarations."""

import json
import runpy
from importlib import resources
from pathlib import Path

import pytest

GENERATOR = Path(__file__).resolve().parents[2] / "dev/generate_results_schema.py"


def generator():
    return runpy.run_path(str(GENERATOR), run_name="generator")


def test_packaged_schema_equals_the_generated_schema():
    packaged = resources.files("ngraph.schemas").joinpath("results.json").read_text()
    assert packaged == generator()["generate"]()


def test_plain_record_definitions_follow_their_declared_fields():
    tools = generator()
    from ngraph.results import ExactAlpha, SelfPair, SplitConstraint

    alpha = tools["record"](ExactAlpha)
    assert list(alpha["properties"]) == ["value", "numerator", "denominator"]
    assert alpha["properties"]["value"] == {
        "description": "Alpha as a binary64 value.",
        "type": "number",
        "exclusiveMinimum": 0,
    }
    assert alpha["properties"]["denominator"] == {
        "description": "Alpha's exact denominator.",
        "type": "integer",
        "minimum": 1,
    }
    described = {
        name: {k: v for k, v in value.items() if k != "description"}
        for name, value in tools["record"](SelfPair)["properties"].items()
    }
    assert described == {
        "kind": {"enum": ["self"]},
        "id": {"type": "string"},
        "node": {"type": "string"},
        "capacity_units": {"enum": [0]},
    }
    split = tools["record"](SplitConstraint)
    assert split["required"] == [
        "kind",
        "label",
        "incoming_physical",
        "basis",
        "members",
        "q_upper_bound",
        "met",
    ]
    assert split["additionalProperties"] is False


def test_an_undeclared_type_has_no_silent_schema():
    with pytest.raises(TypeError, match="no schema"):
        generator()["schema"](complex)
    schema = json.loads(generator()["generate"]())
    assert "SelectorJSON" in schema["$defs"] and "ModelJSON" in schema["$defs"]


def test_the_reference_page_equals_the_generated_page():
    tools = generator()
    page = (GENERATOR.parents[1] / "docs/reference/results.md").read_text()
    assert page == tools["page"](json.loads(tools["generate"]()))


def test_every_field_has_a_description_and_constraints_are_exempt():
    tools = generator()
    document = json.loads(tools["generate"]())
    missing = []
    tools["undescribed"](document, "#", missing)
    assert missing == []
    sample = {
        "properties": {
            "a": {"description": "kept", "type": "integer"},
            "b": {"type": "object", "properties": {"c": {"type": "string"}}},
            "h": {"description": " ", "$ref": "#/$defs/D"},
            "i": {"description": "dangling", "$ref": "#/$defs/Missing"},
        },
        "if": {"properties": {"d": {"const": 1}}},
        "then": {"properties": {"e": {"type": "null"}}},
        "anyOf": [{"properties": {"f": {"description": "x"}, "g": {}}}],
        "$defs": {"D": {"properties": {"j": {"type": "string"}}}},
    }
    found = []
    tools["undescribed"](sample, "#", found)
    assert found == [
        "#/$defs/D/j",
        "#/b",
        "#/b/c",
        "#/h",
        "#/i ($ref #/$defs/Missing names no definition)",
        "#/anyOf[0]/g",
    ]


@pytest.mark.parametrize("check", [False, True])
def test_a_field_without_a_description_stops_the_generator(monkeypatch, check):
    # The field lives in a definition, as every result field does.
    tools = generator()
    document = json.loads(tools["generate"]())
    del document["$defs"]["EndpointsJSON"]["properties"]["sources"]["description"]
    found = []
    tools["undescribed"](document, "#", found)
    assert found == ["#/$defs/EndpointsJSON/sources"]
    main = tools["main"]
    monkeypatch.setitem(main.__globals__, "generate", lambda: json.dumps(document))
    monkeypatch.setattr(
        "sys.argv", ["generate_results_schema.py", *(["--check"] if check else [])]
    )
    with pytest.raises(SystemExit, match="EndpointsJSON/sources"):
        main()


def test_a_record_field_docstring_reaches_the_schema():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Probe:
        first: int
        """The first value."""
        second: str

    assert generator()["field_docs"](Probe) == {"first": "The first value."}


def presence(definition, extra=None):
    """apply_presence on one definition `D` (plus any `$defs` it refers to)."""
    tools = generator()
    document = {"$defs": {"D": definition, **(extra or {})}}
    return tools["apply_presence"](document), document["$defs"]["D"]


def test_presence_facts_render_and_agree_with_the_schema():
    tools = generator()
    document = json.loads(tools["generate"]())
    assert "absent_when" not in json.dumps(document)
    assert "null_when" not in json.dumps(document)
    nullable = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
    found, node = presence(
        {
            "properties": {
                "a": {**nullable, "description": "A count.", "null_when": "it is T1's"},
                "b": {
                    "type": "integer",
                    "description": "A sum.",
                    "absent_when": "x is off",
                },
                "c": {
                    "type": "null",
                    "description": "No totals.",
                    "null_when": "always",
                },
            },
            "required": ["a", "c"],
        }
    )
    assert found == []
    descriptions = [node["properties"][k]["description"] for k in "abc"]
    assert descriptions == [
        "A count. Null when it is T1's.",
        "A sum. Absent when x is off.",
        "Always null: no totals.",
    ]


@pytest.mark.parametrize(
    ("node", "required", "problem"),
    [
        # one plant per refusal kind
        (
            {"type": "integer", "description": "A count."},
            False,
            "optional without absent_when",
        ),
        (
            {"type": "integer", "description": "A count.", "absent_when": "off"},
            True,
            "absent_when on a required property",
        ),
        (
            {
                "anyOf": [{"type": "integer"}, {"type": "null"}],
                "description": "A count.",
            },
            True,
            "nullable without null_when",
        ),
        (
            {"type": "integer", "description": "A count.", "null_when": "off"},
            True,
            "null_when on a property that cannot be null",
        ),
        (
            {"type": "integer", "description": "A count; null for T1."},
            True,
            "the free text says null (declare null_when)",
        ),
        (
            {"type": "integer", "description": "A count; absent without details."},
            True,
            "the free text says absent (declare absent_when)",
        ),
        # Sol's word-order counterexamples: conditional-first true wording and a false
        # "absent when requested" both stay in free text, so both are refused as such.
        (
            {
                "type": "integer",
                "description": "When this output was not requested, the field is absent.",
                "absent_when": "it was not requested",
            },
            False,
            "the free text says absent (declare absent_when)",
        ),
        (
            {
                "type": "integer",
                "description": "A count; absent when requested.",
                "absent_when": "it was not requested",
            },
            False,
            "the free text says absent (declare absent_when)",
        ),
    ],
)
def test_each_presence_disagreement_is_refused(node, required, problem):
    found, _ = presence(
        {"properties": {"f": node}, "required": ["f"] if required else []}
    )
    assert found == [f"D.f: {problem}"]


def test_nullability_is_resolved_through_references_and_composition():
    # Sol's regression: a $ref to a definition that accepts null (as JSONValue does) is
    # nullable; the round-5 check read only the node's own shape and passed it.
    value = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    for node in (
        {"$ref": "#/$defs/Value"},
        {"anyOf": [{"$ref": "#/$defs/Other"}, {"$ref": "#/$defs/Value"}]},
        {"allOf": [{"$ref": "#/$defs/Value"}]},
    ):
        found, _ = presence(
            {
                "properties": {"f": {**node, "description": "A value."}},
                "required": ["f"],
            },
            {"Value": value, "Other": {"enum": ["a"]}},
        )
        assert found == ["D.f: nullable without null_when"], node
    found, _ = presence(
        {
            "properties": {
                "f": {"allOf": [{"$ref": "#/$defs/Other"}], "description": "x."}
            },
            "required": ["f"],
        },
        {"Other": {"enum": ["a"]}},
    )
    assert found == []


def test_a_custom_step_may_export_null_and_its_description_says_when():
    from dataclasses import dataclass
    from importlib import resources
    from io import StringIO

    import jsonschema

    from ngraph import Network, Scenario, prepare, run, write_json
    from ngraph.export import register_result_exporter
    from ngraph.results import StepOutput
    from ngraph.workflow.base import WorkflowStep

    @dataclass(frozen=True)
    class EmptyResult:
        pass

    register_result_exporter(EmptyResult, lambda value, context: None)

    class EmptyStep(WorkflowStep):
        def run(self, context):
            return StepOutput({"operation": "empty"}, EmptyResult())

    class DirectNullStep(WorkflowStep):
        def run(self, context):
            return StepOutput({"operation": "direct-null"}, None)

    value = run(
        prepare(
            Scenario(
                Network(), [EmptyStep(name="empty"), DirectNullStep(name="direct")]
            )
        )
    )
    output = StringIO()
    write_json(value, output)
    wire = json.loads(output.getvalue())
    assert [step["result"] for step in wire["steps"]] == [None, None]
    schema = json.loads(
        resources.files("ngraph.schemas").joinpath("results.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(wire)
    description = schema["$defs"]["StepResultJSON"]["properties"]["result"][
        "description"
    ]
    assert "Null when a custom step returns no result" in description


@pytest.mark.parametrize("check", [False, True])
def test_a_disagreeing_presence_fact_stops_the_generator(monkeypatch, check):
    tools = generator()
    explicit = json.loads(tools["EXPLICIT"].read_text())
    node = explicit["$defs"]["FailureCaseJSON"]["properties"]["trace"]
    node.pop("absent_when")
    monkeypatch.setitem(
        tools["main"].__globals__["generate"].__globals__,
        "EXPLICIT",
        type("Stub", (), {"read_text": staticmethod(lambda: json.dumps(explicit))})(),
    )
    monkeypatch.setattr(
        "sys.argv", ["generate_results_schema.py", *(["--check"] if check else [])]
    )
    with pytest.raises(SystemExit, match="FailureCaseJSON.trace: optional without"):
        tools["main"]()


COUNT = {"type": "integer", "description": "A count."}


@pytest.mark.parametrize(
    ("constraint", "message"),
    [
        # Sol's three composed requirements: the check does not read them, so it refuses.
        ({"required": ["f"]}, "$defs.D: allOf[0] has the form {required}"),
        ({"$ref": "#/$defs/Required"}, "$defs.D: allOf[0] has the form {$ref}"),
        (
            {"anyOf": [{"required": ["f"]}, {"allOf": [{"required": ["f"]}]}]},
            "$defs.D: allOf[0] has the form {anyOf}",
        ),
    ],
)
def test_a_requirement_through_composition_is_refused_not_misread(constraint, message):
    found, _ = presence(
        {"type": "object", "properties": {"f": dict(COUNT)}, "allOf": [constraint]},
        {"Required": {"required": ["f"]}},
    )
    assert found and found[0].startswith(message), found


def test_a_false_absence_behind_a_referenced_requirement_is_refused():
    found, _ = presence(
        {
            "type": "object",
            "properties": {"f": {**COUNT, "absent_when": "details are off"}},
            "allOf": [{"$ref": "#/$defs/Required"}],
        },
        {"Required": {"required": ["f"]}},
    )
    assert found and found[0].startswith("$defs.D: allOf[0] has the form {$ref}"), found


@pytest.mark.parametrize("keyword", ["anyOf", "allOf"])
def test_presence_facts_under_a_composition_branch_are_refused(keyword):
    branch = {
        "type": "object",
        "properties": {"f": {**COUNT, "null_when": "details are off"}},
        "required": ["f"],
    }
    found, _ = presence({keyword: [branch]})
    assert (
        f"$defs.D/{keyword}/0/properties/f: null_when outside a definition's own"
        in (" ".join(found))
    ), found
    assert any(f"D: {keyword}[0] has the form" in f for f in found), found


def _generate_with(change, root=False):
    tools = generator()
    explicit = json.loads(tools["EXPLICIT"].read_text())
    change(explicit if root else explicit["$defs"])
    stub = type("Source", (), {"read_text": staticmethod(lambda: json.dumps(explicit))})
    tools["generate"].__globals__["EXPLICIT"] = stub()
    with pytest.raises(tools["PresenceError"]) as refused:
        tools["generate"]()
    return refused.value.problems


def test_an_equivalent_required_refactor_of_a_real_definition_is_refused_by_name():
    def move(defs):
        definition = defs["NativePlacementJSON"]
        definition.setdefault("allOf", []).append(
            {"required": [definition["required"].pop(0)]}
        )

    problems = _generate_with(move)
    assert any(
        p.startswith("$defs.NativePlacementJSON: allOf[") and "form {required}" in p
        for p in problems
    ), problems


def test_a_wrapped_real_definition_is_refused_not_left_unrendered():
    def wrap(defs):
        defs["NativePlacementJSON"] = {"allOf": [defs["NativePlacementJSON"]]}

    problems = _generate_with(wrap)
    assert any("NativePlacementJSON: allOf[0] has the form" in p for p in problems)
    assert any("outside a definition's own properties" in p for p in problems)


def test_the_classified_forms_are_accepted():
    # A constant test whose branches constrain own values (as ModelJSON's source weights).
    found, node = presence(
        {
            "type": "object",
            "properties": {
                "kind": {"enum": ["a", "b"], "description": "The kind."},
                "f": {
                    "anyOf": [{"type": "integer"}, {"type": "null"}],
                    "description": "A count.",
                    "null_when": "the kind is b",
                },
            },
            "required": ["kind", "f"],
            "additionalProperties": False,
            "if": {"properties": {"kind": {"const": "a"}}, "required": ["kind"]},
            "then": {"properties": {"f": {"type": "integer"}}},
            "else": {"properties": {"f": {"type": "null"}}},
        }
    )
    assert found == [] and node["properties"]["f"]["description"].endswith(
        "Null when the kind is b."
    )
    # A constant test one level down, with nested requirements on a value (as the
    # analyses' detail keys under outputs.details).
    found, _ = presence(
        {
            "type": "object",
            "properties": {
                "outputs": {"$ref": "#/$defs/X", "description": "x."},
                "rows": {"$ref": "#/$defs/X", "description": "x."},
            },
            "required": ["outputs", "rows"],
            "additionalProperties": False,
            "allOf": [
                {
                    "if": {
                        "properties": {
                            "outputs": {
                                "properties": {"details": {"const": True}},
                                "required": ["details"],
                            }
                        },
                        "required": ["outputs"],
                    },
                    "then": {"properties": {"rows": {"items": {"required": ["plan"]}}}},
                }
            ],
        },
        {"X": {"enum": ["a"]}},
    )
    assert found == []
    # Alternatives that each require a key keep both keys optional.
    found, _ = presence(
        {
            "type": "object",
            "properties": {
                "a": {**COUNT, "absent_when": "b is given"},
                "b": {**COUNT, "absent_when": "a is given"},
            },
            "additionalProperties": False,
            "oneOf": [{"required": ["a"]}, {"required": ["b"]}],
        }
    )
    assert found == []
    # ...but a key every alternative requires is required unconditionally: refused.
    found, _ = presence(
        {
            "type": "object",
            "properties": {"a": {**COUNT, "absent_when": "never"}, "b": dict(COUNT)},
            "required": ["b"],
            "oneOf": [{"required": ["a"]}, {"required": ["a", "b"]}],
        }
    )
    assert found == [
        "$defs.D: oneOf requires ['a'] in every alternative, so unconditionally; "
        "list them in the definition's own required"
    ]
    # A union of references and types is classified.
    found, _ = presence(
        {"anyOf": [{"$ref": "#/$defs/X"}, {"type": "string"}]},
        {"X": {"enum": ["a"]}},
    )
    assert found == []
    # An inline object property is refused by name.
    found, _ = presence(
        {
            "type": "object",
            "properties": {
                "o": {
                    "type": "object",
                    "properties": {"g": dict(COUNT)},
                    "description": "x.",
                }
            },
            "required": ["o"],
        }
    )
    assert found and found[0].startswith("$defs.D.o: an inline object"), found


KIND = {"enum": ["a", "b"], "description": "The kind."}
IS_A = {"properties": {"kind": {"const": "a"}}, "required": ["kind"]}


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        # A requirement inside a conditional, in either branch, is refused by form.
        (
            {"if": IS_A, "then": {"required": ["f"]}},
            "$defs.D: its if/then/else cannot be classified: its then holds a required list",
        ),
        (
            {"allOf": [{"if": IS_A, "else": {"required": ["f"]}}]},
            "$defs.D: allOf[0] has the form {else, if}; its else holds a required list",
        ),
        (
            {"allOf": [{"if": IS_A, "then": {"allOf": [{"required": ["f"]}]}}]},
            "$defs.D: allOf[0] has the form {if, then}; its then holds more than value",
        ),
        (
            {"allOf": [{"if": IS_A, "then": {"properties": {"g": {}}}}]},
            "$defs.D: allOf[0] has the form {if, then}; its then holds more than value",
        ),
        # Only a constant test on one own key (or one level down) is a condition.
        *(
            (
                {"allOf": [{"if": test, "then": {"properties": {"f": {}}}}]},
                "$defs.D: allOf[0] has the form {if, then}; its if is not a constant test",
            )
            for test in (
                {},
                {"properties": {"kind": {"enum": ["a", "b"]}}},
                {"properties": {"g": {"const": "a"}}},
                {"properties": {"kind": {"const": "a"}, "f": {"const": 1}}},
                {"properties": {"kind": {"const": "a"}}, "required": ["f"]},
                {
                    "properties": {
                        "kind": {
                            "properties": {"x": {"properties": {"y": {"const": 1}}}}
                        }
                    }
                },
                {"not": {"properties": {"kind": {"const": "a"}}}},
            )
        ),
        (
            {"not": {"not": {"required": ["f"]}}},
            "$defs.D: the keyword not cannot be classified",
        ),
        ({"anyOf": [{"required": ["f"]}]}, "$defs.D: anyOf[0] has the form {required}"),
        ({"then": {"required": ["f"]}}, "$defs.D: then or else without if"),
        (
            {"oneOf": [{"required": ["f"]}, {"properties": {}}]},
            "$defs.D: oneOf has a member that is not a required list",
        ),
    ],
)
def test_a_requirement_the_check_cannot_read_is_refused(extra, message):
    found, _ = presence(
        {
            "type": "object",
            "properties": {
                "kind": dict(KIND),
                "f": {**COUNT, "absent_when": "kind is b"},
            },
            "required": ["kind"],
            "additionalProperties": False,
            **extra,
        }
    )
    assert found and found[0].startswith(message), found


@pytest.mark.parametrize(
    ("node", "refused"),
    [
        # A reference narrowed where it appears (as a standalone analysis requires query).
        ({"allOf": [{"$ref": "#/$defs/X"}, {"required": ["g"]}]}, False),
        ({"allOf": [{"$ref": "#/$defs/X"}, {"not": {"required": ["g"]}}]}, False),
        # Two references are no inline object; a narrowing with properties is one.
        ({"allOf": [{"$ref": "#/$defs/X"}, {"$ref": "#/$defs/X"}]}, False),
        ({"allOf": [{"$ref": "#/$defs/X"}, {"properties": {"g": {}}}]}, True),
        ({"type": "array", "items": {"type": "object", "required": ["g"]}}, True),
        ({"anyOf": [{"type": "null"}, {"type": "object", "properties": {}}]}, True),
    ],
)
def test_an_inline_object_is_refused_and_a_narrowed_reference_is_not(node, refused):
    found, _ = presence(
        {
            "type": "object",
            "properties": {"o": {**node, "description": "x."}},
            "required": ["o"],
        },
        {"X": {"enum": ["a"]}},
    )
    assert any("an inline object" in f for f in found) is refused, found


@pytest.mark.parametrize(
    "member",
    [
        {"type": "object", "properties": {"g": {}}},
        {"type": "array", "items": {"type": "string"}},
        {"oneOf": [{"$ref": "#/$defs/X"}]},
        {"$ref": "#/$defs/X", "description": "x."},
    ],
)
def test_a_union_member_outside_the_classified_forms_is_refused(member):
    found, _ = presence(
        {"anyOf": [{"$ref": "#/$defs/X"}, member]}, {"X": {"enum": ["a"]}}
    )
    assert found and found[0].startswith("$defs.D: anyOf[1] has the form"), found


@pytest.mark.parametrize("key", ["null_when", "absent_when"])
def test_presence_facts_at_the_document_root_are_refused(key):
    def place(raw):
        raw["root"][key] = "off"

    problems = _generate_with(place, root=True)
    assert problems == [
        f"#: {key} outside a definition's own properties "
        "(only $defs.<D>.properties.<field> may declare presence facts)"
    ]


def test_a_narrowed_reference_matches_only_as_a_whole():
    narrowed = {"allOf": [{"$ref": "#/$defs/X"}, {"required": ["g"]}]}
    sibling = {"properties": {"f": {"type": ["integer", "null"], "description": "x."}}}
    found, _ = presence(
        {
            "type": "object",
            "properties": {"o": {**narrowed, **sibling, "description": "x."}},
            "required": ["o"],
            "additionalProperties": False,
        },
        {"X": {"enum": ["a"]}},
    )
    assert found and found[0].startswith("$defs.D.o: an inline object"), found


def closed(names, least=None, **extra):
    return {
        "type": "object",
        "properties": {n: {**COUNT, "absent_when": "not asked"} for n in names},
        "additionalProperties": False,
        **({} if least is None else {"minProperties": least}),
        **extra,
    }


@pytest.mark.parametrize(
    ("names", "least", "refused"),
    [
        (["f"], 1, True),  # the only key: every valid object has it
        (["a", "b", "c"], 1, False),  # PlacementStatesJSON: one of three
        (["a", "b", "c"], 2, False),
        (["a", "b", "c"], 3, True),  # all three are then mandatory
    ],
)
def test_a_minimum_size_is_classified_exactly(names, least, refused):
    found, _ = presence(closed(names, least))
    assert (found != []) is refused, found
    if refused:
        assert all(f.endswith(": absent_when on a required property") for f in found)


def test_a_minimum_size_beyond_the_keys_or_on_an_open_object_is_refused():
    assert presence(closed(["a"], 2))[0] == [
        "$defs.D: minProperties 2 leaves no valid object"
    ]
    assert presence({**closed(["a", "b"], 1), "additionalProperties": True})[0] == [
        "$defs.D: minProperties or oneOf on an object that is not closed is not classified"
    ]


def test_the_real_minimum_size_is_classified_exactly():
    def three(defs):
        defs["PlacementStatesJSON"]["minProperties"] = 3

    problems = _generate_with(three)
    assert problems == [
        f"PlacementStatesJSON.{name}: absent_when on a required property"
        for name in ("converged", "stale", "repair")
    ]


def test_one_of_alternatives_are_classified_exactly():
    # Two equal alternatives never match alone, so every valid object has f.
    found, _ = presence(
        closed(
            ["f", "g"],
            oneOf=[{"required": ["f"]}, {"required": ["g"]}, {"required": ["g"]}],
        )
    )
    assert found == ["D.f: absent_when on a required property"]
    found, _ = presence(
        closed(["f", "g"], oneOf=[{"required": ["f"]}, {"required": ["g"]}])
    )
    assert found == []


def _sol_conditional(placement):
    always = {
        "if": {"properties": {"kind": {"enum": ["a", "b"]}}},
        "then": {"required": ["f"]},
    }
    complementary = [
        {"if": {"properties": {"kind": {"const": k}}}, "then": {"required": ["f"]}}
        for k in ("a", "b")
    ]
    return {
        "direct": always,
        "allOf": {"allOf": [always]},
        "complementary": {"allOf": complementary},
    }[placement]


@pytest.mark.parametrize(
    ("placement", "message"),
    [
        (
            "direct",
            "$defs.D: its if/then/else cannot be classified: its if is not a constant",
        ),
        (
            "allOf",
            "$defs.D: allOf[0] has the form {if, then}; its if is not a constant",
        ),
        (
            "complementary",
            "$defs.D: allOf[0] has the form {if, then}; its then holds a required",
        ),
    ],
)
def test_a_condition_that_could_require_a_key_is_refused_by_form(placement, message):
    # Sol's cases: an always-true condition, and two conditions that together cover every
    # kind; either way f is mandatory, though it declares when it is absent.
    found, _ = presence(
        {
            "type": "object",
            "properties": {
                "kind": dict(KIND),
                "f": {**COUNT, "absent_when": "kind is b"},
            },
            "required": ["kind"],
            "additionalProperties": False,
            **_sol_conditional(placement),
        }
    )
    assert found and found[0].startswith(message), found
    if placement == "complementary":
        assert found[1].startswith(
            "$defs.D: allOf[1] has the form {if, then}; its then"
        )


@pytest.mark.parametrize(
    ("argv", "code"), [(["--help"], 0), (["--nonsense"], 2), (["--check", "x"], 2)]
)
def test_help_and_unknown_arguments_write_nothing(monkeypatch, tmp_path, argv, code):
    main = generator()["main"]
    target, page = tmp_path / "results.json", tmp_path / "results.md"
    target.write_text("sentinel schema")
    page.write_text("sentinel page")
    monkeypatch.setitem(main.__globals__, "TARGET", target)
    monkeypatch.setitem(main.__globals__, "PAGE", page)
    monkeypatch.setattr("sys.argv", ["generate_results_schema.py", *argv])
    with pytest.raises(SystemExit) as stopped:
        main()
    assert stopped.value.code == code
    assert (target.read_text(), page.read_text()) == (
        "sentinel schema",
        "sentinel page",
    )


def test_check_writes_nothing_and_no_argument_writes_both(monkeypatch, tmp_path):
    main = generator()["main"]
    target, page = tmp_path / "results.json", tmp_path / "results.md"
    target.write_text("sentinel schema")
    page.write_text("sentinel page")
    monkeypatch.setitem(main.__globals__, "TARGET", target)
    monkeypatch.setitem(main.__globals__, "PAGE", page)
    monkeypatch.setitem(main.__globals__, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["generate_results_schema.py", "--check"])
    with pytest.raises(SystemExit, match="differs from the record declarations"):
        main()
    assert target.read_text() == "sentinel schema"
    monkeypatch.setattr("sys.argv", ["generate_results_schema.py"])
    main()
    packaged = resources.files("ngraph.schemas").joinpath("results.json").read_text()
    assert target.read_text() == packaged
    assert page.read_text().startswith("# ")
