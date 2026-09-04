"""Workday Agentic Multi-Step Wizard Submitter Strategy."""

import hashlib
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.models import CandidateProfile, JobPosting, TailoredArtifacts
from .base_adapter import BaseATSAdapter
from ..captcha_handler import CaptchaHandler
from ..websurfer_agent import WebSurferAgent

logger = logging.getLogger(__name__)


class WorkdayAgenticSubmitter(BaseATSAdapter):
    """Agentic submitter supporting Workday multi-step application wizards (*.myworkdayjobs.com).
    
    Features:
    - Multi-step wizard navigation up to max_steps.
    - Step transition verification via DOM hashing and change detection.
    - Error element scanning ([aria-invalid='true'], .css-error, [role="alert"], error-banners).
    - Candidate account authentication handling (email/password).
    - CAPTCHA detection and graceful HITL escalation.
    - Structured status reporting (READY_FOR_HITL, SUBMITTED, MAX_STEPS_REACHED, CAPTCHA_DETECTED, VALIDATION_ERROR).
    """

    ERROR_SELECTORS: List[str] = [
        '[aria-invalid="true"]',
        '.css-error',
        '[data-automation-id="error-banner"]',
        '[data-automation-id*="error" i]',
        '[data-automation-id*="errorMessage" i]',
        '[role="alert"]',
        '.alert-danger',
        'div[id*="error" i]',
    ]

    NEXT_BUTTON_SELECTORS: List[str] = [
        '[data-automation-id="bottom-navigation-next-button"]',
        '[data-automation-id="bottom-navigation-save-button"]',
        'button:has-text("Save and Continue")',
        'button:has-text("Next")',
        'button:has-text("Continue")',
    ]

    SUBMIT_BUTTON_SELECTORS: List[str] = [
        '[data-automation-id="bottom-navigation-submit-button"]',
        '[data-automation-id="submitButton"]',
        'button:has-text("Submit Application")',
        'button:has-text("Submit")',
    ]

    def __init__(
        self,
        max_steps: int = 6,
        agent: Optional[WebSurferAgent] = None,
        captcha_handler: Optional[CaptchaHandler] = None,
    ) -> None:
        """Initialize WorkdayAgenticSubmitter.

        Args:
            max_steps: Maximum wizard steps to iterate before capping.
            agent: Optional WebSurferAgent instance for perception/action decisions.
            captcha_handler: Optional CaptchaHandler instance for bot-challenge detection.
        """
        self.max_steps = max_steps
        self.agent = agent or WebSurferAgent()
        self.captcha_handler = captcha_handler or CaptchaHandler()

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        """Check if URL or DOM matches Workday portal patterns."""
        url_lower = (url or "").lower()
        if "myworkdayjobs.com" in url_lower or "workday" in url_lower:
            return True
        if page:
            try:
                if hasattr(page, "locator") and page.locator(
                    '[data-automation-id="click_filter"], [data-automation-id*="workday" i], [data-automation-id="signInSubmitButton"], [data-automation-id="bottom-navigation-submit-button"]'
                ).count() > 0:
                    return True
            except Exception:
                pass
        return False

    def compute_page_hash(self, page: Any) -> str:
        """Compute MD5 hash of visible DOM content to detect page transitions."""
        if not page:
            return ""
        try:
            if hasattr(page, "content"):
                content = str(page.content())
                return hashlib.md5(content.encode("utf-8", errors="ignore")).hexdigest()
        except Exception:
            pass
        return ""

    def scan_errors(self, page: Any) -> List[str]:
        """Scan page for active error banners, alerts, or fields with aria-invalid='true'."""
        if not page:
            return []

        errors: List[str] = []
        frames = [page]
        if hasattr(page, "frames"):
            frames.extend(page.frames)

        for frame in frames:
            for selector in self.ERROR_SELECTORS:
                try:
                    loc = frame.locator(selector)
                    count = loc.count() if hasattr(loc, "count") else 0
                    if count > 0:
                        elements = loc.all() if hasattr(loc, "all") else [loc.first]
                        for elem in elements:
                            try:
                                is_vis = elem.is_visible() if hasattr(elem, "is_visible") else True
                                if not is_vis:
                                    continue

                                text = (elem.inner_text() if hasattr(elem, "inner_text") else "").strip()
                                if text:
                                    if text not in errors:
                                        errors.append(text)
                                else:
                                    # Inspect attributes to identify invalid field
                                    label = (
                                        (elem.get_attribute("aria-label") if hasattr(elem, "get_attribute") else "")
                                        or (elem.get_attribute("name") if hasattr(elem, "get_attribute") else "")
                                        or (elem.get_attribute("id") if hasattr(elem, "get_attribute") else "")
                                    )
                                    msg = f"Invalid or missing value for field: {label}" if label else f"Validation error detected on selector: {selector}"
                                    if msg not in errors:
                                        errors.append(msg)
                            except Exception:
                                pass
                except Exception:
                    pass

        return errors

    def handle_account(self, page: Any, profile: Dict[str, Any]) -> bool:
        """Handle candidate account authentication or creation modal if active."""
        if not page:
            return False

        email = profile.get("email", "")
        password = profile.get("password", "")
        if not email or not password:
            return False

        try:
            email_field = page.locator('input[data-automation-id="email"], input[type="email"], input[id*="email" i]')
            pwd_field = page.locator('input[data-automation-id="password"], input[type="password"]')

            if email_field.count() > 0 and email_field.first.is_visible():
                email_field.first.fill(email)
                if pwd_field.count() > 0 and pwd_field.first.is_visible():
                    pwd_field.first.fill(password)
                
                # Attempt to click Sign In or Submit
                for signin_btn in ['button:has-text("Sign In")', '[data-automation-id="signInSubmitButton"]', 'button:has-text("Log In")']:
                    try:
                        if page.is_visible(signin_btn):
                            page.click(signin_btn)
                            time.sleep(1.0)
                            return True
                    except Exception:
                        pass
                return True
        except Exception as e:
            logger.debug("Workday account handling exception: %s", e)
        return False

    def fill_step(
        self,
        page: Any,
        profile: Dict[str, Any],
        resume_path: Optional[str] = None,
        qa_answers: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Fill profile fields, resume upload, and QA answers for current wizard step."""
        if not page:
            return False

        first_name = profile.get("first_name", "")
        last_name = profile.get("last_name", "")
        email = profile.get("email", "")
        phone = profile.get("phone", "")
        address = profile.get("address", "")
        city = profile.get("city", "")
        state = profile.get("state", "")
        zip_code = profile.get("zip_code", "")

        fields_map = [
            ("first_name", ['[data-automation-id="legalNameSection_firstName"]', 'input[id*="firstName" i]'], first_name),
            ("last_name", ['[data-automation-id="legalNameSection_lastName"]', 'input[id*="lastName" i]'], last_name),
            ("email", ['[data-automation-id="email"]', 'input[type="email"]'], email),
            ("phone", ['[data-automation-id="phone-number"]', 'input[type="tel"]'], phone),
            ("address", ['[data-automation-id="addressSection_addressLine1"]', 'input[id*="addressLine1" i]'], address),
            ("city", ['[data-automation-id="addressSection_city"]', 'input[id*="city" i]'], city),
            ("state", ['[data-automation-id="addressSection_countryRegion"]', 'input[id*="state" i]'], state),
            ("zip_code", ['[data-automation-id="addressSection_postalCode"]', 'input[id*="postal" i]'], zip_code),
        ]

        filled_any = False
        for field_name, selectors, value in fields_map:
            if not value:
                continue
            for sel in selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.fill(str(value))
                        filled_any = True
                        break
                except Exception:
                    pass

        # Handle resume attachment
        actual_resume = resume_path or profile.get("resume_path") or profile.get("resume_pdf_path")
        if actual_resume:
            file_selectors = [
                'input[data-automation-id="file-upload-drop-zone"]',
                'input[type="file"]',
                'input[data-automation-id*="file" i]',
            ]
            for sel in file_selectors:
                try:
                    file_input = page.locator(sel)
                    if file_input.count() > 0:
                        file_input.first.set_input_files(actual_resume)
                        filled_any = True
                        break
                except Exception:
                    pass

        # Handle QA answers
        answers = qa_answers or profile.get("qa_answers", {})
        if answers and isinstance(answers, dict):
            for q_key, q_ans in answers.items():
                try:
                    q_loc = page.locator(f'textarea[aria-label*="{q_key}" i], input[aria-label*="{q_key}" i]')
                    if q_loc.count() > 0 and q_loc.first.is_visible():
                        q_loc.first.fill(str(q_ans))
                        filled_any = True
                except Exception:
                    pass

        return filled_any

    def fill_and_navigate(
        self,
        page: Any,
        profile: Dict[str, Any],
        resume_path: Optional[str] = None,
        qa_answers: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Step through Workday multi-page wizard with error scanning and transition verification.

        Returns:
            Dictionary containing status, steps_completed, errors, and details.
        """
        # 1. Inspect CAPTCHA challenge before starting
        if self.captcha_handler.detect_captcha(page):
            logger.warning("CAPTCHA challenge detected on Workday portal.")
            return {
                "status": "CAPTCHA_DETECTED",
                "steps_completed": 0,
                "errors": ["CAPTCHA challenge detected on page"],
            }

        # 2. Candidate login modal handling
        self.handle_account(page, profile)

        step = 0
        while step < self.max_steps:
            # Check for CAPTCHA during stepping
            if self.captcha_handler.detect_captcha(page):
                return {
                    "status": "CAPTCHA_DETECTED",
                    "steps_completed": step,
                    "errors": ["CAPTCHA challenge detected on page"],
                }

            # Check if review/submit page is reached
            is_submit_ready = False
            for sel in self.SUBMIT_BUTTON_SELECTORS:
                try:
                    if page.is_visible(sel):
                        is_submit_ready = True
                        break
                except Exception:
                    pass

            if is_submit_ready:
                return {
                    "status": "READY_FOR_HITL",
                    "steps_completed": max(1, step),
                    "errors": [],
                }

            # Fill form fields for current step
            self.fill_step(page, profile, resume_path=resume_path, qa_answers=qa_answers)

            # Check for Next / Save and Continue button
            next_selector: Optional[str] = None
            for sel in self.NEXT_BUTTON_SELECTORS:
                try:
                    if page.is_visible(sel):
                        next_selector = sel
                        break
                except Exception:
                    pass

            if not next_selector:
                # No next button found; check again if submit button is visible
                if is_submit_ready:
                    return {
                        "status": "READY_FOR_HITL",
                        "steps_completed": max(1, step),
                        "errors": [],
                    }
                break

            # Capture pre-transition hash and DOM state
            pre_hash = self.compute_page_hash(page)

            # Click Save and Continue / Next
            try:
                page.click(next_selector)
            except Exception as e:
                logger.warning("Error clicking next button (%s): %s", next_selector, e)

            step += 1

            # Check for validation errors triggered by click
            errors = self.scan_errors(page)
            if errors:
                return {
                    "status": "VALIDATION_ERROR",
                    "steps_completed": step,
                    "errors": errors,
                }

            # Capture post-transition hash
            post_hash = self.compute_page_hash(page)

            # If DOM did not change and no review button appeared, check if stuck
            if pre_hash and post_hash and pre_hash == post_hash:
                # Page did not change
                # Verify if next button is still the only action
                return {
                    "status": "VALIDATION_ERROR",
                    "steps_completed": step,
                    "errors": ["Page failed to advance to next step after clicking continue."],
                }

        return {
            "status": "MAX_STEPS_REACHED",
            "steps_completed": step,
            "errors": [],
        }

    def fill_form(
        self,
        page: Any,
        job: JobPosting,
        artifacts: Optional[TailoredArtifacts] = None,
        profile: Optional[Union[dict, CandidateProfile, Any]] = None,
    ) -> bool:
        """BaseATSAdapter compatibility method for filling the form."""
        profile_data = self._normalize_profile(profile)
        resume_path = artifacts.resume_pdf_path if artifacts else None
        qa_answers = artifacts.qa_answers if artifacts else {}

        res = self.fill_and_navigate(
            page=page,
            profile=profile_data,
            resume_path=resume_path,
            qa_answers=qa_answers,
        )
        return res.get("status") in ["READY_FOR_HITL", "SUBMITTED"] or res.get("steps_completed", 0) > 0

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Click Workday final review & submit button and verify confirmation."""
        if not page:
            return False, "Invalid page reference"

        clicked = False
        for sel in self.SUBMIT_BUTTON_SELECTORS:
            try:
                if page.is_visible(sel):
                    page.click(sel)
                    clicked = True
                    break
            except Exception:
                pass

        if not clicked:
            # Fallback direct locator click
            try:
                btn = page.locator('[data-automation-id="bottom-navigation-submit-button"], [data-automation-id="submitButton"]')
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click()
                    clicked = True
            except Exception:
                pass

        confirmed = self.verify_submission(page)
        confirmation_id = ""
        try:
            content = str(page.content())
            match = re.search(r"(?:application|reference|confirmation)\s*(?:#|id|number)?[:\s]*([a-z0-9\-_]{4,20})", content, re.IGNORECASE)
            if match:
                confirmation_id = match.group(0).strip()
        except Exception:
            pass

        if confirmed:
            return True, confirmation_id or "WD-SUBMISSION-CONFIRMED"
        if clicked:
            return True, confirmation_id or "WD-SUBMIT-CLICKED"
        return False, "Failed to submit Workday application"
