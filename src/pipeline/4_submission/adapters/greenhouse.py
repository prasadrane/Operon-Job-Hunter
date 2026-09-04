"""Greenhouse ATS submission adapter."""

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from .base_adapter import BaseATSAdapter

logger = logging.getLogger(__name__)


class GreenhouseAdapter(BaseATSAdapter):
    """Specialized adapter for Greenhouse job boards (boards.greenhouse.io / job-boards.greenhouse.io)."""

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        url_lower = (url or "").lower()
        if "greenhouse.io" in url_lower or "greenhouse" in url_lower:
            return True
        if page:
            try:
                if hasattr(page, "locator") and page.locator("#application_form, #submit_app, form[action*='greenhouse']").count() > 0:
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

        first_name = profile.get("first_name", "")
        last_name = profile.get("last_name", "")
        email = profile.get("email", "")
        phone = profile.get("phone", "")
        location = profile.get("location") or profile.get("city") or profile.get("address", "")
        linkedin = profile.get("linkedin", "")
        github = profile.get("github", "")
        portfolio = profile.get("portfolio") or profile.get("website", "")

        fields_map = [
            ("first_name", ["input[id*='first_name' i]", "input[name*='first_name' i]", "input[autocomplete*='given-name']", "#first_name"], first_name),
            ("last_name", ["input[id*='last_name' i]", "input[name*='last_name' i]", "input[autocomplete*='family-name']", "#last_name"], last_name),
            ("email", ["input[id*='email' i]", "input[name*='email' i]", "input[type='email']", "#email"], email),
            ("phone", ["input[id*='phone' i]", "input[name*='phone' i]", "input[type='tel']", "#phone"], phone),
            ("location", ["input[id*='location' i]", "input[name*='location' i]", "#location", "input[placeholder*='location' i]"], location),
            ("linkedin", ["input[id*='linkedin' i]", "input[name*='linkedin' i]", "input[placeholder*='linkedin' i]"], linkedin),
            ("github", ["input[id*='github' i]", "input[name*='github' i]", "input[placeholder*='github' i]"], github),
            ("portfolio", ["input[id*='website' i]", "input[name*='portfolio' i]", "input[id*='portfolio' i]", "#website"], portfolio),
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
                    "#resume_upload",
                    "input[id*='resume' i]",
                    "input[name*='resume' i]",
                    "input[type='file']",
                ]
                for sel in file_selectors:
                    try:
                        file_input = frame.locator(sel)
                        if file_input.count() > 0:
                            file_input.first.set_input_files(resume_path)
                            filled_any = True
                            logger.info("Attached resume via Greenhouse selector: %s", sel)
                            break
                    except Exception:
                        pass

        return filled_any

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Click Greenhouse submit button and confirm receipt."""
        submit_selectors = [
            "#submit_app",
            "input#submit_app",
            "input[type='submit'][value*='Submit Application' i]",
            "button:has-text('Submit Application')",
            "input[type='submit']",
            "button[type='submit']",
        ]
        clicked = False
        for sel in submit_selectors:
            try:
                if page.is_visible(sel):
                    page.click(sel, force=True, timeout=5000)
                    clicked = True
                    logger.info("Clicked Greenhouse submit selector: %s", sel)
                    time.sleep(2.5)
                    break
            except Exception:
                pass

        if not clicked:
            clicked = self.safe_click(page, "Submit Application") or self.safe_click(page, "Submit")

        # Check confirmation
        time.sleep(1.0)
        confirmed = self.verify_submission(page)

        # Extract confirmation id / reference if available
        confirmation_id = ""
        try:
            content = str(page.content())
            match = re.search(r"(?:confirmation|application|reference)\s*(?:#|id|code)?[:\s]*([a-z0-9\-_]{4,20})", content, re.IGNORECASE)
            if match:
                confirmation_id = match.group(0).strip()
        except Exception:
            pass

        if confirmed:
            return True, confirmation_id or "GH-SUBMISSION-CONFIRMED"
        if clicked:
            return True, confirmation_id or "GH-SUBMIT-CLICKED"
        return False, "Failed to submit Greenhouse application"
