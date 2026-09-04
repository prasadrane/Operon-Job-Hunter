# tests/unit/test_brain_sectioned.py
import importlib, json
from unittest.mock import MagicMock

from src.brain.inference import enumerate_sections, make_cache_key, reduce_section_plans
from src.brain.tailor_schema import TailorPlan

inference_mod = importlib.import_module("src.brain.inference")

FIXTURE = [
    {"id": "node_rm", "type": "graph_node", "content": "Rocket Mortgage",
     "metadata": {"node_type": "Company", "name": "Rocket Mortgage",
                  "graph_node_id": "Rocket Mortgage"}},
    {"id": "node_lcs", "type": "graph_node", "content": "London Computer Systems",
     "metadata": {"node_type": "Company", "name": "London Computer Systems",
                  "graph_node_id": "London Computer Systems"}},
    {"id": "node_doc", "type": "graph_node", "content": "MASTER RESUME",
     "metadata": {"node_type": "Company", "name": "MASTER RESUME & EXHAUSTIVE SOURCE OF TRUTH",
                  "graph_node_id": "MASTER RESUME & EXHAUSTIVE SOURCE OF TRUTH"}},
    # real-data noise (B1, profiled 2026-08-27): story titles, role names and
    # the doc-title itself all appear as ownership-edge sources
    {"id": "e1", "type": "graph_edge", "content": "",
     "metadata": {"source": "Rocket Mortgage", "target": "story_1", "relation": "LED_STORY"}},
    {"id": "e2", "type": "graph_edge", "content": "",
     "metadata": {"source": "London Computer Systems", "target": "story_2", "relation": "LED_STORY"}},
    {"id": "e3", "type": "graph_edge", "content": "",
     "metadata": {"source": "Story 1 - Observability & Fannie Mae Integration (Dynatrace)",
                  "target": "node_action_9", "relation": "HAS_ACTION"}},
    {"id": "e4", "type": "graph_edge", "content": "",
     "metadata": {"source": "Software Engineer", "target": "node_action_10", "relation": "HAS_ACTION"}},
    {"id": "e5", "type": "graph_edge", "content": "",
     "metadata": {"source": "MASTER RESUME & EXHAUSTIVE SOURCE OF TRUTH",
                  "target": "ALEX RIVERA", "relation": "EMPLOYED"}},
]


def test_enumerate_sections_real_data_shape():
    """B1: only LED_STORY-source Company nodes become sections; story titles,
    role names and the doc-title pseudo-company (which HAS edges) stay out."""
    secs = enumerate_sections(chunks=FIXTURE)
    assert secs == ["skills", "experience@rocket_mortgage",
                    "experience@london_computer_systems"]


def _plan(section, story_ids, skills, bullets):
    return TailorPlan.model_validate({
        "section": section, "skills_to_emphasize": skills,
        "stories": [{"id": sid, "why": "w"} for sid in story_ids],
        "bullets": [{"text": f"b-{b}", "source": b} for b in bullets],
        "gaps": []})


def test_reduce_global_uniqueness_and_skills_union():
    p1 = _plan("experience@a", ["s1"], ["Kafka", "AWS"], ["s1"])
    p2 = _plan("experience@b", ["s1", "s2"], ["AWS", "Dynatrace"], ["s1", "s2"])
    out = reduce_section_plans([("experience@a", p1), ("experience@b", p2)])
    assert out["merged_skills"] == ["Kafka", "AWS", "Dynatrace"]
    kept_b = [b.source for b in out["plans"]["experience@b"].bullets]
    assert "s1" not in kept_b and "s2" in kept_b  # collision: earlier section wins
    assert any("collision" in w.lower() for w in out["warnings"])


def test_reduce_same_section_story_bullet_pair_survives():
    """B2: a bullet citing its own section's listed story is one claim, not a
    collision — the canonical §3.3 shape must survive reduce intact."""
    p = _plan("experience@a", ["s1"], ["Kafka"], ["s1"])
    out = reduce_section_plans([("experience@a", p)])
    assert [s.id for s in out["plans"]["experience@a"].stories] == ["s1"]
    assert [b.source for b in out["plans"]["experience@a"].bullets] == ["s1"]
    assert out["warnings"] == []


def test_tailor_resume_sections_end_to_end_with_mock(monkeypatch):
    from collections import OrderedDict
    from src.brain.inference import BrainInference
    b = BrainInference.__new__(BrainInference)
    from src.brain.config import get_brain_settings
    b.settings = get_brain_settings()
    b._cache = OrderedDict()
    b.retriever = MagicMock()
    from src.brain.retriever import RetrievedChunk
    b.retriever.retrieve.return_value = [
        RetrievedChunk(id="story_kafka_ci", content="Kafka on MSK 70%",
                       score=0.9, chunk_type="story")]
    b.ollama = MagicMock()
    good = json.dumps({"section": "skills", "skills_to_emphasize": ["Kafka"],
                       "stories": [{"id": "story_kafka_ci", "why": "w"}],
                       "bullets": [{"text": "Kafka on MSK 70%", "source": "story_kafka_ci"}],
                       "gaps": []})
    b.ollama.generate.return_value = good
    monkeypatch.setattr(inference_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inference_mod, "employer_of", lambda cid, chunks=None: None)
    monkeypatch.setattr(inference_mod, "append_telemetry", lambda rec: None)
    out = b.tailor_resume_sections("Need Kafka expert " * 5)
    assert out["plans"]["skills"] is not None
    assert out["plans"]["skills"].bullets[0].source == "story_kafka_ci"
    assert b.ollama.generate.call_args.kwargs.get("format") is not None  # schema-format used


def _recording_brian(monkeypatch, sections, generate_result, last_meta=None):
    """BrainInference with mocks; returns (b, records) where records captures
    every append_telemetry dict for the run."""
    from collections import OrderedDict
    from src.brain.inference import BrainInference
    from src.brain.retriever import RetrievedChunk
    b = BrainInference.__new__(BrainInference)
    b.settings = inference_mod.get_brain_settings()
    b._cache = OrderedDict()
    b.retriever = MagicMock()
    b.retriever.retrieve.return_value = [
        RetrievedChunk(id="story_kafka_ci", content="Kafka on MSK 70%",
                       score=0.9, chunk_type="story")]
    b.ollama = MagicMock()
    b.ollama.last_meta = last_meta
    if isinstance(generate_result, list):
        b.ollama.generate.side_effect = generate_result
    else:
        b.ollama.generate.return_value = generate_result
    monkeypatch.setattr(inference_mod, "enumerate_sections",
                        lambda chunks=None: list(sections))
    monkeypatch.setattr(inference_mod, "employer_of", lambda cid, chunks=None: None)
    records = []
    monkeypatch.setattr(inference_mod, "append_telemetry", records.append)
    return b, records


_GOOD_PLAN = json.dumps({
    "section": "skills", "skills_to_emphasize": ["Kafka"],
    "stories": [{"id": "story_kafka_ci", "why": "w"}],
    "bullets": [{"text": "Kafka on MSK 70%", "source": "story_kafka_ci"}],
    "gaps": []})


def test_section_telemetry_failure_fields(monkeypatch):
    """Failed parse: format_fail True, no integrity drops, num_ctx from the
    tailor-resume profile; records stay JSON-serializable with a MagicMock
    client and no last_meta."""
    b, records = _recording_brian(monkeypatch, ["skills"], "garbage not json")
    b.tailor_resume_sections("JD " * 30)
    sec = [r for r in records if r["section"] == "skills"][0]
    assert sec["format_fail"] is True
    assert sec["plan_integrity_violations"] == 0
    assert sec["num_ctx"] == 4096
    assert "prompt_eval_count" not in sec
    assert records[-1]["section"] == "__reduce__"
    assert records[-1]["reduce_collisions"] == 0
    json.dumps(records, allow_nan=False)  # serializable even with MagicMock client


def test_section_telemetry_integrity_drops_and_prompt_count(monkeypatch):
    """Gate drop (unknown bullet source) -> plan_integrity_violations >= 1;
    prompt_eval_count taken from ollama.last_meta."""
    bad = json.dumps({
        "section": "skills", "skills_to_emphasize": ["Kafka"],
        "stories": [{"id": "story_kafka_ci", "why": "w"}],
        "bullets": [{"text": "Ghost metric 90%", "source": "story_ghost"}],
        "gaps": []})
    b, records = _recording_brian(monkeypatch, ["skills"], bad,
                                  last_meta={"prompt_eval_count": 1500, "eval_count": 80})
    b.tailor_resume_sections("Need Kafka expert " * 5)
    sec = [r for r in records if r["section"] == "skills"][0]
    assert sec["format_fail"] is False
    assert sec["plan_integrity_violations"] >= 1
    assert sec["prompt_eval_count"] == 1500


def test_run_level_reduce_collisions_record(monkeypatch):
    """Two sections claiming the same story -> reduce collisions counted in a
    final __reduce__ record."""
    b, records = _recording_brian(monkeypatch, ["skills", "skills2"], _GOOD_PLAN)
    out = b.tailor_resume_sections("Need Kafka expert " * 5)
    assert any("reduce collision" in w for w in out["warnings"])
    last = records[-1]
    assert last["section"] == "__reduce__"
    assert last["mode"] == "tailoring"
    assert last["reduce_collisions"] >= 1


def test_section_failure_degrades_to_none_plan(monkeypatch):
    from collections import OrderedDict
    from src.brain.inference import BrainInference
    b = BrainInference.__new__(BrainInference)
    from src.brain.config import get_brain_settings
    b.settings = get_brain_settings()
    b._cache = OrderedDict()
    b.retriever = MagicMock()
    b.retriever.retrieve.return_value = []
    b.ollama = MagicMock()
    b.ollama.generate.return_value = "garbage not json"
    monkeypatch.setattr(inference_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inference_mod, "append_telemetry", lambda rec: None)
    out = b.tailor_resume_sections("JD " * 30)
    assert out["plans"]["skills"] is None
    assert any("skills" in w for w in out["warnings"])
