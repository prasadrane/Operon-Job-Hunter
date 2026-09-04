"""Lever ATS submission adapter."""

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from .base_adapter import BaseATSAdapter

logger = logging.getLogger(__name__)


class LeverAdapter(BaseATSAdapter):
    """Specialized adapter for Lever job postings (jobs.lever.co)."""

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        url_lower = (url or "").lower()
        if "lever.co" in url_lower:
            return True
        if page:
            try:
                if hasattr(page, "locator") and page.locator("form#application-form, button.template-btn-submit, form[action*='lever.co']").count() > 0:
                    return True
            except Exception:
                pass
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

        full_name = profile.get("full_name") or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        email = profile.get("email", "")
        phone = profile.get("phone", "")
        linkedin = profile.get("linkedin", "")
        github = profile.get("github", "")
        portfolio = profile.get("portfolio") or profile.get("website", "")
        location = profile.get("location") or profile.get("city", "")

        fields_map = [
            ("full_name", ["input[name='name']", "input[id*='name' i]", "input[placeholder*='full name' i]"], full_name),
            ("email", ["input[name='email']", "input[type='email']", "input[id*='email' i]"], email),
            ("phone", ["input[name='phone']", "input[type='tel']", "input[id*='phone' i]"], phone),
            ("location", ["input[name='location']", "input[id*='location' i]"], location),
            ("linkedin", ["input[name*='urls[LinkedIn]' i]", "input[name*='linkedin' i]", "input[placeholder*='linkedin' i]"], linkedin),
            ("github", ["input[name*='urls[GitHub]' i]", "input[name*='github' i]", "input[placeholder*='github' i]"], github),
            ("portfolio", ["input[name*='urls[Portfolio]' i]", "input[name*='urls[Other]' i]", "input[name*='website' i]"], portfolio),
        ]

        filled_any = False
        for frame in frames:
            for field_name, selectors, value in fields_map:
                if not value:
                    continue
                for sel in selectors:
                    try:
                        if frame.is_visible(sel):
                            frame.fill(sel, str(value), timeout=2000)
                            filled_any = True
                            break
                    except Exception:
                        pass

            # Handle resume attachment
            if resume_path:
                file_selectors = [
                    "input[type='file']",
                    "input[name='resume']",
                    "input[id*='resume' i]",
                ]
                for sel in file_selectors:
                    try:
                        file_input = frame.locator(sel)
                        if file_input.count() > 0:
                            file_input.first.set_input_files(resume_path)
                            filled_any = True
                            logger.info("Attached resume via Lever selector: %s", sel)
                            break
                    except Exception:
                        pass

        return filled_any

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Click Lever submit button and verify submission confirmation."""
        submit_selectors = [
            "button.template-btn-submit",
            "button:has-text('Submit application')",
            "button:has-text('Submit Application')",
            "button[type='submit']",
            "input[type='submit']",
        ]
        clicked = False
        for sel in submit_selectors:
            try:
                if page.is_visible(sel):
                    page.click(sel, force=True, timeout=5000)
                    clicked = True
                    logger.info("Clicked Lever submit button: %s", sel)
                    time.sleep(2.5)
                    break
            except Exception:
                pass

        if not clicked:
            clicked = self.safe_click(page, "Submit application") or self.safe_click(page, "Submit")

        time.sleep(1.0)
        confirmed = self.verify_submission(page)

        confirmation_id = ""
        try:
            content = str(page.content())
            match = re.search(r"(?:confirmation|application|reference)\s*(?:#|id|code)?[:\s]*([a-z0-9\-_]{4,20})", content, re.IGNORECASE)
            if match:
                confirmation_id = match.group(0).strip()
        except Exception:
            pass

        if confirmed:
            return True, confirmation_id or "LEVER-SUBMISSION-CONFIRMED"
        if clicked:
            return True, confirmation_id or "LEVER-SUBMIT-CLICKED"
        return False, "Failed to submit Lever application"
