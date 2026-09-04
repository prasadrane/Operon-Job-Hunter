"""0-100 Fit Scorer for CareerGraph AI following Alex's exact rubric."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

from src.core.config import get_settings
from src.core.gateway.facade import LLMGateway, get_gateway
from src.core.models import JobPosting
from src.core.persona import SAMPLE_FULL_NAME, SAMPLE_PROFILE_SUMMARY, SAMPLE_SKILLS

logger = logging.getLogger(__name__)


CANDIDATE_PROFILE_TEXT = f"""- {SAMPLE_FULL_NAME} (6+ years experience)
- Senior / Staff Backend Software Engineer (Individual Contributor Track).
- Core Mastery: {', '.join(SAMPLE_SKILLS)}.
- Summary: {SAMPLE_PROFILE_SUMMARY}
- NOT suitable: Director / VP / Management tracks (IC track only), Pure Data Science / ML researcher, Frontend-only, Mobile-only (iOS/Android), Non-US locations."""

RESUME_SUMMARY_TEXT = f"{SAMPLE_FULL_NAME} is a Senior Backend Engineer with 6+ years building high-throughput event pipelines and API services in Python (FastAPI, Django). Track record: 40M events/day ingestion platform, payments idempotency rework, Kubernetes migration, and latency cuts measured in p95. Strong on PostgreSQL, Kafka, Redis, AWS."


class FitScoreResult(BaseModel):
    """Result of 0-100 Fit Scoring."""

    score: float = 0.0
    reason: str = ""
    worth_applying: bool = False
    title: Optional[str] = None
    stack: Optional[str] = None
    location_remote: Optional[str] = None
    raw_response: Optional[Dict[str, Any]] = None


class FitScorer:
    """Evaluates job descriptions against candidate profile using 0-100 rubric."""

    NON_US_MARKERS = [
        "germany", "france", "uk", "united kingdom", "india", "netherlands",
        "spain", "italy", "poland", "romania", "ireland", "belgium", "austria",
        "switzerland", "sweden", "norway", "denmark", "finland", "portugal",
        "czech", "hungary", "greece", "brazil", "mexico", "china", "japan",
        "singapore", "australia", "new zealand", "south africa", "dubai",
        "f/m/d", "m/f/d", "(hybrid, london", "(onsite, berlin",
    ]

    NON_FIT_PATTERNS = [
        ("data scientist", 35.0,
         "Data science / ML research is outside candidate's backend IC track."),
        ("data analyst", 35.0,
         "Data analyst role does not match senior backend engineering."),
        ("machine learning engineer", 35.0,
         "Pure ML engineering / model training role."),
        ("director", 40.0, "Director / management track; candidate is Senior IC."),
        ("vice president", 40.0, "VP track; candidate is Senior IC."),
        ("vp ", 40.0, "VP track; candidate is Senior IC."),
        ("head of", 40.0, "Executive / Head of role; candidate is Senior IC."),
        ("managing director", 40.0, "Executive management track."),
        ("frontend", 35.0, "Frontend-only role; candidate is backend/distributed systems specialist."),
        ("ios", 35.0, "Mobile iOS role outside candidate's cloud backend focus."),
        ("android", 35.0, "Mobile Android role outside candidate's cloud backend focus."),
        ("ui/ux", 35.0, "Design / UI/UX role."),
    ]

    def __init__(self, llm: Optional[Any] = None, retriever: Optional[Any] = None) -> None:
        self.llm = llm or get_gateway()
        self.retriever = retriever
        self.min_score = get_settings().min_fit_score

    def _build_scoring_prompt(
        self,
        title: str,
        description: str,
        company: Optional[str] = None,
        location: Optional[str] = None,
        min_score: Optional[int] = None,
    ) -> str:
        threshold = min_score if min_score is not None else self.min_score
        job_info = f"Company: {company or 'Unknown'}\nTitle: {title}\nLocation: {location or 'US / Remote'}\nDescription:\n{description}"

        prompt = f"""You are evaluating job postings for a candidate. Output ONLY a JSON object, no other text.

CANDIDATE:
{CANDIDATE_PROFILE_TEXT}

RESUME SUMMARY:
{RESUME_SUMMARY_TEXT}

JOB TO SCORE:
{job_info}

STRICT SCORING RUBRIC — follow these ranges exactly:

90-100: EXACT match. Role is senior/staff/lead .NET/C#/ASP.NET Core backend or AWS-native backend (ECS/Lambda/DynamoDB). US or Remote. Stack directly matches resume.

75-89: STRONG overlap. Role is senior backend/platform engineer. Primary stack may differ slightly (e.g., Java instead of .NET) but same domain (cloud, microservices, enterprise). US or Remote.

60-74: PARTIAL overlap. Role is backend/engineering but significant gaps (wrong stack, different seniority, or partial skill match).

40-59: WEAK overlap. Some engineering relevance but major mismatch in role type, stack, or level.

20-39: WRONG fit. Role is in a different function (data science, ML/AI research, frontend-only, mobile, DevOps-only, QA, director/VP/management, sales, recruiting, designer).

0-19: NO relevance. Completely unrelated role or location.

HARD RULES — these override everything else:
- Data scientist, ML engineer, AI researcher, data analyst roles: MAX score 35 regardless of company
- Director, VP, "Head of", "Managing Director" roles: MAX score 40 regardless of company (candidate is senior IC track, not management)
- Frontend-only, mobile (iOS/Android), UI/UX roles: MAX score 35
- Non-US locations (EU, India, etc.): MAX score 30 regardless of role fit
- If a role has NO overlap with .NET/C#/AWS/backend/cloud: MAX score 40

Output format:
{{
  "score": 0-100,
  "title": "{title}",
  "stack": "key tech from JD (comma-separated, max 6 items)",
  "location_remote": "location + remote policy",
  "reason": "one sentence why this fits or doesn't fit the candidate",
  "worth_applying": true/false
}}

Set worth_applying=true only if score >= {threshold}.
Output ONLY valid JSON."""
        return prompt

    def _clean_json_str(self, text: str) -> str:
        """Strip markdown fences and whitespace from LLM output."""
        cleaned = text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()

    def _heuristic_score(
        self,
        title: str,
        description: str,
        company: Optional[str] = None,
        location: Optional[str] = None,
        min_score: Optional[int] = None,
    ) -> FitScoreResult:
        """Heuristic rule-based fallback scoring when LLM is unavailable."""
        threshold = min_score if min_score is not None else self.min_score
        full_text = f"{title} {company or ''} {location or ''} {description}".lower()
        title_lower = title.lower()

        # Check non-US location
        for loc in self.NON_US_MARKERS:
            if loc in full_text:
                return FitScoreResult(
                    score=25.0,
                    reason=f"Non-US location detected ({loc}). Candidate is based in US.",
                    worth_applying=False,
                    title=title,
                )

        # Check hard penalties
        for pattern, max_score, penalty_reason in self.NON_FIT_PATTERNS:
            if pattern in title_lower:
                return FitScoreResult(
                    score=max_score,
                    reason=penalty_reason,
                    worth_applying=False,
                    title=title,
                )

        # Calculate positive keyword affinity
        score = 50.0
        matched_stack = []

        # Strong positive signals (.NET / C#)
        if any(k in full_text for k in [".net", "c#", "csharp", "asp.net"]):
            score += 25.0
            matched_stack.append("C#/.NET")

        # Cloud / AWS
        if any(k in full_text for k in ["aws", "amazon web services", "ecs", "lambda", "dynamodb"]):
            score += 15.0
            matched_stack.append("AWS")

        # Microservices / Distributed backend
        if any(k in full_text for k in ["microservices", "distributed systems", "event-driven", "kafka"]):
            score += 10.0
            matched_stack.append("Microservices/Kafka")

        # Ontology-aware skill gap bridging boost
        bridging_notes = []
        if self.retriever and hasattr(self.retriever, "bridge_skill_gaps"):
            raw_tokens = re.findall(r"\b[A-Za-z0-9+#\.-]{2,}\b", f"{title} {description}")
            gap_analysis = self.retriever.bridge_skill_gaps(raw_tokens[:25])
            if gap_analysis.get("transferable_bridges"):
                score += 8.0  # Ontology boost for adjacent domain mastery
                for b in gap_analysis["transferable_bridges"][:2]:
                    bridging_notes.append(f"{b['target_skill']} ➔ {', '.join(b['bridging_skills'][:2])} ({b['category']})")
                matched_stack.append("Transferable:" + "/".join([b["target_skill"] for b in gap_analysis["transferable_bridges"][:2]]))

        # Seniority match
        if any(k in title_lower for k in ["senior", "sr", "staff", "lead", "principal"]):
            score += 5.0

        final_score = min(95.0, max(15.0, score))
        worth = final_score >= threshold
        stack_str = ", ".join(matched_stack) if matched_stack else "General Backend"
        reason = f"Heuristic match: {stack_str} alignment with backend IC track."
        if bridging_notes:
            reason += f" Transferable bridges: {'; '.join(bridging_notes)}."

        return FitScoreResult(
            score=final_score,
            reason=reason,
            worth_applying=worth,
            title=title,
            stack=stack_str,
            location_remote=location or "US / Remote",
        )


    def score_job(
        self,
        title: str,
        description: str,
        company: Optional[str] = None,
        location: Optional[str] = None,
        min_score: Optional[int] = None,
    ) -> FitScoreResult:
        """Score a single job posting against candidate profile."""
        prompt = self._build_scoring_prompt(
            title=title,
            description=description,
            company=company,
            location=location,
            min_score=min_score,
        )

        try:
            raw_res = self.llm.generate(prompt=prompt, json_mode=True)
            cleaned = self._clean_json_str(raw_res)
            data = json.loads(cleaned)

            # Handle if array returned
            if isinstance(data, list) and len(data) > 0:
                data = data[0]

            score = float(data.get("score", 0.0))
            threshold = min_score if min_score is not None else self.min_score
            worth = bool(data.get("worth_applying", score >= threshold))

            return FitScoreResult(
                score=score,
                reason=data.get(
                    "reason", "Evaluated against candidate profile."),
                worth_applying=worth,
                title=data.get("title", title),
                stack=data.get("stack", ""),
                location_remote=data.get(
                    "location_remote", location or "US / Remote"),
                raw_response=data,
            )
        except Exception as exc:
            logger.warning(
                "FitScorer LLM generation failed (%s); using heuristic fallback.", exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="evaluation",
                    component="fit_scorer",
                    error_type="LLM_FALLBACK",
                    message=f"FitScorer LLM generation failed: {exc}. Using heuristic fallback.",
                )
            except Exception:
                pass
            return self._heuristic_score(
                title=title,
                description=description,
                company=company,
                location=location,
                min_score=min_score,
            )

    def score_batch(
        self,
        jobs: List[JobPosting],
        min_score: Optional[int] = None,
    ) -> List[FitScoreResult]:
        """Score multiple jobs sequentially or in batch."""
        if not jobs:
            return []

        # Attempt batch LLM call
        threshold = min_score if min_score is not None else self.min_score
        jobs_text_list = []
        for i, j in enumerate(jobs, start=1):
            jobs_text_list.append(
                f"Job {i}:\nCompany: {j.company}\nTitle: {j.title}\nLocation: {j.location or 'US/Remote'}\nDescription:\n{j.description or ''}"
            )
        jobs_text = "\n---\n".join(jobs_text_list)

        prompt = f"""You are evaluating job postings for a candidate. Output ONLY a JSON array, no other text.

CANDIDATE:
{CANDIDATE_PROFILE_TEXT}

RESUME SUMMARY:
{RESUME_SUMMARY_TEXT}

JOBS TO SCORE:
{jobs_text}

STRICT SCORING RUBRIC — follow these ranges exactly:
90-100: EXACT match. Senior/staff/lead .NET/C#/ASP.NET Core backend or AWS-native backend.
75-89: STRONG overlap. Senior backend/platform engineer.
60-74: PARTIAL overlap. Backend/engineering but significant gaps.
40-59: WEAK overlap. Major mismatch in role type, stack, or level.
20-39: WRONG fit. Different function (data science, ML/AI research, frontend, mobile, management).
0-19: NO relevance.

For each job output:
{{
  "job_number": 1,
  "score": 0-100,
  "title": "extracted job title",
  "stack": "key tech from JD (comma-separated)",
  "location_remote": "location + remote policy",
  "reason": "one sentence why this fits or doesn't fit",
  "worth_applying": true/false
}}

Set worth_applying=true only if score >= {threshold}.
Include ALL {len(jobs)} jobs. Output ONLY the JSON array."""

        try:
            raw_res = self.llm.generate(prompt=prompt, json_mode=True)
            cleaned = self._clean_json_str(raw_res)
            data = json.loads(cleaned)

            if isinstance(data, list) and len(data) == len(jobs):
                results = []
                for item, job in zip(data, jobs):
                    sc = float(item.get("score", 0.0))
                    results.append(
                        FitScoreResult(
                            score=sc,
                            reason=item.get("reason", ""),
                            worth_applying=bool(
                                item.get("worth_applying", sc >= threshold)),
                            title=item.get("title", job.title),
                            stack=item.get("stack", ""),
                            location_remote=item.get(
                                "location_remote", job.location or ""),
                            raw_response=item,
                        )
                    )
                return results
        except Exception as exc:
            logger.warning(
                "FitScorer batch LLM call failed (%s); falling back to single scoring.", exc)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="evaluation",
                    component="fit_scorer",
                    error_type="LLM_BATCH_ERROR",
                    message=f"FitScorer batch LLM call failed: {exc}. Falling back to single scoring.",
                )
            except Exception:
                pass

        # Fallback to single job scoring
        return [
            self.score_job(
                title=j.title,
                description=j.description or "",
                company=j.company,
                location=j.location,
                min_score=min_score,
            )
            for j in jobs
        ]
