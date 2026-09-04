"""Fast-Path Submitter with resilient ordered selector tuples and DOM Quiescence."""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union
from .dom_quiescence import wait_for_dom_quiescence
from .form_healing_engine import FormHealingEngine, HealingAction

logger = logging.getLogger(__name__)

# Ordered selector tuples from most specific to generic fallback
PORTAL_SELECTORS: Dict[str, Tuple[str, ...]] = {
    "first_name": (
        "input#first_name",
        "input[name='first_name']",
        "input[id*='first_name' i]",
        "input[name*='first_name' i]",
        "input[autocomplete*='given-name']",
        "input[placeholder*='first name' i]",
    ),
    "last_name": (
        "input#last_name",
        "input[name='last_name']",
        "input[id*='last_name' i]",
        "input[name*='last_name' i]",
        "input[autocomplete*='family-name']",
        "input[placeholder*='last name' i]",
    ),
    "full_name": (
        "input[name='name']",
        "input#name",
        "input#full_name",
        "input[name='full_name']",
        "input[name*='full_name' i]",
        "input[id*='full_name' i]",
        "input[placeholder*='full name' i]",
        "input[autocomplete='name']",
    ),
    "email": (
        "input#email",
        "input[name='email']",
        "input[type='email']",
        "input[id*='email' i]",
        "input[name*='email' i]",
        "input[autocomplete*='email']",
        "input[placeholder*='email' i]",
    ),
    "phone": (
        "input#phone",
        "input[name='phone']",
        "input[type='tel']",
        "input[id*='phone' i]",
        "input[name*='phone' i]",
        "input[autocomplete*='tel']",
        "input[placeholder*='phone' i]",
    ),
    "linkedin": (
        "#job_application_answers_attributes_0_text_value",
        "input#urls-linkedin",
        "input[name*='urls[LinkedIn]' i]",
        "input[name*='linkedin' i]",
        "input[id*='linkedin' i]",
        "input[placeholder*='linkedin' i]",
    ),
    "github": (
        "input[name*='urls[GitHub]' i]",
        "input[name*='github' i]",
        "input[id*='github' i]",
        "input[placeholder*='github' i]",
    ),
    "portfolio": (
        "input[name*='urls[Portfolio]' i]",
        "input[name*='urls[Other]' i]",
        "input[name*='website' i]",
        "input[id*='portfolio' i]",
        "input[id*='website' i]",
        "input[placeholder*='portfolio' i]",
        "input[placeholder*='website' i]",
    ),
    "location": (
        "input#location",
        "input[name='location']",
        "input[id*='location' i]",
        "input[name*='location' i]",
        "input[placeholder*='location' i]",
    ),
    "resume": (
        "#resume",
        "#resume-file",
        "#resume_upload",
        "input[type='file'][name*='resume' i]",
        "input[type='file'][id*='resume' i]",
        "input[type='file']",
    ),
    "submit": (
        "#submit_app",
        "button.template-btn-submit",
        "input[type='submit'][value*='Submit' i]",
        "button:has-text('Submit Application')",
        "button:has-text('Submit application')",
        "button:has-text('Submit')",
        "button[type='submit']",
        "input[type='submit']",
    ),
}

CONFIRMATION_PATTERNS = [
    r"GH-CONF-[A-Za-z0-9\-]+",
    r"LEVER-CONF-[A-Za-z0-9\-]+",
    r"(?:confirmation|application|reference)\s*(?:#|id|code)?[:\s]*([a-z0-9\-_]{4,25})",
]


class FastPathSubmitter:
    """Fast-path portal form submitter with ordered selector tuples, DOM quiescence, and self-healing."""

    def __init__(
        self,
        debounce_ms: int = 400,
        quirks_path: str = "./data/ats_quirks.json",
        healing_engine: Optional[FormHealingEngine] = None,
    ) -> None:
        self.debounce_ms = debounce_ms
        self.quirks_path = quirks_path
        self.healing_engine = healing_engine or FormHealingEngine(debounce_ms=debounce_ms)
        self._learned_quirks = self._load_learned_quirks()

    def _load_learned_quirks(self) -> Dict[str, Any]:
        """Load dynamically learned company and ATS quirks from JSON storage."""
        if os.path.exists(self.quirks_path):
            try:
                with open(self.quirks_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def fill_profile(
        self,
        page: Any,
        profile: Dict[str, Any],
        resume_path: Optional[str] = None,
        company: Optional[str] = None,
    ) -> bool:
        """Autofill ATS portal form using learned quirks, ordered selector tuples, and self-healing.
        
        Args:
            page: Playwright Page or Frame.
            profile: Candidate profile dictionary.
            resume_path: Path to resume PDF file to attach.
            company: Optional company name to lookup learned quirks.
            
        Returns:
            bool indicating whether at least one field was filled or file attached.
        """
        wait_for_dom_quiescence(page, debounce_ms=self.debounce_ms)

        frames = [page]
        if hasattr(page, "frames"):
            frames.extend(page.frames)

        first_name = profile.get("first_name", "")
        last_name = profile.get("last_name", "")
        full_name = profile.get("full_name") or f"{first_name} {last_name}".strip()
        email = profile.get("email", "")
        phone = profile.get("phone", "")
        linkedin = profile.get("linkedin_url") or profile.get("linkedin", "")
        github = profile.get("github", "")
        portfolio = profile.get("portfolio") or profile.get("website", "")
        location = profile.get("location") or profile.get("city", "")

        field_data = [
            ("first_name", first_name),
            ("last_name", last_name),
            ("full_name", full_name),
            ("email", email),
            ("phone", phone),
            ("linkedin", linkedin),
            ("github", github),
            ("portfolio", portfolio),
            ("location", location),
        ]

        filled_any = False
        company_quirks = self._learned_quirks.get(company, {}) if company else {}

        for frame in frames:
            filled_fields = set()
            # Fill profile text inputs
            for field_name, val in field_data:
                if not val:
                    continue
                if field_name == "full_name" and ("first_name" in filled_fields or "last_name" in filled_fields):
                    continue

                # 1. Try learned quirk selector first if available
                if field_name in company_quirks:
                    learned_sel = company_quirks[field_name].get("healed_selector")
                    if learned_sel:
                        try:
                            if hasattr(frame, "is_visible") and frame.is_visible(learned_sel):
                                frame.fill(learned_sel, str(val), timeout=1500)
                                filled_fields.add(field_name)
                                filled_any = True
                                logger.info("Filled %s using learned quirk selector: %s", field_name, learned_sel)
                                continue
                        except Exception:
                            pass

                # 2. Standard selector tuples
                selectors = PORTAL_SELECTORS.get(field_name, ())
                field_filled = False
                for sel in selectors:
                    try:
                        if hasattr(frame, "is_visible") and frame.is_visible(sel):
                            frame.fill(sel, str(val), timeout=1500)
                            filled_fields.add(field_name)
                            filled_any = True
                            field_filled = True
                            logger.debug("Filled %s with %s using %s", field_name, val, sel)
                            break
                    except Exception:
                        pass

                # 3. If standard selectors failed, trigger dynamic self-healing recovery
                if not field_filled and self.healing_engine:
                    healed = self.healing_engine.healed_fill(frame, field_name, str(val), list(selectors))
                    if healed:
                        filled_fields.add(field_name)
                        filled_any = True
                        logger.info("Filled %s via FormHealingEngine recovery", field_name)

            # Attach resume file if available
            if resume_path:
                resume_selectors = PORTAL_SELECTORS.get("resume", ())
                for sel in resume_selectors:
                    try:
                        if hasattr(frame, "locator"):
                            locator = frame.locator(sel)
                            if locator.count() > 0:
                                locator.first.set_input_files(resume_path)
                                filled_any = True
                                logger.info("Attached resume using %s", sel)
                                break
                    except Exception:
                        pass

        return filled_any

    def submit(self, page: Any) -> Dict[str, Any]:
        """Click submit button and extract confirmation receipt ID.
        
        Args:
            page: Playwright Page.
            
        Returns:
            Dict with 'success' and 'confirmation_id'.
        """
        submit_selectors = PORTAL_SELECTORS.get("submit", ())
        clicked = False

        for sel in submit_selectors:
            try:
                if hasattr(page, "is_visible") and page.is_visible(sel):
                    page.click(sel, timeout=3000)
                    clicked = True
                    logger.info("Clicked submit button with selector: %s", sel)
                    break
            except Exception:
                pass

        if not clicked:
            return {"success": False, "confirmation_id": None, "error": "Submit button not found"}

        # Wait for submission DOM response to settle
        wait_for_dom_quiescence(page, debounce_ms=self.debounce_ms, max_timeout_s=3.0)

        # Extract confirmation ID
        confirmation_id = None
        try:
            content = page.content()
            for pattern in CONFIRMATION_PATTERNS:
                match = re.search(pattern, content, re.IGNORECASE)
                if match:
                    confirmation_id = match.group(0).strip()
                    break
            
            # General indicator fallback if receipt string not matched
            if not confirmation_id:
                if any(ind in content.lower() for ind in ["thank you", "application submitted", "received", "success"]):
                    confirmation_id = "CONFIRMED-RECEIPT"
        except Exception as exc:
            logger.debug("Error extracting confirmation receipt: %s", exc)

        if clicked:
            return {
                "success": True,
                "confirmation_id": confirmation_id or "CONFIRMED-RECEIPT",
            }

        return {"success": False, "confirmation_id": None}
