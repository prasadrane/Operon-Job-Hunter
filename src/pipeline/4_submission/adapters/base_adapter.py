"""Base class and common utilities for ATS submission adapters."""

from abc import ABC, abstractmethod
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.models import CandidateProfile, JobPosting, TailoredArtifacts

logger = logging.getLogger(__name__)

CONFIRMATION_INDICATORS: List[str] = [
    "thank you for applying",
    "thanks for applying",
    "application submitted",
    "application received",
    "thank you for your application",
    "your application has been submitted",
    "application complete",
    "application accepted",
    "we have received your application",
    "we received your application",
    "application successfully submitted",
    "submission successful",
]

CONFIRMATION_URL_KEYWORDS: List[str] = [
    "/submitted",
    "/confirmation",
    "/success",
    "/thank-you",
    "/thanks",
    "/applied",
    "/done",
]


class BaseATSAdapter(ABC):
    """Abstract base class for all ATS portal submission adapters."""

    @abstractmethod
    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        """Return True if this adapter can handle the given URL or page DOM."""
        pass

    def _normalize_profile(self, profile: Optional[Union[dict, CandidateProfile, Any]]) -> Dict[str, Any]:
        """Convert CandidateProfile or dict into standard dictionary."""
        if profile is None:
            return CandidateProfile().model_dump()
        if isinstance(profile, CandidateProfile):
            return profile.model_dump()
        if isinstance(profile, dict):
            # Ensure defaults
            defaults = CandidateProfile().model_dump()
            defaults.update(profile)
            if not defaults.get("full_name"):
                defaults["full_name"] = f"{defaults.get('first_name', '')} {defaults.get('last_name', '')}".strip()
            return defaults
        if hasattr(profile, "__dict__"):
            return dict(profile.__dict__)
        return {}

    def safe_click(self, page_or_frame: Any, action_label: str) -> bool:
        """Robust click action targeting buttons and submit inputs with fallbacks."""
        if not page_or_frame:
            return False

        clean_label = action_label.replace('"', '\\"')
        selectors = [
            f'button:has-text("{clean_label}")',
            f'input[type="submit"][value*="{clean_label}" i]',
            f'button[id*="{clean_label}" i]',
            f'button[name*="{clean_label}" i]',
            f'a:has-text("{clean_label}")',
            f'[role="button"]:has-text("{clean_label}")',
        ]
        for sel in selectors:
            try:
                if page_or_frame.is_visible(sel):
                    page_or_frame.click(sel, force=True, timeout=3000)
                    time.sleep(0.5)
                    return True
            except Exception:
                pass
        return False

    def verify_submission(self, page_or_frame: Any) -> bool:
        """Check whether application confirmation indicator or URL is present."""
        if not page_or_frame:
            return False
        try:
            url = str(getattr(page_or_frame, "url", "")).lower()
            if any(term in url for term in CONFIRMATION_URL_KEYWORDS):
                logger.info("Submission confirmed via URL redirect: %s", url)
                return True

            if hasattr(page_or_frame, "content"):
                content = str(page_or_frame.content()).lower()
                for indicator in CONFIRMATION_INDICATORS:
                    if indicator in content:
                        logger.info("Submission confirmed via DOM content: '%s'", indicator)
                        return True
        except Exception as e:
            logger.warning("Error verifying submission: %s", e)
        return False

    def fill_custom_questions(self, page_or_frame: Any, qa_answers: Dict[str, Any]) -> bool:
        """Attempt to fill open-ended or custom questions based on QA answers dictionary."""
        if not qa_answers or not page_or_frame:
            return False

        filled_count = 0
        frames = [page_or_frame]
        if hasattr(page_or_frame, "frames"):
            frames.extend(page_or_frame.frames)

        for frame in frames:
            for question_key, answer_val in qa_answers.items():
                if not answer_val:
                    continue
                str_val = str(answer_val)
                key_clean = re.sub(r"[_\W]+", " ", question_key).strip()

                selectors = [
                    f'textarea[name*="{question_key}" i]',
                    f'textarea[id*="{question_key}" i]',
                    f'input[type="text"][name*="{question_key}" i]',
                    f'input[type="text"][id*="{question_key}" i]',
                    f'input[placeholder*="{key_clean}" i]',
                    f'textarea[placeholder*="{key_clean}" i]',
                ]
                for sel in selectors:
                    try:
                        if frame.is_visible(sel):
                            frame.fill(sel, str_val, timeout=2000)
                            filled_count += 1
                            break
                    except Exception:
                        pass
        return filled_count > 0

    def fill_form(
        self,
        page: Any,
        job: JobPosting,
        artifacts: Optional[TailoredArtifacts] = None,
        profile: Optional[Union[dict, CandidateProfile, Any]] = None,
    ) -> bool:
        """High-level form filling combining candidate profile, custom questions, and resume."""
        profile_data = self._normalize_profile(profile)
        resume_path = artifacts.resume_pdf_path if artifacts else None
        qa_answers = artifacts.qa_answers if artifacts else {}

        profile_filled = self.fill_profile(page, profile_data, resume_path=resume_path)
        if qa_answers:
            self.fill_custom_questions(page, qa_answers)
        return profile_filled

    def fill_profile(
        self,
        page_or_frame: Any,
        profile: Dict[str, Any],
        resume_path: Optional[str] = None,
    ) -> bool:
        """Pre-fill candidate demographic and contact fields. Override in subclasses."""
        return False

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Trigger final application submission and verify result."""
        clicked = self.safe_click(page, "Submit Application") or self.safe_click(page, "Submit")
        time.sleep(2.0)
        confirmed = self.verify_submission(page)
        if confirmed:
            return True, "Application successfully submitted"
        if clicked:
            return True, "Submit clicked (verification pending)"
        return False, "Submit action failed or button not found"
