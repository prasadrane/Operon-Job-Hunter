"""Application Q&A generator for open-ended ATS and portal questions."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.core.gateway.facade import LLMGateway, get_gateway
from src.core.models import JobPosting

logger = logging.getLogger(__name__)


def adapt_brain_answer(answer: str) -> str:
    """v2 tailor answers are JSON plans; QAGenerator consumes prose (spec P1)."""
    from src.brain.tailor_schema import parse_tailor_plan
    from src.brain.validator import plan_to_prose
    plan = parse_tailor_plan(answer)
    return plan_to_prose(plan) if plan is not None else answer


class QAGenerator:
    """Generates precise, high-impact responses for standard and custom job application form questions."""

    def __init__(
        self,
        llm: Optional[LLMGateway] = None,
        retriever: Optional[Any] = None,
        brain: Optional[Any] = None,
    ) -> None:
        self._llm = llm
        self.retriever = retriever
        self._brain = brain

    @property
    def llm(self) -> LLMGateway:
        if self._llm is None:
            self._llm = get_gateway()
        return self._llm

    @property
    def brain(self) -> Optional[Any]:
        # _llm guard preserved: an explicitly-injected LLM means gateway-first, no brain
        if self._brain is None and self._llm is None:
            from src.brain.factory import get_brain
            self._brain = get_brain()
        return self._brain

    def generate_answers(
        self,
        job: JobPosting,
        custom_questions: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """Generate a dictionary of application questions and tailored responses."""
        company = job.company or "the company"
        title = job.title or "Senior Software Engineer"
        desc = job.description or ""

        # Baseline standard answer templates grounded in Alex's profile
        answers: Dict[str, str] = {
            "why_us": (
                f"I am eager to join {company} as a {title} because of your commitment to building high-performance, "
                f"mission-critical software at scale. With over a decade of experience modernizing enterprise distributed "
                f"systems on AWS and .NET Core, I am excited to contribute directly to {company}'s platform reliability "
                f"and engineering velocity."
            ),
            "technical_challenge": (
                "At Rocket Mortgage, our high-volume transaction service suffered intermittent 10-15s stalls under peak load. "
                "I analyzed low-level thread dumps using WinDbg and dotnet-counters to isolate a third-party locking bottleneck, "
                "then designed a SemaphoreSlim-based throttling mechanism that restored 99.99% availability under 50k+ daily transactions."
            ),
            "work_authorization": (
                "Currently on an active H-1B visa with an approved I-140 petition. Does not require the H-1B lottery for transfer."
            ),
            "notice_period": "2 weeks standard notice.",
            "salary_expectation": "$160,000 - $185,000 base salary (flexible based on total compensation and equity structure).",
            "remote_preference": "Open to Remote (US-wide) or Hybrid (Chicago/Midwest).",
        }

        # If custom questions are provided, attempt Career Brain or LLM completion
        if custom_questions:
            for q in custom_questions:
                if not q.strip():
                    continue
                q_clean = q.strip()
                ans = self._answer_custom_question(q_clean, company, title, desc)
                answers[q_clean] = ans

        return answers

    def _answer_custom_question(self, question: str, company: str, title: str, job_desc: str) -> str:
        """Answer a custom open-ended question using Career Brain or candidate context."""
        q_lower = question.lower()

        # 1. Profile Fact Pinning for direct identity/status questions
        if any(term in q_lower for term in ["work authorization", "visa status", "sponsorship", "require visa", "authorized to work"]):
            return "Currently authorized to work in the United States on an active H-1B visa with an approved I-140 petition. Does not require the H-1B lottery for transfer."
        if any(term in q_lower for term in ["notice period", "how soon can you start", "start date", "availability"]):
            return "2 weeks standard notice from offer acceptance."
        if any(term in q_lower for term in ["salary expectation", "compensation", "desired salary"]):
            return "$160,000 - $185,000 base salary (flexible based on total compensation and equity structure)."

        # 2. Try Career Brain first for grounded first-person answers
        if self.brain:
            try:
                res = self.brain.query(query=question, mode="tailoring", job_desc=job_desc)
                res.answer = adapt_brain_answer(res.answer)
                if res and res.answer and "I don't have that information" not in res.answer:
                    return res.answer.strip()
            except Exception as exc:
                logger.warning("Career Brain query failed on '%s', falling back: %s", question, exc)

        # 3. GraphRetriever fallback context
        grounded_proof_text = ""
        fallback_grounded_answer = ""
        if self.retriever and hasattr(self.retriever, "retrieve_causal_paths"):
            tokens = [w for w in question.replace("?", " ").split() if len(w) >= 3]
            paths = self.retriever.retrieve_causal_paths(tokens, max_paths=1)
            if paths:
                p = paths[0]
                grounded_proof_text = f"\nVERIFIED GRAPH EVIDENCE:\n- Story/Role: {p.get('company', 'Rocket Mortgage')}\n- Action: {p.get('action')}\n- Business Metric Impact: {', '.join(p.get('metric', []))}\n"
                metric_str = ", ".join(p.get('metric', [])) or "high reliability"
                fallback_grounded_answer = (
                    f"At {p.get('company', 'Rocket Mortgage')}, I {p.get('action')}, "
                    f"achieving verified impact ({metric_str}). I look forward to applying this same rigorous approach at {company}."
                )

        prompt = (
            f"You are Alex Rivera, a Senior Software Engineer with 10+ years of experience in C#/.NET Core, AWS, Kafka, and microservices.\n"
            f"Candidate profile facts:\n"
            f"- Master of Science in Information Systems (Univ. of Cincinnati)\n"
            f"- Approved I-140 petition, active H-1B\n"
            f"- Experience at Rocket Mortgage (AWS ECS, Bedrock GenAI intent router, Kafka governance, Dynatrace observability)\n"
            f"- Experience at London Computer Systems (.NET, SQL Server optimization, payment gateway integration)\n"
            f"{grounded_proof_text}\n"
            f"Target Company: {company}\n"
            f"Target Role: {title}\n"
            f"Job Description Excerpt: {job_desc[:500]}\n\n"
            f"Please write a concise (2-4 sentence), professional answer to this application question:\n"
            f"Question: '{question}'\n\n"
            f"Return ONLY the response text."
        )

        try:
            res = self.llm.generate(prompt=prompt, temperature=0.2).strip()
            # If response is JSON, extract string
            if res.startswith("{") and res.endswith("}"):
                try:
                    parsed = json.loads(res)
                    if isinstance(parsed, dict) and question in parsed:
                        return parsed[question]
                    if isinstance(parsed, dict) and len(parsed) == 1:
                        return list(parsed.values())[0]
                except Exception:
                    pass
            return res.strip('"')
        except Exception as exc:
            logger.warning("Custom question LLM answering failed for '%s': %s", question, exc)
            if fallback_grounded_answer:
                return fallback_grounded_answer
            return (
                f"With 10+ years of software engineering experience in cloud-native microservices, AWS, and .NET Core, "
                f"I bring verified expertise in building resilient backend platforms that scale."
            )

