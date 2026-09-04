# tests/unit/test_brain_validator_grounding.py
from src.brain.tailor_schema import TailorPlan
from src.brain.validator import (
    extract_entities, employer_of, plan_to_prose, validate_tailor_output,
)

FIXTURE_CHUNKS = [
    {"id": "story_kafka_ci", "type": "story",
     "content": "Led Kafka governance on AWS MSK cutting incidents 70%",
     "metadata": {"company": "Rocket Mortgage"}},
    {"id": "node_dynatrace", "type": "graph_node", "content": "Dynatrace",
     "metadata": {"node_type": "Technology", "name": "Dynatrace"}},
    {"id": "node_rm", "type": "graph_node", "content": "Rocket Mortgage",
     "metadata": {"node_type": "Company", "name": "Rocket Mortgage"}},
    {"id": "node_action_9", "type": "graph_node", "content": "Did the thing",
     "metadata": {"node_type": "Action", "name": "Did the thing"}},
    {"id": "edge_led", "type": "graph_edge", "content": "RocketMortgage --[LED_STORY]--> story_dyn",
     "metadata": {"source": "Rocket Mortgage", "target": "story_dyn", "relation": "LED_STORY"}},
    {"id": "story_dyn", "type": "story", "content": "Dynatrace alert noise down 80%",
     "metadata": {}},
]


def test_extract_entities_lowercases_and_strips_stopwords():
    ents = extract_entities("Led Kafka governance on AWS MSK, cutting incidents 70%")
    assert "kafka" in ents and "aws" in ents and "70%" in ents
    assert "on" not in ents and "the" not in ents


def test_employer_of_direct_metadata():
    assert employer_of("story_kafka_ci", chunks=FIXTURE_CHUNKS) == "Rocket Mortgage"


def test_employer_of_via_edge_traversal():
    assert employer_of("story_dyn", chunks=FIXTURE_CHUNKS) == "Rocket Mortgage"


def test_employer_of_unknown_returns_none():
    assert employer_of("node_dynatrace", chunks=FIXTURE_CHUNKS) is None


def _good_plan():
    return TailorPlan.model_validate({
        "section": "experience@rocket_mortgage",
        "skills_to_emphasize": ["Kafka"],
        "stories": [{"id": "story_kafka_ci", "why": "w", "emphasize": ["Kafka"]}],
        "bullets": [{"text": "Led Kafka governance on AWS MSK cutting incidents 70%",
                     "source": "story_kafka_ci", "bold": ["Kafka", "70%"]}],
        "gaps": [],
    })


def _ctx():
    ids = {c["id"] for c in FIXTURE_CHUNKS if c["type"] != "graph_edge"}
    ents = {c["id"]: extract_entities(c["content"]) for c in FIXTURE_CHUNKS}
    return ids, ents


def test_gate_passes_clean_plan():
    ids, ents = _ctx()
    res = validate_tailor_output(_good_plan(), ids, ents, "experience@rocket_mortgage")
    assert res.confidence >= 0.8 and not res.drops


def test_gate_drops_bullet_with_unknown_source():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.bullets[0].source = "story_ghost"
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage")
    assert len(res.drops) == 1 and len(plan.bullets) == 1 and len(res.plan.bullets) == 0


def test_gate_drops_bullet_with_ungrounded_entities():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.bullets[0].text = "Led Kafka governance with Flink and Spark magic"
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage")
    assert len(res.drops) == 1  # flink/spark/magic not in source-chunk entities


def test_gate_rejects_out_of_section_source():
    ids, ents = _ctx()
    plan = _good_plan()
    res = validate_tailor_output(plan, ids, ents, "experience@fannie_mae",
                                 chunks=FIXTURE_CHUNKS)
    assert any("section" in w.lower() for w in res.warnings + res.drops)


def test_gate_strips_oversized_bold():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.bullets[0].bold = ["Led Kafka governance on AWS MSK cutting incidents"]  # >5 words
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage")
    assert res.plan.bullets[0].bold == []
    assert any("bold" in w.lower() for w in res.warnings)


def test_gate_warns_inconsistent_emphasis():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.skills_to_emphasize = ["Flink"]  # mentioned nowhere
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage")
    assert any("consistency" in w.lower() for w in res.warnings)


def test_plan_to_prose_contains_stories_and_bullets():
    prose = plan_to_prose(_good_plan())
    assert "Kafka governance" in prose and "w" in prose


def test_gate_rejects_gap_present_in_corpus():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.gaps = ["Kafka experience absent"]  # Kafka IS in the corpus
    corpus = set()
    for e in ents.values():
        corpus |= e
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage",
                                 chunks=FIXTURE_CHUNKS, corpus_entities=corpus)
    assert res.plan.gaps == []
    assert any("gap" in w.lower() for w in res.warnings + res.drops)


def test_gate_keeps_gap_absent_from_corpus():
    ids, ents = _ctx()
    plan = _good_plan()
    plan.gaps = ["Flink streaming experience absent"]
    corpus = set()
    for e in ents.values():
        corpus |= e
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage",
                                 chunks=FIXTURE_CHUNKS, corpus_entities=corpus)
    assert res.plan.gaps == ["Flink streaming experience absent"]


def test_gate_normalizes_bullet_source_with_prefix():
    ids, ents = _ctx()
    plan = _good_plan()
    # Model wrote prefix from [STAR_Story: story_kafka_ci]
    plan.bullets[0].source = "STAR_Story: story_kafka_ci"
    res = validate_tailor_output(plan, ids, ents, "experience@rocket_mortgage")
    assert not res.drops
    assert res.plan.bullets[0].source == "story_kafka_ci"


def test_gate_normalizes_bullet_source_with_story_slug():
    ids = {"Story 6 - AI Intent-to-API Router on Amazon Bedrock"}
    ents = {"Story 6 - AI Intent-to-API Router on Amazon Bedrock": extract_entities("AI intent router")}
    plan = TailorPlan.model_validate({
        "section": "skills",
        "skills_to_emphasize": [],
        "stories": [{"id": "story-6", "why": "AI", "emphasize": []}],
        "bullets": [{"text": "AI intent router", "source": "story-6", "bold": []}],
        "gaps": [],
    })
    res = validate_tailor_output(plan, ids, ents, "skills")
    assert not res.drops
    assert res.plan.bullets[0].source == "Story 6 - AI Intent-to-API Router on Amazon Bedrock"
    assert res.plan.stories[0].id == "Story 6 - AI Intent-to-API Router on Amazon Bedrock"

