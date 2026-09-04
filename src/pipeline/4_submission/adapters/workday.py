"""Workday ATS multi-step wizard and submission adapter."""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.models import CandidateProfile, JobPosting, TailoredArtifacts
from .base_adapter import BaseATSAdapter

logger = logging.getLogger(__name__)


class WorkdayAdapter(BaseATSAdapter):
    """Specialized adapter for Workday multi-step candidate portals (*.myworkdayjobs.com)."""

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
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

    def safe_click(self, page_or_frame: Any, action_label: str) -> bool:
        """
        Multi-tier click handler targeting Workday pointer interception overlays
        (div[data-automation-id="click_filter"]) directly before button fallbacks.
        """
        if not page_or_frame:
            return False

        clean_label = action_label.replace('"', '\\"')

        # Tier 1: Target overlay div directly by aria-label or data-automation-id
        overlay_selectors = [
            f'[data-automation-id="click_filter"][aria-label*="{clean_label}" i]',
            f'div[role="button"][aria-label*="{clean_label}" i]',
            f'button:has-text("{clean_label}")',
            f'div[data-automation-id*="{clean_label}" i]',
        ]
        for sel in overlay_selectors:
            try:
                if page_or_frame.is_visible(sel):
                    page_or_frame.click(sel, force=True, timeout=3000)
                    time.sleep(0.5)
                    return True
            except Exception:
                pass

        # Tier 2: Native JS mouse & pointer event dispatch on click_filter overlay
        try:
            executed = page_or_frame.evaluate(
                """
                (label) => {
                    const overlays = Array.from(document.querySelectorAll('[data-automation-id="click_filter"], button, div[role="button"]'));
                    const target = overlays.find(el => 
                        el.getAttribute('aria-label')?.toLowerCase().includes(label.toLowerCase()) ||
                        el.textContent?.toLowerCase().includes(label.toLowerCase()) ||
                        el.getAttribute('data-automation-id')?.toLowerCase().includes(label.toLowerCase())
                    );
                    if (target) {
                        target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
                        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                        target.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true }));
                        target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                        target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                        if (typeof target.click === 'function') target.click();
                        return true;
                    }
                    return false;
                }
                """,
                action_label,
            )
            if executed:
                time.sleep(0.5)
                return True
        except Exception:
            pass

        # Tier 3: Workday specific button ID fallbacks
        fallback_button_ids = [
            "bottom-navigation-submit-button",
            "submitButton",
            "signInSubmitButton",
            "bottom-navigation-next-button",
            "bottom-navigation-save-button",
            "previous-button",
        ]
        action_lower = action_label.lower()
        if "submit" in action_lower:
            target_ids = [b for b in fallback_button_ids if "submit" in b.lower()] + [b for b in fallback_button_ids if "submit" not in b.lower()]
        elif "next" in action_lower or "continue" in action_lower:
            target_ids = [b for b in fallback_button_ids if "next" in b.lower()] + [b for b in fallback_button_ids if "next" not in b.lower()]
        else:
            target_ids = fallback_button_ids

        for btn_id in target_ids:
            try:
                btn = page_or_frame.locator(f'[data-automation-id="{btn_id}"]')
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(force=True, timeout=3000)
                    time.sleep(0.5)
                    return True
            except Exception:
                pass

        return False

    def handle_login_if_present(self, page: Any, profile: Dict[str, Any]) -> bool:
        """Handle Workday account login or guest creation if required."""
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
                self.safe_click(page, "Sign In") or self.safe_click(page, "signInSubmitButton")
                time.sleep(2.0)
                return True
        except Exception as e:
            logger.debug("Workday login bypass/exception: %s", e)
        return False

    def fill_profile(
        self,
        page_or_frame: Any,
        profile: Dict[str, Any],
        resume_path: Optional[str] = None,
    ) -> bool:
        if not page_or_frame:
            return False

        frames = [page_or_frame]
        if hasattr(page_or_frame, "frames"):
            frames.extend(page_or_frame.frames)

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
        for frame in frames:
            for field_name, selectors, value in fields_map:
                if not value:
                    continue
                for sel in selectors:
                    try:
                        loc = frame.locator(sel)
                        if loc.count() > 0 and loc.first.is_visible():
                            loc.first.fill(str(value))
                            filled_any = True
                            break
                    except Exception:
                        pass

            # Handle resume attachment
            if resume_path:
                file_selectors = [
                    'input[data-automation-id="file-upload-drop-zone"]',
                    'input[type="file"]',
                    'input[data-automation-id*="file" i]',
                ]
                for sel in file_selectors:
                    try:
                        file_input = frame.locator(sel)
                        if file_input.count() > 0:
                            file_input.first.set_input_files(resume_path)
                            filled_any = True
                            logger.info("Attached resume via Workday selector: %s", sel)
                            break
                    except Exception:
                        pass

        return filled_any

    def fill_form(
        self,
        page: Any,
        job: JobPosting,
        artifacts: Optional[TailoredArtifacts] = None,
        profile: Optional[Union[dict, CandidateProfile, Any]] = None,
    ) -> bool:
        """Handle Workday multi-step wizard navigation and step form filling."""
        profile_data = self._normalize_profile(profile)
        resume_path = artifacts.resume_pdf_path if artifacts else None
        qa_answers = artifacts.qa_answers if artifacts else {}

        # 1. Attempt login if prompt is active
        self.handle_login_if_present(page, profile_data)

        # 2. Iterate through multi-page wizard steps (max 6 steps)
        max_steps = 6
        step_count = 0
        filled_overall = False

        while step_count < max_steps:
            step_count += 1
            filled_this_step = self.fill_profile(page, profile_data, resume_path=resume_path)
            if qa_answers:
                self.fill_custom_questions(page, qa_answers)

            if filled_this_step:
                filled_overall = True

            # If review or final submit button is visible, stop stepping
            submit_btn = page.locator('[data-automation-id="bottom-navigation-submit-button"], button:has-text("Submit Application")')
            try:
                if submit_btn.count() > 0 and submit_btn.first.is_visible():
                    logger.info("Workday final submit step reached at step %s", step_count)
                    break
            except Exception:
                pass

            # Click Next / Save and Continue to proceed to next wizard page
            next_clicked = self.safe_click(page, "bottom-navigation-next-button") or self.safe_click(page, "Save and Continue") or self.safe_click(page, "Next")
            if not next_clicked:
                break
            time.sleep(2.0)

        return filled_overall or (step_count > 1)

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Click Workday final review & submit button."""
        clicked = self.safe_click(page, "bottom-navigation-submit-button") or self.safe_click(page, "submitButton") or self.safe_click(page, "Submit Application") or self.safe_click(page, "Submit")

        time.sleep(2.5)
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
