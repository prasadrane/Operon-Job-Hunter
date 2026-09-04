"""Unit tests for Stage 2 Evaluation Pipeline:
- WorkAuthGuard (visa/citizenship blockers)
- GhostJobDetector (legitimacy, scam markers, ghost jobs)
- FitScorer (Alex 0-100 rubric, IC track, microservices vs penalties)
- RubricEvaluator (7-Block A-G structured evaluation)
"""

import importlib
import json
import pytest
from unittest.mock import MagicMock, patch

from src.core.models import JobPosting, JobStatus, EvaluationResult

work_auth_mod = importlib.import_module("src.pipeline.2_evaluation.work_auth_guard")
WorkAuthGuard = work_auth_mod.WorkAuthGuard
WorkAuthResult = work_auth_mod.WorkAuthResult

ghost_mod = importlib.import_module("src.pipeline.2_evaluation.ghost_job_detector")
GhostJobDetector = ghost_mod.GhostJobDetector
GhostJobReport = ghost_mod.GhostJobReport

scorer_mod = importlib.import_module("src.pipeline.2_evaluation.scorer")
FitScorer = scorer_mod.FitScorer
FitScoreResult = scorer_mod.FitScoreResult

rubric_mod = importlib.import_module("src.pipeline.2_evaluation.rubric_evaluator")
RubricEvaluator = rubric_mod.RubricEvaluator


# ============================================================================
# 1. WorkAuthGuard Tests
# ============================================================================

def test_work_auth_guard_blocks_no_sponsorship():
    guard = WorkAuthGuard()
    jd = "Candidates must be US Citizens or Green Card holders. No visa sponsorship provided now or in the future."
    res = guard.check(jd)
    assert res.has_blocker is True
    assert guard.has_blocker(jd) is True
    assert any("sponsorship" in reason.lower() for reason in res.reasons)


def test_work_auth_guard_blocks_us_citizen_only():
    guard = WorkAuthGuard()
    jd = "Due to federal contract regulations, this role is open to US Citizens only."
    res = guard.check(jd)
    assert res.has_blocker is True
    assert any("citizen" in reason.lower() for reason in res.reasons)


def test_work_auth_guard_blocks_security_clearance():
    guard = WorkAuthGuard()
    jd = "Active Top Secret / SCI clearance required prior to start date."
    res = guard.check(jd)
    assert res.has_blocker is True
    assert any("clearance" in reason.lower() for reason in res.reasons)


def test_work_auth_guard_allows_standard_jd():
    guard = WorkAuthGuard()
    jd = (
        "We are looking for a Senior .NET Engineer to build distributed microservices in AWS. "
        "Competitive salary, 401(k) matching, and comprehensive healthcare."
    )
    res = guard.check(jd)
    assert res.has_blocker is False
    assert guard.has_blocker(jd) is False
    assert len(res.reasons) == 0


def test_work_auth_guard_allows_explicit_sponsorship():
    guard = WorkAuthGuard()
    jd = "We sponsor H-1B transfers and green cards for qualified international candidates."
    res = guard.check(jd)
    assert res.has_blocker is False
    assert guard.has_blocker(jd) is False


def test_work_auth_guard_consensus_voting_clear_agreement():
    guard = WorkAuthGuard()
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps({
        "has_blocker": True,
        "confidence": 0.95,
        "reason": "Explicit restriction to US citizens"
    })
    jd = "Due to export controls, open to US Citizens only."
    res = guard.evaluate_consensus(jd, llm=mock_llm)
    assert res.has_blocker is True
    assert res.confidence_score >= 0.9
    assert res.consensus_votes is not None
    assert res.consensus_votes.get("rule_vote") is True
    assert res.consensus_votes.get("llm_vote") is True


def test_work_auth_guard_consensus_voting_llm_disambiguates():
    guard = WorkAuthGuard()
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps({
        "has_blocker": False,
        "confidence": 0.90,
        "reason": "Company does support STEM OPT and future sponsorship"
    })
    # Ambiguous phrase that might trigger a weak regex match or require clarification
    jd = "Candidates must be authorized to work in the US. We consider candidates with valid work authorization."
    res = guard.evaluate_consensus(jd, llm=mock_llm)
    assert res.has_blocker is False
    assert res.consensus_votes.get("llm_vote") is False


def test_work_auth_guard_consensus_voting_llm_failure_resilience():
    guard = WorkAuthGuard()
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("LLM Timeout")
    jd = "No visa sponsorship is provided."
    res = guard.evaluate_consensus(jd, llm=mock_llm)
    assert res.has_blocker is True
    assert res.consensus_votes.get("rule_vote") is True



# ============================================================================
# 2. GhostJobDetector Tests
# ============================================================================

def test_ghost_job_detector_flags_reposted_over_180_days():
    detector = GhostJobDetector()
    job = JobPosting(
        id="ghost_1",
        company="OldCo",
        title="Senior C# Developer",
        url="https://example.com/job/1",
    )
    report = detector.detect(job, days_open=210, repost_count=6)
    assert report.is_ghost_job is True
    assert report.legitimacy_score < 70
    assert any("180" in r or "days" in r.lower() for r in report.reasons)


def test_ghost_job_detector_flags_scam_markers():
    detector = GhostJobDetector()
    job = JobPosting(
        id="scam_1",
        company="Shady LLC",
        title=".NET Developer",
        url="https://example.com/job/2",
        description="Earn $180/hr remote! Send resume to hr-jobs-direct@gmail.com and interview via Telegram @recruiter123. Equipment check deposit required.",
    )
    report = detector.detect(job)
    assert report.is_scam is True
    assert report.is_ghost_job is True
    assert report.legitimacy_score <= 40
    assert any("gmail" in r.lower() or "telegram" in r.lower() or "deposit" in r.lower() for r in report.reasons)


def test_ghost_job_detector_passes_legitimate_job():
    detector = GhostJobDetector()
    job = JobPosting(
        id="legit_1",
        company="Capital One",
        title="Senior Software Engineer - .NET / AWS",
        url="https://capitalone.com/careers/1234",
        description="Join our Card Tech platform team building event-driven microservices in AWS ECS and .NET 8.",
    )
    report = detector.detect(job, days_open=14, repost_count=0)
    assert report.is_scam is False
    assert report.is_ghost_job is False
    assert report.legitimacy_score >= 85


# ============================================================================
# 3. FitScorer Tests
# ============================================================================

def test_fit_scorer_exact_match_mock():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps({
        "score": 95,
        "title": "Senior .NET Backend Engineer",
        "stack": ".NET 8, C#, AWS ECS, DynamoDB, Kafka",
        "location_remote": "Remote (US)",
        "reason": "Direct alignment with 10+ yrs .NET, AWS microservices, and event-driven systems.",
        "worth_applying": True
    })

    scorer = FitScorer(llm=mock_llm)
    res = scorer.score_job(
        title="Senior .NET Backend Engineer",
        description="Building enterprise microservices using C# .NET 8, DynamoDB and AWS ECS.",
        company="Capital One"
    )

    assert isinstance(res, FitScoreResult)
    assert res.score == 95.0
    assert res.worth_applying is True
    assert "alignment" in res.reason.lower()


def test_fit_scorer_markdown_json_parsing():
    mock_llm = MagicMock()
    # LLM returns markdown fenced JSON block
    mock_llm.generate.return_value = """```json
{
  "score": 88,
  "title": "Lead Software Engineer",
  "stack": "C#, ASP.NET Core, AWS, Kubernetes",
  "location_remote": "Chicago, IL (Hybrid)",
  "reason": "Strong match on backend C# and cloud architecture.",
  "worth_applying": true
}
```"""

    scorer = FitScorer(llm=mock_llm)
    res = scorer.score_job(title="Lead Software Engineer", description="C#, AWS, Kubernetes")
    assert res.score == 88.0
    assert res.worth_applying is True


def test_fit_scorer_hard_rule_penalties_in_prompt():
    """Verify that the FitScorer prompt template enforces hard penalties."""
    scorer = FitScorer()
    prompt = scorer._build_scoring_prompt(
        title="Data Science Director",
        description="Leading ML research team",
        company="AI Corp"
    )
    assert "data scientist" in prompt.lower()
    assert "35" in prompt
    assert "management" in prompt.lower() or "director" in prompt.lower()
    assert "30" in prompt


def test_fit_scorer_heuristic_fallback_on_llm_failure():
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = Exception("LLM connection timeout")

    scorer = FitScorer(llm=mock_llm)
    # Good backend C# / AWS role
    res = scorer.score_job(
        title="Senior .NET Core Software Engineer",
        description="Proficient with C#, ASP.NET Core, AWS Lambda, microservices architecture.",
        company="Enterprise Tech"
    )
    assert res.score >= 75.0
    assert res.worth_applying is True

    # Bad non-fit role (Data Scientist)
    res_ds = scorer.score_job(
        title="Principal Data Scientist & ML Researcher",
        description="Deep learning models with PyTorch, NLP research.",
        company="AI Lab"
    )
    assert res_ds.score <= 35.0
    assert res_ds.worth_applying is False


def test_fit_scorer_batch_scoring():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps([
        {
            "job_number": 1,
            "score": 92,
            "title": "Senior .NET Engineer",
            "stack": "C#, .NET 8, AWS",
            "location_remote": "Remote",
            "reason": "Exact stack match.",
            "worth_applying": True
        },
        {
            "job_number": 2,
            "score": 30,
            "title": "Engineering Director",
            "stack": "People Management, OKRs",
            "location_remote": "New York, NY",
            "reason": "Management track, not IC.",
            "worth_applying": False
        }
    ])

    scorer = FitScorer(llm=mock_llm)
    jobs = [
        JobPosting(id="j1", company="A", title="Senior .NET Engineer", url="https://a.com/1"),
        JobPosting(id="j2", company="B", title="Engineering Director", url="https://b.com/2")
    ]
    results = scorer.score_batch(jobs, min_score=85)
    assert len(results) == 2
    assert results[0].score == 92.0
    assert results[0].worth_applying is True
    assert results[1].score == 30.0
    assert results[1].worth_applying is False


def test_fit_scorer_with_graph_ontology_bridging():
    """Verify FitScorer leverages GraphRetriever to recognize transferable skills without docking score."""
    mock_retriever = MagicMock()
    mock_retriever.bridge_skill_gaps.return_value = {
        "direct_matches": ["AWS", ".NET"],
        "transferable_bridges": [{
            "target_skill": "RabbitMQ",
            "category": "DistributedMessaging",
            "bridging_skills": ["Kafka", "Amazon MSK"],
            "bridging_statement": "Verified mastery of Distributed Messaging via Kafka."
        }],
        "unmatched_gaps": []
    }

    scorer = FitScorer(llm=None, retriever=mock_retriever)
    # Force heuristic fallback: FitScorer.__init__ does `self.llm = llm or get_gateway()`,
    # so a real LLM would be used if configured. Patch it to raise, exercising the
    # retriever-bridging path the test asserts on.
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("forced fallback for test")
    scorer.llm = mock_llm
    res = scorer.score_job(
        title="Senior Distributed Systems Engineer",
        description="Seeking engineer experienced with C#, AWS, and RabbitMQ message streaming.",
        company="Fintech Org"
    )

    assert res.score >= 80.0
    assert "Transferable" in res.stack or "RabbitMQ" in res.reason
    assert "bridges" in res.reason.lower() or "transferable" in res.reason.lower()



# ============================================================================
# 4. RubricEvaluator (7-Block A-G) Tests
# ============================================================================

def test_rubric_evaluator_full_7_blocks():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = json.dumps({
        "fit_score": 93.0,
        "reason": "Outstanding alignment with senior .NET / AWS microservices stack.",
        "block_a": {
            "title": "Senior .NET Core Engineer",
            "domain": "Fintech / Payments",
            "tech_stack": [".NET 8", "C#", "AWS ECS", "Kafka", "DynamoDB"],
            "seniority_level": "Senior IC"
        },
        "block_b": {
            "match_score": 95.0,
            "matched_skills": [".NET 8", "C#", "AWS", "Kafka", "DynamoDB"],
            "missing_skills": ["Snowflake"],
            "gap_analysis": "Minor gap in Snowflake analytics which is easily mitigated."
        },
        "block_c": {
            "level_fit": "Exact match",
            "seniority_assessment": "Senior IC track matching 10+ years backend engineering."
        },
        "block_d": {
            "salary_range": "$160,000 - $190,000",
            "market_competitiveness": "Strong competitive range for US remote backend IC."
        },
        "block_e": {
            "pitch_angle": "Highlight Rocket Mortgage Bedrock intent router & ECS underwriting modernization.",
            "value_hook": "Proven track record cutting cloud costs by 40% with zero downtime."
        },
        "block_f": {
            "star_stories": [
                {
                    "situation": "Rocket Mortgage underwriting engine legacy monolith",
                    "action": "Modernized to AWS ECS Fargate .NET 8 microservices",
                    "result": "40% cost reduction, 99.95% uptime"
                }
            ]
        },
        "block_g": {
            "legitimacy_score": 98.0,
            "is_ghost_job": False,
            "work_auth_blocker": False,
            "notes": "Verified legitimate company posting."
        }
    })

    evaluator = RubricEvaluator(llm=mock_llm)
    job = JobPosting(
        id="job_capone",
        company="Capital One",
        title="Senior .NET Core Engineer",
        url="https://capitalone.com/careers/123",
        description="Join Capital One Card Tech. We build distributed C# .NET 8 services on AWS ECS with Kafka and DynamoDB.",
    )

    eval_res = evaluator.evaluate(job)
    assert isinstance(eval_res, EvaluationResult)
    assert eval_res.job_id == "job_capone"
    assert eval_res.fit_score == 93.0
    assert eval_res.score == 93.0
    assert eval_res.work_auth_blocker is False
    assert eval_res.is_ghost_job is False
    assert "block_a" in eval_res.block_scores
    assert "block_b" in eval_res.block_scores
    assert "block_c" in eval_res.block_scores
    assert "block_d" in eval_res.block_scores
    assert "block_e" in eval_res.block_scores
    assert "block_f" in eval_res.block_scores
    assert "block_g" in eval_res.block_scores


def test_rubric_evaluator_work_auth_blocker_overrides():
    mock_llm = MagicMock()
    evaluator = RubricEvaluator(llm=mock_llm)

    job = JobPosting(
        id="job_defense",
        company="Defense Tech",
        title="Senior .NET Engineer",
        url="https://defense.example.com/1",
        description="US Citizenship required due to DOD clearance. Absolutely no visa sponsorship.",
    )

    eval_res = evaluator.evaluate(job)
    assert eval_res.work_auth_blocker is True
    assert eval_res.fit_score <= 30.0
    assert "work authorization" in eval_res.reason.lower() or "sponsorship" in eval_res.reason.lower()


def test_rubric_evaluator_ghost_job_flags():
    mock_llm = MagicMock()
    evaluator = RubricEvaluator(llm=mock_llm)

    job = JobPosting(
        id="job_scam",
        company="Phantom Services",
        title="Remote .NET C# Engineer",
        url="https://phantom.example.com/2",
        description="Earn $150/hr immediately. Send CV to hr@gmail.com and message @telegram_bot for check deposit.",
    )

    eval_res = evaluator.evaluate(job)
    assert eval_res.is_ghost_job is True
    assert eval_res.fit_score <= 30.0


def test_rubric_evaluator_fallback_heuristic():
    mock_llm = MagicMock()
    mock_llm.generate.side_effect = RuntimeError("Provider down")

    evaluator = RubricEvaluator(llm=mock_llm)
    job = JobPosting(
        id="job_fallback",
        company="Fidelity",
        title="Senior Backend Engineer - C# / AWS",
        url="https://fidelity.com/jobs/999",
        description="Seeking Senior Software Engineer with strong C#, .NET Core, AWS, and relational database skills.",
    )

    eval_res = evaluator.evaluate(job)
    assert isinstance(eval_res, EvaluationResult)
    assert eval_res.fit_score >= 70.0
    assert eval_res.work_auth_blocker is False
    assert "block_a" in eval_res.block_scores
    assert "block_g" in eval_res.block_scores
