"""7-Block (A-G) Rubric Evaluator for CareerGraph AI."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from src.core.gateway.facade import LLMGateway, get_gateway
from src.core.models import EvaluationResult, JobPosting
from .ghost_job_detector import GhostJobDetector, GhostJobReport
from .scorer import CANDIDATE_PROFILE_TEXT, FitScorer
from .work_auth_guard import WorkAuthGuard, WorkAuthResult

logger = logging.getLogger(__name__)


class RubricEvaluator:
    """Performs deep 7-Block (A-G) structured evaluation of job postings."""

    def __init__(
        self,
        llm: Optional[Any] = None,
        work_auth_guard: Optional[WorkAuthGuard] = None,
        ghost_job_detector: Optional[GhostJobDetector] = None,
        fit_scorer: Optional[FitScorer] = None,
    ) -> None:
        self.llm = llm or get_gateway()
        self.work_auth_guard = work_auth_guard or WorkAuthGuard()
        self.ghost_job_detector = ghost_job_detector or GhostJobDetector()
        self.fit_scorer = fit_scorer or FitScorer(llm=self.llm)

    def _clean_json_str(self, text: str) -> str:
        """Extract and clean valid JSON substring from LLM response text."""
        if not text:
            return "{}"
        cleaned = text.strip()
        # Extract balanced json block if present
        match = re.search(r"(\{[\s\S]*\})", cleaned)
        if match:
            cleaned = match.group(1).strip()
        else:
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        return cleaned.strip()

    def _build_rubric_prompt(self, job: JobPosting, master_resume: Optional[str] = None) -> str:
        resume_summary = master_resume or CANDIDATE_PROFILE_TEXT
        return f"""You are performing a comprehensive 7-Block (A through G) candidate-to-job evaluation.
Output ONLY a valid JSON object matching the schema below.

CANDIDATE PROFILE:
{resume_summary}

JOB POSTING:
Company: {job.company}
Title: {job.title}
Location: {job.location or 'US / Remote'}
URL: {job.url}
Description:
{job.description or ''}

EVALUATION RUBRIC — 7 BLOCKS:
Block A: Role Summary & Domain (Role title, company, business domain, tech stack summary, remote/onsite policy)
Block B: CV & Skills Match (Match score 0-100, matched skills list, missing skills list, gap analysis)
Block C: Seniority & Leveling Strategy (Level fit: Exact Match/Mismatch, leveling assessment, scope)
Block D: Compensation Analysis (Extracted/estimated salary range, market competitiveness, location tier)
Block E: Personalization Angle & Pitch (Tailored pitch angle, key value hook, why candidate fits this team)
Block F: STAR+R Behavioral Story Match Mapping (1-3 relevant stories from candidate's experience mapped to JD requirements)
Block G: Legitimacy & Safety Check (Posting legitimacy assessment, ghost-job risk, work authorization check)

Output JSON structure:
{{
  "fit_score": 0-100,
  "reason": "Executive summary of evaluation",
  "block_a": {{
    "title": "{job.title}",
    "domain": "e.g., Fintech / Cloud SaaS",
    "tech_stack": [".NET 8", "C#", "AWS ECS", "Kafka"],
    "seniority_level": "Senior IC"
  }},
  "block_b": {{
    "match_score": 0-100,
    "matched_skills": ["C#", ".NET Core", "AWS"],
    "missing_skills": ["Optional missing tool"],
    "gap_analysis": "Assessment of technical overlap"
  }},
  "block_c": {{
    "level_fit": "Exact match",
    "seniority_assessment": "Senior IC track matching 10+ years backend engineering"
  }},
  "block_d": {{
    "salary_range": "$150,000 - $190,000",
    "market_competitiveness": "Competitive for US Senior Backend IC"
  }},
  "block_e": {{
    "pitch_angle": "Focus on AWS cloud cost reduction (40%) and Bedrock AI intent router",
    "value_hook": "Proven high-throughput distributed systems experience"
  }},
  "block_f": {{
    "star_stories": [
      {{
        "situation": "Rocket Mortgage underwriting engine legacy monolith",
        "action": "Modernized to AWS ECS Fargate .NET 8 microservices",
        "result": "40% cost reduction, 99.95% uptime"
      }}
    ]
  }},
  "block_g": {{
    "legitimacy_score": 95.0,
    "is_ghost_job": false,
    "work_auth_blocker": false,
    "notes": "Verified company posting"
  }}
}}

Output ONLY the JSON object."""

    def _fallback_blocks(
        self,
        job: JobPosting,
        fit_score: float,
        reason: str,
        work_auth: WorkAuthResult,
        ghost_report: GhostJobReport,
    ) -> Dict[str, Any]:
        """Generate structured 7-block dictionary when LLM is unavailable."""
        return {
            "block_a": {
                "title": job.title,
                "domain": "Enterprise Software / Cloud",
                "tech_stack": [".NET 8", "C#", "AWS", "Microservices"],
                "seniority_level": "Senior IC",
            },
            "block_b": {
                "match_score": fit_score,
                "matched_skills": ["C#", ".NET Core", "AWS ECS", "Microservices", "REST APIs"],
                "missing_skills": [],
                "gap_analysis": "Solid technical overlap with backend engineering requirements.",
            },
            "block_c": {
                "level_fit": "Senior IC Fit",
                "seniority_assessment": "10+ years backend systems experience matches requirements.",
            },
            "block_d": {
                "salary_range": "$140,000 - $185,000",
                "market_competitiveness": "Standard market rate for US backend roles.",
            },
            "block_e": {
                "pitch_angle": "Highlight Rocket Mortgage AWS ECS modernization and microservices architecture.",
                "value_hook": "Proven track record cutting cloud costs by 40% with high concurrency.",
            },
            "block_f": {
                "star_stories": [
                    {
                        "situation": "Rocket Mortgage Underwriting Engine cloud modernization",
                        "action": "Migrated to AWS ECS Fargate .NET Core with DynamoDB single-table design",
                        "result": "40% infrastructure cost reduction with 99.95% uptime",
                    },
                    {
                        "situation": "London Computer Systems enterprise payment gateway",
                        "action": "Engineered idempotent payment processing with exponential backoff",
                        "result": "100% failover resilience with zero financial ledger corruption",
                    },
                ]
            },
            "block_g": {
                "legitimacy_score": ghost_report.legitimacy_score,
                "is_ghost_job": ghost_report.is_ghost_job,
                "work_auth_blocker": work_auth.has_blocker,
                "notes": (
                    "; ".join(work_auth.reasons + ghost_report.reasons)
                    if (work_auth.reasons or ghost_report.reasons)
                    else "Legitimate posting verified."
                ),
            },
        }

    def _evaluate_with_rules(self, job: JobPosting, master_resume: Optional[str] = None) -> EvaluationResult:
        """Internal worker executing 7-Block evaluation via LLM or rule-based fallback."""
        desc = job.description or ""
        work_auth = self.work_auth_guard.check(desc)
        if work_auth.has_blocker:
            return EvaluationResult(
                id=f"eval_{uuid4().hex[:12]}",
                job_id=job.id,
                fit_score=0.0,
                score=0.0,
                technical_score=0.0,
                passed=False,
                work_auth_blocker=True,
                reason=f"Hard knockout: Work authorization / Clearance blocker: {'; '.join(work_auth.reasons)}",
                block_scores={
                    "block_g": {
                        "legitimacy_score": 0.0,
                        "is_ghost_job": False,
                        "work_auth_blocker": True,
                        "notes": "; ".join(work_auth.reasons),
                    }
                },
                created_at=datetime.utcnow().isoformat(),
                evaluated_at=datetime.utcnow(),
            )

        ghost_report = self.ghost_job_detector.detect(job)
        fit_score = 0.0
        reason = ""
        block_scores: Dict[str, Any] = {}

        try:
            prompt = self._build_rubric_prompt(job, master_resume)
            raw_res = self.llm.generate(prompt=prompt, json_mode=True)
            cleaned = self._clean_json_str(raw_res)
            data = json.loads(cleaned)

            fit_score = float(data.get("fit_score", 0.0))
            reason = data.get("reason", "7-Block evaluation completed.")

            block_scores = {
                "block_a": data.get("block_a", {}),
                "block_b": data.get("block_b", {}),
                "block_c": data.get("block_c", {}),
                "block_d": data.get("block_d", {}),
                "block_e": data.get("block_e", {}),
                "block_f": data.get("block_f", {}),
                "block_g": data.get("block_g", {}),
            }
        except Exception as exc:
            logger.warning("RubricEvaluator LLM generation failed (%s); using fallback rubric.", exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="evaluation",
                    component="rubric_evaluator",
                    error_type="LLM_FALLBACK",
                    message=f"RubricEvaluator LLM generation failed: {exc}. Using fallback rubric.",
                    company=getattr(job, "company", None),
                    metadata={"job_id": getattr(job, "id", None)},
                )
            except Exception:
                pass
            score_res = self.fit_scorer.score_job(
                title=job.title,
                description=desc,
                company=job.company,
                location=job.location,
            )
            fit_score = score_res.score
            reason = score_res.reason
            block_scores = self._fallback_blocks(job, fit_score, reason, work_auth, ghost_report)

        # Guardrail Enforcement & Score Overrides
        if work_auth.has_blocker:
            fit_score = min(fit_score, 30.0)
            reason = f"Work authorization blocker: {'; '.join(work_auth.reasons)}"
            if "block_g" in block_scores:
                block_scores["block_g"]["work_auth_blocker"] = True

        if ghost_report.is_ghost_job:
            fit_score = min(fit_score, 30.0)
            if not work_auth.has_blocker:
                reason = f"Ghost job / Scam warning: {'; '.join(ghost_report.reasons)}"
            if "block_g" in block_scores:
                block_scores["block_g"]["is_ghost_job"] = True
                block_scores["block_g"]["legitimacy_score"] = ghost_report.legitimacy_score

        if "block_g" not in block_scores or not block_scores["block_g"]:
            block_scores["block_g"] = {
                "legitimacy_score": ghost_report.legitimacy_score,
                "is_ghost_job": ghost_report.is_ghost_job,
                "work_auth_blocker": work_auth.has_blocker,
                "notes": "; ".join(work_auth.reasons + ghost_report.reasons),
            }
        else:
            block_scores["block_g"]["work_auth_blocker"] = work_auth.has_blocker
            block_scores["block_g"]["is_ghost_job"] = ghost_report.is_ghost_job or block_scores["block_g"].get("is_ghost_job", False)

        return EvaluationResult(
            id=f"eval_{uuid4().hex[:12]}",
            job_id=job.id,
            fit_score=fit_score,
            score=fit_score,
            reason=reason,
            block_scores=block_scores,
            work_auth_blocker=work_auth.has_blocker,
            is_ghost_job=ghost_report.is_ghost_job,
            evaluated_at=datetime.utcnow(),
        )

    def evaluate(self, job: JobPosting, master_resume: Optional[str] = None) -> EvaluationResult:
        """Run full 7-Block evaluation with early-applicant recency boost."""
        desc = job.description or ""
        title_lower = (job.title or "").lower()

        # Hard Knockout 1: PhD / Doctorate academic requirement
        if any(p in title_lower for p in ["phd", "ph.d", "doctorate", "doctoral", "postdoc", "post-doc"]):
            return EvaluationResult(
                id=f"eval_{uuid4().hex[:12]}",
                job_id=job.id,
                fit_score=0.0,
                technical_score=0.0,
                passed=False,
                reason="Hard knockout: Role requires a PhD / academic doctorate, which candidate does not possess.",
                blocks={"block_c": {"level_fit": "Disqualified", "seniority_assessment": "Mandatory PhD requirement not met."}},
                created_at=datetime.utcnow().isoformat(),
            )

        # Hard Knockout 2: Student / Intern / New Grad position
        if any(p in title_lower for p in ["intern", "internship", "co-op", "coop", "working student", "student", "fellowship", "new grad", "university grad", "entry level", "campus"]):
            return EvaluationResult(
                id=f"eval_{uuid4().hex[:12]}",
                job_id=job.id,
                fit_score=0.0,
                technical_score=0.0,
                passed=False,
                reason="Hard knockout: Candidate is a 10+ year Senior IC, disqualified from student/intern/new-grad roles.",
                blocks={"block_c": {"level_fit": "Disqualified", "seniority_assessment": "Student/Intern position."}},
                created_at=datetime.utcnow().isoformat(),
            )

        # Execute evaluation rules
        eval_res = self._evaluate_with_rules(job, master_resume=master_resume)

        # Early-Applicant Recency Boost Calculation
        recency_boost = 0.0
        posting_age_hours = None

        if job.posted_at:
            now_utc = datetime.now(timezone.utc)
            posted_utc = job.posted_at if job.posted_at.tzinfo else job.posted_at.replace(tzinfo=timezone.utc)
            age_sec = (now_utc - posted_utc).total_seconds()
            posting_age_hours = max(0.0, age_sec / 3600.0)

            if not eval_res.work_auth_blocker and not eval_res.is_ghost_job and eval_res.fit_score >= 40.0:
                if posting_age_hours <= 24.0:
                    recency_boost = 10.0
                elif posting_age_hours <= 72.0:
                    recency_boost = 5.0

        if recency_boost > 0:
            eval_res.fit_score = min(100.0, eval_res.fit_score + recency_boost)
            eval_res.score = eval_res.fit_score

        if eval_res.block_scores is not None and isinstance(eval_res.block_scores, dict):
            eval_res.block_scores["recency_boost"] = recency_boost
            if posting_age_hours is not None:
                eval_res.block_scores["posting_age_hours"] = round(posting_age_hours, 1)

        return eval_res
