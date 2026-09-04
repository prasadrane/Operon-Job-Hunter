import json

from src.brain.tailor_schema import TailorPlan, parse_tailor_plan, tailor_json_schema

VALID = json.dumps({
    "section": "experience@rocket_mortgage",
    "skills_to_emphasize": ["Kafka", "AWS MSK"],
    "stories": [{"id": "story_kafka_ci", "why": "JD asks schema evolution",
                 "emphasize": ["Avro"]}],
    "bullets": [{"text": "Embedded Avro schema validation into CI, cutting incidents 70%",
                 "source": "story_kafka_ci", "bold": ["Avro schema validation", "70%"]}],
    "gaps": ["Flink experience absent"],
})


def test_parse_valid_plan():
    plan = parse_tailor_plan(VALID)
    assert isinstance(plan, TailorPlan)
    assert plan.bullets[0].source == "story_kafka_ci"
    assert plan.bullets[0].bold == ["Avro schema validation", "70%"]


def test_parse_strips_code_fences():
    plan = parse_tailor_plan("```json\n" + VALID + "\n```")
    assert plan is not None and plan.section == "experience@rocket_mortgage"


def test_parse_invalid_returns_none_without_repair():
    assert parse_tailor_plan("not json at all") is None


def test_repair_callback_used_once():
    calls = []

    def repair(raw: str) -> str:
        calls.append(raw)
        return VALID

    plan = parse_tailor_plan("{broken", repair=repair)
    assert plan is not None and len(calls) == 1


def test_json_schema_exposes_required_shape():
    schema = tailor_json_schema()
    assert schema["type"] == "object"
    props = schema["properties"]
    assert {"section", "skills_to_emphasize", "stories", "bullets", "gaps"} <= set(props)
    assert "bold" in props["bullets"]["items"]["properties"]
    flat = json.dumps(schema)
    assert "$defs" not in schema and "$ref" not in flat  # M1: grammar converter needs a flat schema
