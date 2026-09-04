import json

from src.core.gateway.mock import MockLLMProvider


def test_rubric_route_returns_seven_blocks():
    p = MockLLMProvider()
    out = json.loads(p.generate(
        "Evaluate the 7-Block rubric. Job requires Python, FastAPI, Kafka. "
        "Candidate profile: Python, FastAPI, PostgreSQL. Respond with block_a through block_g.",
        json_mode=True))
    assert 0 <= out["fit_score"] <= 100
    assert all(f"block_{c}" in out for c in "abcdefg")
    assert isinstance(out["block_g"]["is_ghost_job"], bool)


def test_scorer_route_returns_score_keys():
    p = MockLLMProvider()
    out = json.loads(p.generate(
        "Is this job worth applying? Return JSON with worth_applying.", json_mode=True))
    assert {"score", "worth_applying", "reason"} <= set(out)


def test_tailor_route_returns_bullets():
    p = MockLLMProvider()
    out = json.loads(p.generate(
        "Target Company: Vertexa\nTarget Title: Senior Backend Engineer\n"
        "produce tailored bullets. Respond in JSON format with summary and optimized_bullets.",
        json_mode=True))
    assert out["summary"]
    assert isinstance(out["optimized_bullets"], list)


def test_mock_scores_track_skill_overlap():
    p = MockLLMProvider()
    strong = json.loads(p.generate("7-Block rubric. Job: Python FastAPI Kafka Kubernetes AWS PostgreSQL Redis. "
                                   "Candidate: Python FastAPI Kafka Kubernetes AWS PostgreSQL Redis.", json_mode=True))
    weak = json.loads(p.generate("7-Block rubric. Job: React TypeScript CSS. Candidate: Python FastAPI Kafka.",
                                 json_mode=True))
    assert strong["fit_score"] > weak["fit_score"]


def test_default_route_nonempty():
    assert MockLLMProvider().generate("anything else").strip()


def test_llm_gateway_routes_to_mock_provider():
    from src.core.config import Settings
    from src.core.gateway.facade import LLMGateway

    settings = Settings(_env_file=None, primary_llm_provider="mock")
    gw = LLMGateway(settings=settings)
    providers = gw.providers
    assert len(providers) == 1
    assert isinstance(providers[0], MockLLMProvider)

