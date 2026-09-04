# tests/unit/test_brain_evaluator_frozen.py
import json

import pytest

from src.brain.evaluator import (
    grade_qa_answer, grade_tailor_plan, summarize,
)

GOLD = {"fit_score": 81.0, "matched_skills": ["Kafka", "AWS MSK", "Avro"],
        "missing_skills": ["Flink"]}

PLAN_RAW = json.dumps({
    "section": "skills",
    "skills_to_emphasize": ["Kafka", "AWS MSK", "Python", "CI", "Avro", "REST"],
    "stories": [{"id": "story_kafka_ci", "why": "w"}],
    "bullets": [{"text": "Led Kafka governance on AWS MSK cutting incidents 70%",
                 "source": "story_kafka_ci"}],
    "gaps": [],
})


def test_grade_tailor_plan_all_metrics():
    g = grade_tailor_plan(PLAN_RAW, GOLD, chunk_ids={"story_kafka_ci"})
    assert g["parsed"] and g["integrity"]
    assert g["grounding_rate"] == 1.0
    # gold atoms {kafka, aws, msk, avro} all in plan atoms: recall@5 = 1.0
    assert g["recall_at_5"] == 1.0


def test_grade_tailor_plan_unknown_source_fails_integrity():
    bad = json.dumps({"section": "skills", "skills_to_emphasize": [],
                      "stories": [], "bullets": [{"text": "t", "source": "ghost"}],
                      "gaps": []})
    g = grade_tailor_plan(bad, GOLD, chunk_ids={"story_kafka_ci"})
    assert g["parsed"] and not g["integrity"] and g["grounding_rate"] == 0.0


def test_grade_tailor_plan_unparsed():
    g = grade_tailor_plan("prose, not json", GOLD, chunk_ids=set())
    assert g == {"parsed": False, "integrity": False,
                 "grounding_rate": 0.0, "recall_at_5": None}


def test_grade_tailor_plan_no_gold():
    g = grade_tailor_plan(PLAN_RAW, None, chunk_ids={"story_kafka_ci"})
    assert g["recall_at_5"] is None and g["parsed"]


def test_grade_tailor_plan_compound_gold_skills_atomized():
    # live gold matched_skills are compound phrases; atomize before intersect
    gold = {"matched_skills": ["Event-driven systems (MSK/Kafka)"]}
    raw = json.dumps({"section": "skills",
                      "skills_to_emphasize": ["Kafka", "MSK"],
                      "stories": [], "bullets": [], "gaps": []})
    g = grade_tailor_plan(raw, gold, chunk_ids=set())
    assert g["recall_at_5"] is not None and g["recall_at_5"] > 0.8


def test_grade_qa_negative_probe_admit():
    g = grade_qa_answer("I don't have experience leading a 20-person org.", "admit")
    assert g["verdict"] == "admit" and g["correct"]


def test_grade_qa_negative_probe_bluff():
    g = grade_qa_answer("I led a 20 person org at Google for three years.", "admit")
    assert g["verdict"] == "bluff" and not g["correct"]


def test_grade_qa_expected_answer_passthrough():
    g = grade_qa_answer("Kafka governance work on AWS MSK.", "answer")
    assert g["verdict"] == "answer" and g["correct"]


def test_grade_qa_bluff_not_fooled_by_embedded_never():
    # "whenever"/"forever"/"nevertheless" must not fire the "never" marker
    bluff = ("Whenever Flink comes up, I say I have forever used it, "
             "and nevertheless I led a 20-person org.")
    g = grade_qa_answer(bluff, "admit")
    assert g["verdict"] == "bluff" and not g["correct"]


def test_grade_qa_admit_with_standalone_never():
    g = grade_qa_answer("I have never led a 20-person org.", "admit")
    assert g["verdict"] == "admit" and g["correct"]


def test_grade_qa_rejects_unknown_expected():
    with pytest.raises(ValueError):
        grade_qa_answer("x", "asnwer")


def test_summarize_aggregates():
    rows = [grade_tailor_plan(PLAN_RAW, GOLD, {"story_kafka_ci"}),
            grade_tailor_plan("nope", GOLD, set())]
    s = summarize(rows)
    assert s["format_valid_rate"] == 0.5 and s["n"] == 2


def test_grade_letter_length_and_grounding():
    from src.brain.evaluator import grade_letter
    g = grade_letter("Kafka governance work on AWS MSK " * 50, {"kafka", "aws", "msk", "governance", "work"})
    assert g["length_ok"]  # 300 words, inside 250-350 band
    assert g["grounding_rate"] > 0.9
    assert not grade_letter("too short", {"kafka"})["length_ok"]
