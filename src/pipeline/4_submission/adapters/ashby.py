"""Ashby ATS submission adapter."""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from .base_adapter import BaseATSAdapter

logger = logging.getLogger(__name__)


class AshbyAdapter(BaseATSAdapter):
    """Specialized adapter for Ashby job boards (jobs.ashbyhq.com / ashbyhq.com)."""

    def can_handle(self, url: str, page: Optional[Any] = None) -> bool:
        url_lower = (url or "").lower()
        if "ashbyhq.com" in url_lower or "ashby" in url_lower:
            return True
        if page:
            try:
                if hasattr(page, "locator") and page.locator("[data-qa*='ashby' i], [class*='ashby' i], form[action*='ashby']").count() > 0:
                    return True
            except Exception:
                pass
        return False

    def get_effective_email(
        self,
        email: str,
        company: str,
        prior_applications: Optional[List[str]] = None,
    ) -> str:
        """Derive alias email (e.g. user+company@domain.com) if prior application exists for company."""
        if not prior_applications or not email or "@" not in email:
            return email

        clean_company = re.sub(r"[^\w]", "", (company or "").lower())
        if not clean_company:
            return email

        prior_clean = [re.sub(r"[^\w]", "", c.lower()) for c in prior_applications]
        if clean_company in prior_clean:
            user, domain = email.split("@", 1)
            base_user = user.split("+", 1)[0]
            return f"{base_user}+{clean_company}@{domain}"

        return email

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
        linkedin = profile.get("linkedin", "")
        github = profile.get("github", "")
        portfolio = profile.get("portfolio") or profile.get("website", "")

        fields_map = [
            ("name", ["input[name='name']", "input[id*='name' i]", "input[placeholder*='name' i]"], full_name),
            ("first_name", ["input[name='firstName']", "input[id*='first_name' i]"], first_name),
            ("last_name", ["input[name='lastName']", "input[id*='last_name' i]"], last_name),
            ("email", ["input[name='email']", "input[type='email']", "input[id*='email' i]"], email),
            ("phone", ["input[name='phone']", "input[type='tel']", "input[id*='phone' i]"], phone),
            ("location", ["input[name='location']", "input[id*='location' i]"], location),
            ("linkedin", ["input[name*='linkedin' i]", "input[id*='linkedin' i]", "input[placeholder*='linkedin' i]"], linkedin),
            ("github", ["input[name*='github' i]", "input[id*='github' i]", "input[placeholder*='github' i]"], github),
            ("portfolio", ["input[name*='website' i]", "input[name*='portfolio' i]", "input[placeholder*='portfolio' i]"], portfolio),
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
                    "input[data-qa*='resume' i]",
                    "input[id*='resume' i]",
                ]
                for sel in file_selectors:
                    try:
                        file_input = frame.locator(sel)
                        if file_input.count() > 0:
                            file_input.first.set_input_files(resume_path)
                            filled_any = True
                            logger.info("Attached resume via Ashby selector: %s", sel)
                            break
                    except Exception:
                        pass

        return filled_any

    def submit(self, page: Any) -> Tuple[bool, str]:
        """Click Ashby submit button and confirm receipt."""
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "button:has-text('Submit')",
            "input[type='submit']",
        ]
        clicked = False
        for sel in submit_selectors:
            try:
                if page.is_visible(sel):
                    page.click(sel, force=True, timeout=5000)
                    clicked = True
                    logger.info("Clicked Ashby submit selector: %s", sel)
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
            match = re.search(r"(?:confirmation|application|reference)\s*(?:#|id|code)?[:\s]*([a-z0-9\-_]{4,20})", content, re.IGNORECASE)
            if match:
                confirmation_id = match.group(0).strip()
        except Exception:
            pass

        if confirmed:
            return True, confirmation_id or "ASHBY-SUBMISSION-CONFIRMED"
        if clicked:
            return True, confirmation_id or "ASHBY-SUBMIT-CLICKED"
        return False, "Failed to submit Ashby application"
