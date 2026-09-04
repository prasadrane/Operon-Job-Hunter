"""Generic heuristic fallback ATS submission adapter."""

import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from .base_adapter import BaseATSAdapter

logger = logging.getLogger(__name__)


class GenericAdapter(BaseATSAdapter):
    """Fallback heuristic adapter for arbitrary or custom careers portals."""

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        # Generic adapter handles any URL as the terminal fallback
        return True

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
        full_name = profile.get("full_name") or f"{first_name} {last_name}".strip()
        email = profile.get("email", "")
        phone = profile.get("phone", "")
        location = profile.get("location") or profile.get("city", "")
        address = profile.get("address", "")
        city = profile.get("city", "")
        state = profile.get("state", "")
        zip_code = profile.get("zip_code", "")
        linkedin = profile.get("linkedin", "")
        github = profile.get("github", "")
        portfolio = profile.get("portfolio") or profile.get("website", "")

        fields_map = [
            ("first_name", ["input[id*='first_name' i]", "input[name*='first_name' i]", "input[placeholder*='first name' i]"], first_name),
            ("last_name", ["input[id*='last_name' i]", "input[name*='last_name' i]", "input[placeholder*='last name' i]"], last_name),
            ("full_name", ["input[id*='full_name' i]", "input[name*='full_name' i]", "input[id='name' i]", "input[name='name' i]", "input[placeholder*='full name' i]"], full_name),
            ("email", ["input[id*='email' i]", "input[name*='email' i]", "input[type='email']", "input[placeholder*='email' i]"], email),
            ("phone", ["input[id*='phone' i]", "input[name*='phone' i]", "input[type='tel']", "input[placeholder*='phone' i]"], phone),
            ("location", ["input[id*='location' i]", "input[name*='location' i]", "input[placeholder*='location' i]"], location),
            ("address", ["input[id*='address' i]", "input[name*='address' i]", "input[placeholder*='address' i]"], address),
            ("city", ["input[id*='city' i]", "input[name*='city' i]", "input[placeholder*='city' i]"], city),
            ("state", ["input[id*='state' i]", "input[name*='state' i]", "input[placeholder*='state' i]"], state),
            ("zip_code", ["input[id*='zip' i]", "input[name*='zip' i]", "input[placeholder*='zip' i]"], zip_code),
            ("linkedin", ["input[id*='linkedin' i]", "input[name*='linkedin' i]", "input[placeholder*='linkedin' i]"], linkedin),
            ("github", ["input[id*='github' i]", "input[name*='github' i]", "input[placeholder*='github' i]"], github),
            ("portfolio", ["input[id*='website' i]", "input[name*='portfolio' i]", "input[id*='portfolio' i]", "input[placeholder*='portfolio' i]"], portfolio),
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
                    "input[id*='resume' i]",
                    "input[name*='resume' i]",
                    "input[data-qa*='resume' i]",
                ]
                for sel in file_selectors:
                    try:
                        file_input = frame.locator(sel)
                        if file_input.count() > 0:
                            file_input.first.set_input_files(resume_path)
                            filled_any = True
                            logger.info("Attached resume via Generic selector: %s", sel)
                            break
                    except Exception:
                        pass

        return filled_any

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Trigger generic submission by locating submit buttons."""
        submit_selectors = [
            "button[type='submit']",
            "input[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
        ]
        clicked = False
        for sel in submit_selectors:
            try:
                if page.is_visible(sel):
                    page.click(sel, force=True, timeout=4000)
                    clicked = True
                    logger.info("Clicked generic submit selector: %s", sel)
                    time.sleep(2.5)
                    break
            except Exception:
                pass

        if not clicked:
            clicked = self.safe_click(page, "Submit Application") or self.safe_click(page, "Submit")

        time.sleep(1.0)
        confirmed = self.verify_submission(page)

        confirmation_id = ""
        try:
            content = str(page.content())
            match = re.search(r"(?:application|reference|confirmation)\s*(?:#|id|code)?[:\s]*([a-z0-9\-_]{4,20})", content, re.IGNORECASE)
            if match:
                confirmation_id = match.group(0).strip()
        except Exception:
            pass

        if confirmed:
            return True, confirmation_id or "GENERIC-SUBMISSION-CONFIRMED"
        if clicked:
            return True, confirmation_id or "GENERIC-SUBMIT-CLICKED"
        return False, "Failed to submit application via Generic adapter"
