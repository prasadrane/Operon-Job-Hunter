import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.brain.synthesizer import Synthesizer


def _synth(teacher_output):
    s = Synthesizer.__new__(Synthesizer)
    s.teacher_model = "qwen3.8-max"
    s.settings = MagicMock(BRAIN_TEACHER_MODEL="qwen3.8-max")
    from src.brain.synthesizer import Environment, FileSystemLoader
    from pathlib import Path
    s.jinja_env = Environment(loader=FileSystemLoader(str(Path("src/brain/prompts"))))
    s.retriever = MagicMock()
    from src.brain.retriever import RetrievedChunk
    s.retriever.retrieve.return_value = [
        RetrievedChunk(id="story_kafka_ci", content="Led Kafka governance on AWS MSK cutting incidents 70%",
                       score=0.9, chunk_type="story")]
    s._call_teacher = AsyncMock(return_value=teacher_output)
    return s


GOOD_PLAN = json.dumps({
    "section": "skills", "skills_to_emphasize": ["Kafka"],
    "stories": [{"id": "story_kafka_ci", "why": "w"}],
    "bullets": [{"text": "Led Kafka governance on AWS MSK cutting incidents 70%",
                 "source": "story_kafka_ci"}],
    "gaps": []})


@pytest.mark.asyncio
async def test_synthesize_tailor_sections_serving_parity(monkeypatch):
    import src.brain.inference as inf_mod
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inf_mod, "employer_of", lambda cid, chunks=None: None)
    s = _synth(GOOD_PLAN)
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    assert len(pairs) == 1 and rejects == []
    pair = pairs[0]
    assert pair["metadata"]["facet"] == "tailor_resume" and pair["metadata"]["section"] == "skills"
    assert "[story: story_kafka_ci]" in pair["messages"][1]["content"]
    assert "SECTION: skills" in pair["messages"][1]["content"]
    assert json.loads(pair["messages"][2]["content"])["skills_to_emphasize"] == ["Kafka"]


@pytest.mark.asyncio
async def test_synthesize_tailor_sections_rejects_ungrounded(monkeypatch):
    import src.brain.inference as inf_mod
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inf_mod, "employer_of", lambda cid, chunks=None: None)
    bad = json.dumps({"section": "skills", "skills_to_emphasize": [],
                      "stories": [], "bullets": [
                          {"text": "Built Flink Spark magic at Google", "source": "story_kafka_ci"}],
                      "gaps": []})
    s = _synth(bad)
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    # bullet entities not in source chunk -> gate drop -> empty bullets -> reject
    assert pairs == [] and len(rejects) == 1
    rej = rejects[0]
    assert rej["job_id"] == "j1" and rej["section"] == "skills" and rej["reason"] == "gate_drop"
    assert rej["detail"][0].startswith("bullet dropped: ungrounded entities")


@pytest.mark.asyncio
async def test_section_scope_rejects_foreign_employer_chunk(monkeypatch):
    """experience@ section where the retrieved chunk belongs to another
    employer must be rejected. Patches src.brain.validator.employer_of — the
    REAL binding both the synth pre-filter and the gate's scope re-check use
    (the old inference.employer_of patch was dead for the synthesizer)."""
    import src.brain.inference as inf_mod
    import src.brain.validator as v
    monkeypatch.setattr(inf_mod, "enumerate_sections",
                        lambda chunks=None: ["experience@rocket_mortgage"])
    monkeypatch.setattr(v, "employer_of", lambda cid, chunks=None: "Fannie Mae")
    s = _synth(GOOD_PLAN)
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    # foreign-owned chunk -> scope filter drops it -> no_chunks
    assert pairs == [] and rejects == [{"job_id": "j1", "section": "experience@rocket_mortgage",
                                        "reason": "no_chunks"}]


@pytest.mark.asyncio
async def test_gap_naming_real_corpus_skill_is_stripped(monkeypatch):
    """Teacher claims a gap that names a skill present in the corpus ->
    corpus_entities reverse-verification strips it from the pair plan."""
    import src.brain.inference as inf_mod
    import src.brain.validator as v
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(v, "_INDEX_CACHE", {})
    monkeypatch.setattr(v, "_load_chunks", lambda path: [
        {"id": "c1", "type": "story", "content": "Led Kafka governance on AWS MSK."}])
    plan_with_gap = json.dumps({
        "section": "skills", "skills_to_emphasize": ["Kafka"],
        "stories": [{"id": "story_kafka_ci", "why": "w"}],
        "bullets": [{"text": "Led Kafka governance on AWS MSK cutting incidents 70%",
                     "source": "story_kafka_ci"}],
        "gaps": ["Kafka certification missing"]})
    s = _synth(plan_with_gap)
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    assert len(pairs) == 1 and rejects == []
    assert json.loads(pairs[0]["messages"][2]["content"])["gaps"] == []


STAR_ANSWER = ("I led Kafka governance work on AWS MSK without formal authority over the "
               "platform squads: I mapped stakeholders, ran monthly technical syncs, and "
               "aligned the teams on a shared runbook, cutting incidents 70% and shrinking "
               "mean time to recovery across three quarters.")


@pytest.mark.asyncio
async def test_synthesize_behavioral_grounded():
    from src.brain.mode_router import BrainMode
    from src.brain.prompt_builder import build_prompt
    s = _synth(STAR_ANSWER)
    chunks = s.retriever.retrieve("x")
    question = "Tell me about a time you led a project without formal authority."
    pair, reason = await s.synthesize_behavioral(question, chunks)
    assert reason is None
    assert pair["metadata"]["mode"] == "qa" and pair["metadata"]["facet"] == "behavioral"
    # F3 (P8): the router serves "tell me about a time..." in AVATAR mode, so
    # the training prompt must be the avatar.j2 render, not qa.j2.
    assert pair["messages"][1]["content"] == build_prompt(question, BrainMode.AVATAR, chunks)


@pytest.mark.asyncio
async def test_synthesize_behavioral_rejects_fabrication():
    s = _synth("I deployed Rust services on Kubernetes at Google with Spanner and BigQuery, "
               "migrating eleven critical workloads while leading a team of nine engineers "
               "through two consecutive release trains without incidents or regressions.")
    chunks = s.retriever.retrieve("x")
    pair, reason = await s.synthesize_behavioral("q", chunks)
    assert pair is None and reason == "ungrounded"


@pytest.mark.asyncio
async def test_qa_pair_rejects_refusal_third_person_and_stub():
    """F4 + F2: canned template refusals (0 entities — vacuous grounding pass),
    third-person meta prose on AVATAR-routed questions, and short one-line
    stubs are rejected with per-call reasons (no shared instance state)."""
    s = _synth("I don't have that information. The context does not mention it, "
               "and there is no information about such a project anywhere in the "
               "provided material I was given to answer this interview question with.")
    pair, reason = await s.synthesize_behavioral("Tell me about a time you failed a launch.",
                                                 s.retriever.retrieve("x"))
    assert pair is None and reason == "refusal"
    s2 = _synth("Alex led Kafka governance work on AWS MSK without formal authority, "
                "mapping stakeholders, running monthly syncs, and cutting incidents 70% "
                "over three quarters while aligning platform squads on one shared runbook.")
    pair, reason = await s2.synthesize_behavioral("Tell me about a time you led a project "
                                                  "without formal authority.", s2.retriever.retrieve("x"))
    assert pair is None and reason == "third_person"
    s3 = _synth("I led Kafka governance work cutting incidents 70%.")  # 9 words
    pair, reason = await s3.synthesize_behavioral("Tell me about a time you led a project "
                                                  "without formal authority.", s3.retriever.retrieve("x"))
    assert pair is None and reason == "too_short"
    assert not hasattr(s, "last_reject_reason")  # F2: reasons are per-call returns
    # Name SELF-disclosure in a first-person answer is legal:
    s4 = _synth("I'm Alex Rivera, and I led Kafka governance work on AWS MSK without "
                "formal authority — mapping stakeholders, running monthly syncs, and "
                "aligning platform squads on a shared runbook, cutting incidents 70%.")
    pair, reason = await s4.synthesize_behavioral("Tell me about yourself.",
                                                  s4.retriever.retrieve("x"))
    assert reason is None and pair is not None


@pytest.mark.asyncio
async def test_synthesize_legacy_grounded_retrieval_path():
    """F5 (spec §3.4 remainder): legacy 386 questions re-synthesized grounded;
    chunks come from the SERVE retrieval path; what/how questions keep the
    qa.j2 assistant voice (route_mode), and name mentions are legal there."""
    from src.brain.retriever import RetrievedChunk
    s = _synth("Alex Rivera has used C# for several years to build backend services "
               "and REST APIs, including a reporting service on Azure App Service "
               "with SQL Server, Entity Framework, and unit test coverage of 80%.")
    chunks = [RetrievedChunk(id="n_csharp", content="Used C# with ASP.NET, SQL Server, "
                             "Entity Framework, REST APIs, and Azure App Service; coverage 80%",
                             score=1.0, chunk_type="graph_node")]
    pair, reason = await s.synthesize_legacy("How many years did you work with C#?", chunks)
    assert reason is None and pair["metadata"]["facet"] == "legacy"


@pytest.mark.asyncio
async def test_synthesize_letter_length_and_grounding():
    s = _synth("I led Kafka governance on AWS MSK cutting incidents 70%. " * 30)  # ~270 words, grounded
    pair, reason = await s.synthesize_letter({"job_id": "j1", "jd": "Need Kafka expert"})
    assert reason is None and pair["metadata"]["facet"] == "cover_letter"


@pytest.mark.asyncio
async def test_synthesize_letter_rejects_too_short():
    s = _synth("Too short.")
    pair, reason = await s.synthesize_letter({"job_id": "j1", "jd": "Need Kafka expert"})
    assert pair is None and reason.startswith("length_band")


@pytest.mark.asyncio
async def test_teacher_error_contained(monkeypatch):
    import src.brain.inference as inf_mod
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inf_mod, "employer_of", lambda cid, chunks=None: None)
    s = _synth("")
    s._call_teacher = AsyncMock(side_effect=RuntimeError("gateway 503"))
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    assert pairs == [] and rejects == [{"job_id": "j1", "section": "skills",
                                        "reason": "teacher_fail",
                                        "detail": ["gateway 503"]}]
    pair, reason = await s.synthesize_behavioral("q", s.retriever.retrieve("x"))
    assert pair is None and reason == "teacher_fail"
    pair, reason = await s.synthesize_letter({"job_id": "j1", "jd": "Need Kafka expert"})
    assert pair is None and reason.startswith("teacher_fail")


@pytest.mark.asyncio
async def test_parse_fail_reason(monkeypatch):
    """Teacher replies with non-JSON -> plan unparseable -> reject reason parse_fail."""
    import src.brain.inference as inf_mod
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inf_mod, "employer_of", lambda cid, chunks=None: None)
    s = _synth("sorry, I cannot help with that")
    pairs, rejects = await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    assert pairs == [] and rejects == [{"job_id": "j1", "section": "skills",
                                        "reason": "parse_fail"}]


@pytest.mark.asyncio
async def test_synthesize_fact_node_grounded_and_rejects_fabrication():
    node = {"id": "node_t_kafka", "type": "graph_node", "content": "Apache Kafka",
            "metadata": {"node_type": "Technology", "name": "Apache Kafka"}}
    s = _synth("I ran Apache Kafka clusters on AWS MSK and cut incidents 70% "
               "across three quarters of platform work.")
    pair, reason = await s.synthesize_fact_node(node, [])
    assert reason is None and pair["metadata"]["facet"] == "factual" and pair["metadata"]["mode"] == "qa"
    s2 = _synth("I used Apache Kafka together with Redis, MongoDB, and DynamoDB at "
                "Netflix, Spanner, and BigQuery while leading a platform guild of nine.")
    pair, reason = await s2.synthesize_fact_node(node, [])
    assert pair is None and reason == "ungrounded"


@pytest.mark.asyncio
async def test_call_teacher_forwards_json_mode_to_gateway(monkeypatch):
    """_call_teacher gained a json_mode kwarg (Alibaba 400s on
    response_format=json_object when the prompt lacks the word "json") and
    forwards it verbatim to the gateway provider; default stays True."""
    import src.core.gateway as gw
    import src.brain.synthesizer as syn_mod
    calls = {}
    provider = MagicMock()
    def _generate(**kw):
        calls.update(kw)
        return "ok"
    provider.generate.side_effect = _generate
    gateway = MagicMock()
    gateway.alibaba_provider = provider
    monkeypatch.setattr(gw, "get_gateway", lambda: gateway)
    s = Synthesizer.__new__(Synthesizer)
    s.teacher_model = "m"
    assert await s._call_teacher("p", json_mode=False) == "ok"
    assert calls["json_mode"] is False
    await s._call_teacher("p")
    assert calls["json_mode"] is True


@pytest.mark.asyncio
async def test_behavioral_teacher_call_is_plain_completion():
    """BEHAVIORAL prose prompt (qa.j2) contains no "json" -> teacher must be
    called with json_mode=False or the Alibaba endpoint 400s instantly."""
    s = _synth("I led Kafka governance work cutting incidents 70%.")
    await s.synthesize_behavioral("Tell me about a governance project",
                                  s.retriever.retrieve("x"))
    assert s._call_teacher.await_args.kwargs.get("json_mode") is False


@pytest.mark.asyncio
async def test_fact_avatar_letter_teacher_calls_plain_completion():
    node = {"id": "node_t_kafka", "type": "graph_node", "content": "Apache Kafka",
            "metadata": {"node_type": "Technology", "name": "Apache Kafka"}}
    s = _synth("I ran Apache Kafka clusters on AWS MSK and cut incidents 70%.")
    await s.synthesize_fact_node(node, [])
    assert s._call_teacher.await_args.kwargs.get("json_mode") is False
    s2 = _synth("Ten years building data-heavy backend platforms at Rocket Mortgage.")
    await s2.synthesize_avatar("Introduce yourself and your career arc.",
                               s2.retriever.retrieve("x"))
    assert s2._call_teacher.await_args.kwargs.get("json_mode") is False
    s3 = _synth("I led Kafka governance on AWS MSK cutting incidents 70%. " * 30)
    await s3.synthesize_letter({"job_id": "j1", "jd": "Need Kafka expert"})
    assert s3._call_teacher.await_args.kwargs.get("json_mode") is False


@pytest.mark.asyncio
async def test_json_emitting_paths_keep_json_mode(monkeypatch):
    """Tailor sections (schema block says JSON) and legacy synthesize_chunk
    templates emit JSON -> keep json_mode=True."""
    import src.brain.inference as inf_mod
    monkeypatch.setattr(inf_mod, "enumerate_sections", lambda chunks=None: ["skills"])
    monkeypatch.setattr(inf_mod, "employer_of", lambda cid, chunks=None: None)
    s = _synth(GOOD_PLAN)
    await s.synthesize_tailor_sections({"job_id": "j1", "jd": "Need Kafka expert"})
    assert s._call_teacher.await_args.kwargs.get("json_mode", True) is True
    s2 = _synth('{"pairs": [{"question": "q", "answer": "a"}]}')
    await s2.synthesize_chunk({"id": "x", "type": "story", "content": "c",
                               "metadata": {}})
    assert s2._call_teacher.await_args.kwargs.get("json_mode", True) is True


@pytest.mark.asyncio
async def test_synthesize_avatar_pair_shape():
    """P8 parity: avatar facet must render through the served avatar.j2 prompt,
    byte-exact with build_prompt(question, BrainMode.AVATAR, chunks)."""
    from src.brain.mode_router import BrainMode
    from src.brain.prompt_builder import build_prompt
    s = _synth("Ten years building data-heavy backend platforms at Rocket Mortgage.")
    question = "Introduce yourself and your career arc."
    chunks = s.retriever.retrieve("x")
    pair, reason = await s.synthesize_avatar(question, chunks)
    assert reason is None and pair["metadata"]["mode"] == "avatar" and pair["metadata"]["facet"] == "avatar"
    assert "Alex Rivera" in pair["messages"][1]["content"]
    # the parity assertion: train prompt == serve prompt
    assert pair["messages"][1]["content"] == build_prompt(question, BrainMode.AVATAR, chunks)
