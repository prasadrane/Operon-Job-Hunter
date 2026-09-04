"""Form Healing Engine: Runtime locator recovery, validation diagnosis, and pointer event cascades."""

from dataclasses import asdict, dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealingAction(str, Enum):
    SELECTOR_RECOVERY = "selector_recovery"
    FORMAT_SANITIZATION = "format_sanitization"
    POINTER_CASCADE = "pointer_cascade"
    RETRY_AFTER_QUIESCENCE = "retry_after_quiescence"


@dataclass
class HealingEvent:
    company: str
    portal_type: str
    field_name: str
    original_selector: str
    healed_selector: str
    action: HealingAction
    details: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event": "form_healing_event",
            "span_id": f"heal_{int(self.timestamp * 1000)}",
            "tokens": 0,
            "metadata": {
                "company": self.company,
                "portal_type": self.portal_type,
                "field_name": self.field_name,
                "original_selector": self.original_selector,
                "healed_selector": self.healed_selector,
                "action": self.action.value if isinstance(self.action, HealingAction) else str(self.action),
                "details": self.details,
                "timestamp": self.timestamp,
            },
        }


class FormHealingEngine:
    """Runtime self-healing engine for repairing failed form interactions and format errors."""

    # Fuzzy keywords mapped to standard field names
    FIELD_LABEL_KEYWORDS: Dict[str, List[str]] = {
        "first_name": ["first name", "given name", "forename", "legal first name"],
        "last_name": ["last name", "family name", "surname", "legal last name"],
        "full_name": ["full name", "your name", "candidate name"],
        "email": ["email", "e-mail", "email address"],
        "phone": ["phone", "mobile", "cell", "telephone", "phone number"],
        "linkedin": ["linkedin", "linkedin profile", "linkedin url"],
        "github": ["github", "github profile", "github url"],
        "portfolio": ["portfolio", "website", "personal site", "other url"],
        "location": ["location", "city", "current city", "street address"],
        "resume": ["resume", "cv", "attach resume", "curriculum vitae"],
    }

    # Exclusion patterns to prevent accidental cross-field matches
    FIELD_EXCLUSIONS: Dict[str, List[str]] = {
        "location": ["email", "e-mail", "phone", "name", "resume"],
        "first_name": ["last", "family", "surname", "full", "email", "phone"],
        "last_name": ["first", "given", "forename", "full", "email", "phone"],
        "phone": ["email", "name", "address"],
        "email": ["phone", "name", "address"],
    }

    def __init__(self, debounce_ms: int = 400) -> None:
        self.debounce_ms = debounce_ms

    def _is_safe_element(self, el_selector: str, field_name: str, page_or_frame: Any) -> bool:
        """Verify element attributes do not conflict with excluded fields."""
        exclusions = self.FIELD_EXCLUSIONS.get(field_name, [])
        if not exclusions:
            return True

        try:
            loc = page_or_frame.locator(el_selector).first
            inp_type = (loc.get_attribute("type") or "").lower()
            inp_name = (loc.get_attribute("name") or "").lower()
            inp_id = (loc.get_attribute("id") or "").lower()
            inp_placeholder = (loc.get_attribute("placeholder") or "").lower()
            inp_aria = (loc.get_attribute("aria-label") or "").lower()

            combined = f"{inp_type} {inp_name} {inp_id} {inp_placeholder} {inp_aria}"
            for exc in exclusions:
                if exc in combined:
                    return False
            return True
        except Exception:
            return True

    def extract_validation_errors(self, page_or_frame: Any) -> List[str]:
        """Extract visible form validation errors and ARIA error references."""
        found_errors: List[str] = []

        # 1. Resolve aria-invalid inputs with aria-describedby or aria-errormessage
        try:
            invalid_inputs = page_or_frame.locator('[aria-invalid="true"]')
            if invalid_inputs.count() > 0:
                for inp in invalid_inputs.all():
                    for attr in ["aria-describedby", "aria-errormessage"]:
                        raw_attr = inp.get_attribute(attr)
                        if raw_attr:
                            for msg_id in raw_attr.split():
                                msg_loc = page_or_frame.locator(f"#{msg_id}")
                                if msg_loc.count() > 0 and msg_loc.first.is_visible():
                                    txt = msg_loc.first.inner_text().strip()
                                    if txt and txt not in found_errors:
                                        found_errors.append(txt)
        except Exception:
            pass

        # 2. Extract standard error container classes and roles
        error_selectors = [
            '[role="alert"]',
            '[role="status"]',
            '[aria-live="assertive"]',
            '[data-automation-id="errorMessage"]',
            ".invalid-feedback",
            ".field-error",
            ".error-msg",
            ".error-message",
            ".alert-danger",
            "span.error",
        ]
        for sel in error_selectors:
            try:
                loc = page_or_frame.locator(sel)
                if loc.count() > 0:
                    for txt in loc.all_inner_texts():
                        clean = txt.strip()
                        if clean and clean not in found_errors:
                            found_errors.append(clean)
            except Exception:
                pass

        return found_errors

    def auto_format_value(self, field_name: str, raw_val: str, error_context: str = "") -> str:
        """Sanitize and adjust input formatting based on error context."""
        err_lower = error_context.lower()
        val_str = str(raw_val or "").strip()

        if field_name == "phone":
            digits_only = re.sub(r"\D", "", val_str)
            if "10" in err_lower or "ten" in err_lower or "without punctuation" in err_lower:
                # If digits start with US country code '1' and length 11, strip leading 1
                if len(digits_only) == 11 and digits_only.startswith("1"):
                    return digits_only[1:]
                return digits_only[-10:] if len(digits_only) >= 10 else digits_only
            elif "country code" in err_lower or "+1" in err_lower:
                if not val_str.startswith("+"):
                    if len(digits_only) == 10:
                        return f"+1{digits_only}"
                    elif len(digits_only) == 11 and digits_only.startswith("1"):
                        return f"+{digits_only}"
                return re.sub(r"[^\d+]", "", val_str)

        elif field_name == "email":
            return val_str.replace(" ", "").lower()

        elif field_name in ("first_name", "last_name", "full_name"):
            return re.sub(r"\s+", " ", val_str)

        return val_str

    def recover_locator(
        self,
        page_or_frame: Any,
        field_name: str,
        failed_selectors: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Perform semantic fuzzy search to discover inputs whose standard selectors failed."""
        keywords = self.FIELD_LABEL_KEYWORDS.get(field_name, [field_name.replace("_", " ")])

        # 1. Search for <label> elements containing field keywords
        for kw in keywords:
            try:
                labels = page_or_frame.locator(f'label:has-text("{kw}")')
                if labels.count() > 0:
                    for i in range(labels.count()):
                        lbl = labels.nth(i)
                        for_attr = lbl.get_attribute("for")
                        if for_attr:
                            target_id_sel = f"#{for_attr}"
                            if page_or_frame.locator(target_id_sel).count() > 0:
                                if self._is_safe_element(target_id_sel, field_name, page_or_frame):
                                    return target_id_sel
                        # Check if input is nested inside label
                        nested_inp = lbl.locator("input, textarea, select")
                        if nested_inp.count() > 0:
                            nested_id = nested_inp.first.get_attribute("id")
                            if nested_id:
                                sel = f"#{nested_id}"
                                if self._is_safe_element(sel, field_name, page_or_frame):
                                    return sel
                            nested_name = nested_inp.first.get_attribute("name")
                            if nested_name:
                                sel = f"input[name='{nested_name}']"
                                if self._is_safe_element(sel, field_name, page_or_frame):
                                    return sel
            except Exception:
                pass

        # 2. Search inputs by placeholder or aria-label
        for kw in keywords:
            fallback_selectors = [
                f'input[placeholder*="{kw}" i]',
                f'input[aria-label*="{kw}" i]',
                f'textarea[placeholder*="{kw}" i]',
                f'textarea[aria-label*="{kw}" i]',
                f'input[id*="{kw.replace(" ", "_")}" i]',
                f'input[name*="{kw.replace(" ", "_")}" i]',
            ]
            for sel in fallback_selectors:
                try:
                    if page_or_frame.locator(sel).count() > 0 and page_or_frame.locator(sel).first.is_visible():
                        if self._is_safe_element(sel, field_name, page_or_frame):
                            return sel
                except Exception:
                    pass

        return None

    def healed_fill(
        self,
        page_or_frame: Any,
        field_name: str,
        value: str,
        failed_selectors: Optional[List[str]] = None,
    ) -> bool:
        """Attempt to locate healed selector and fill with real keystrokes."""
        recovered_sel = self.recover_locator(page_or_frame, field_name, failed_selectors)
        if not recovered_sel:
            return False

        try:
            loc = page_or_frame.locator(recovered_sel).first
            loc.focus()
            loc.fill(value)
            return True
        except Exception as e:
            logger.debug("Failed healed fill on %s with selector %s: %s", field_name, recovered_sel, e)
            return False

    def dispatch_pointer_cascade(self, page_or_frame: Any, selector: str) -> bool:
        """Dispatch a full sequence of Pointer and Mouse events to bypass click interception overlays."""
        try:
            executed = page_or_frame.evaluate(
                """(sel) => {
                    const el = document.querySelector(sel);
                    if (!el) return false;
                    el.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    if (typeof el.click === 'function') el.click();
                    return true;
                }""",
                selector,
            )
            return bool(executed)
        except Exception as e:
            logger.debug("Pointer cascade execution error on %s: %s", selector, e)
            return False

    def create_healing_event(
        self,
        company: str,
        portal_type: str,
        field_name: str,
        original_selector: str,
        healed_selector: str,
        action: HealingAction,
        details: str,
    ) -> HealingEvent:
        """Create structured HealingEvent for telemetry persistence."""
        return HealingEvent(
            company=company,
            portal_type=portal_type,
            field_name=field_name,
            original_selector=original_selector,
            healed_selector=healed_selector,
            action=action,
            details=details,
        )
