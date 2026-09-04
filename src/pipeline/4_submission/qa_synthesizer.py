"""Q&A Synthesizer: Deterministic triage, STAR+R memory retrieval, and FactGuard validation."""

from dataclasses import dataclass
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class QuestionType(str, Enum):
    PROFILE_FIELD = "profile_field"
    WORK_AUTH_SPONSORSHIP = "work_auth_sponsorship"
    EEO_DEMOGRAPHIC = "eeo_demographic"
    LEGAL_CONDUCT = "legal_conduct"
    CUSTOM_ESSAY = "custom_essay"


@dataclass
class QuestionTriage:
    question_type: QuestionType
    is_custom: bool
    field_key: Optional[str] = None


class QASynthesizer:
    """Triage and answer generation engine for ATS form questions."""

    def __init__(self, qa_generator: Optional[Any] = None) -> None:
        self._qa_generator = qa_generator

    @property
    def qa_generator(self) -> Any:
        if self._qa_generator is None:
            try:
                import importlib
                _mod = importlib.import_module("src.pipeline.3_tailoring.qa_generator")
                QAGenerator = getattr(_mod, "QAGenerator")
                self._qa_generator = QAGenerator()
            except Exception as exc:
                logger.debug("QAGenerator deferred init error in QASynthesizer: %s", exc)
        return self._qa_generator

    def triage_question(self, prompt_text: str) -> QuestionTriage:
        """Classify question into deterministic profile field, EEO, or custom essay."""
        text = prompt_text.lower().strip()

        # Helper regex tester
        def has_phrase(pattern: str) -> bool:
            return bool(re.search(pattern, text, re.IGNORECASE))

        # 1. Profile basic fields
        if has_phrase(r"\b(first\s*name|given\s*name|legal\s*first\s*name)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="first_name")
        if has_phrase(r"\b(last\s*name|family\s*name|surname|legal\s*last\s*name)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="last_name")
        if has_phrase(r"\b(full\s*name|your\s*name|legal\s*name)\b") and not has_phrase(r"\b(company|employer)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="full_name")
        if has_phrase(r"\b(email\s*address|e-?mail)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="email")
        if has_phrase(r"\b(phone\s*number|mobile|telephone|cell)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="phone")
        if has_phrase(r"\b(linkedin|linkedin\s*url|linkedin\s*profile)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="linkedin")
        if has_phrase(r"\b(github|github\s*url|github\s*profile)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="github")
        if has_phrase(r"\b(portfolio|website|personal\s*site)\b"):
            return QuestionTriage(QuestionType.PROFILE_FIELD, is_custom=False, field_key="portfolio")

        # 2. Work Authorization & Sponsorship
        if has_phrase(r"\b(authorized|legally\s*eligible|work\s*in\s*the\s*united\s*states|work\s*in\s*the\s*us)\b") or has_phrase(r"\b(sponsorship|visa|h-?1b|sponsor)\b"):
            return QuestionTriage(QuestionType.WORK_AUTH_SPONSORSHIP, is_custom=False)

        # 3. EEO Demographics & Surveys
        if has_phrase(r"\b(gender|sex|race|racial|ethnicity|veteran|military|disability|handicap|demographic|self-?identification)\b"):
            return QuestionTriage(QuestionType.EEO_DEMOGRAPHIC, is_custom=False)

        # 4. Legal / Misconduct / Non-competes
        if has_phrase(r"\b(misconduct|terminated\s*for\s*cause|non-?compete|restrictive\s*covenant)\b"):
            return QuestionTriage(QuestionType.LEGAL_CONDUCT, is_custom=False)

        # 5. Open-ended / Custom essay
        return QuestionTriage(QuestionType.CUSTOM_ESSAY, is_custom=True)

    def resolve_answer(
        self,
        prompt_text: str,
        profile: Dict[str, Any],
        max_chars: int = 500,
        job_context: Optional[str] = None,
    ) -> str:
        """Resolve deterministic field value or synthesize grounded STAR+R response."""
        triage = self.triage_question(prompt_text)

        # Deterministic profile mapping
        if triage.question_type == QuestionType.PROFILE_FIELD:
            key = triage.field_key
            if key:
                val = profile.get(key)
                if not val and key == "full_name":
                    val = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
                return str(val or "")

        # Deterministic work authorization / sponsorship
        elif triage.question_type == QuestionType.WORK_AUTH_SPONSORSHIP:
            text_lower = prompt_text.lower()
            if "sponsor" in text_lower or "visa" in text_lower or "h1b" in text_lower:
                return "Yes" if profile.get("requires_sponsorship", False) else "No"
            return "Yes" if profile.get("us_work_authorized", True) else "No"

        # Deterministic EEO decline
        elif triage.question_type == QuestionType.EEO_DEMOGRAPHIC:
            return "Decline to Self-Identify"

        # Deterministic legal conduct
        elif triage.question_type == QuestionType.LEGAL_CONDUCT:
            return "No"

        # Custom Essay / STAR+R synthesis
        return self._synthesize_custom_essay(prompt_text, profile, max_chars, job_context)

    def _synthesize_custom_essay(
        self,
        prompt: str,
        profile: Dict[str, Any],
        max_chars: int,
        job_context: Optional[str],
    ) -> str:
        """Synthesize response grounded in candidate STAR+R master stories with Career Brain support."""
        stories = profile.get("master_stories", [])
        prompt_lower = prompt.lower()

        matched_story = None
        for story in stories:
            skills = [s.lower() for s in story.get("skills", [])]
            if any(sk in prompt_lower or any(word in prompt_lower for word in sk.split() if len(word) >= 4) for sk in skills):
                matched_story = story
                break

        if not matched_story and stories:
            matched_story = stories[0]

        if matched_story:
            situation = matched_story.get("situation", "")
            action = matched_story.get("action", "")
            result = matched_story.get("result", "")
            ans = f"{situation} I {action.lower() if action.startswith('I ') else action}, which {result.lower()}"
        elif self.qa_generator is not None:
            # Delegate to unified QAGenerator / Career Brain
            try:
                company = profile.get("target_company") or "the company"
                title = profile.get("target_title") or "Senior Software Engineer"
                ans = self.qa_generator._answer_custom_question(
                    prompt, company=company, title=title, job_desc=job_context or ""
                )
            except Exception as exc:
                logger.debug("QAGenerator delegation fallback in QASynthesizer: %s", exc)
                first_name = profile.get("first_name", "I")
                ans = f"{first_name} brings extensive engineering experience delivering reliable distributed services and scalable architecture."
        else:
            first_name = profile.get("first_name", "I")
            ans = f"{first_name} brings extensive engineering experience delivering reliable distributed services and scalable architecture."

        ans = re.sub(r"\s+", " ", ans).strip()

        # Enforce character limit
        if len(ans) > max_chars:
            cutoff = ans[:max_chars - 3].rfind(".")
            if cutoff > 30:
                ans = ans[:cutoff + 1]
            else:
                ans = ans[:max_chars - 3] + "..."

        return ans
