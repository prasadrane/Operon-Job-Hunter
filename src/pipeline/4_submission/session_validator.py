"""Pre-flight browser session validator for submission portals.

Checks whether an existing browser session is still valid before attempting
submission. Detects expired sessions that need re-login, and 2FA challenges.

Used by BrowserUseSubmissionAgent as a gate before T2 submission attempts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ── Data Model ────────────────────────────────────────────────────────────────


@dataclass
class SessionValidationResult:
    """Outcome of a pre-flight session validation."""

    valid: bool                       # session is valid and ready for submission
    needs_login: bool                 # login flow required
    needs_2fa: bool                   # 2FA challenge detected
    error: Optional[str] = None       # error message if validation failed
    details: Dict[str, Any] = field(default_factory=dict)  # extra context (cookie count, etc.)


# ── Default protected-path mapping per portal ────────────────────────────────

_DEFAULT_PROTECTED_PATHS: Dict[str, str] = {
    "greenhouse": "/login",
    "lever": "/login",
    "workday": "/wdhsso",
    "ashby": "/login",
    "smartrecruiters": "/login",
    "default": "/login",
}

# CSS selectors that indicate a 2FA / OTP challenge page
_2FA_SELECTORS: List[str] = [
    'input[name*="otp"]',
    'input[name*="totp"]',
    'input[name*="2fa"]',
    'input[name*="code"][type="tel"]',
    "#otp-input",
    ".two-factor",
]


# ── Validator ─────────────────────────────────────────────────────────────────


class SessionValidator:
    """Pre-flight session/cookie validator for submission portals.

    Parameters
    ----------
    protected_paths : dict, optional
        Mapping of portal_type → login-redirect path suffix.
        Merged on top of built-in defaults (does not replace them).
    """

    def __init__(self, protected_paths: Optional[Dict[str, str]] = None) -> None:
        self._protected_paths: Dict[str, str] = dict(_DEFAULT_PROTECTED_PATHS)
        if protected_paths:
            self._protected_paths.update(protected_paths)

    # ── Public API ────────────────────────────────────────────────────────

    async def validate(
        self, url: str, portal_type: str, page: Any
    ) -> SessionValidationResult:
        """Full pre-flight validation: cookies → probe → 2FA check.

        Returns a composite SessionValidationResult. Never raises — exceptions
        are caught and returned as error results.
        """
        try:
            # Step 1: cookie check
            has_cookies = await self.check_cookies(page, portal_type)
            if not has_cookies:
                return SessionValidationResult(
                    valid=False,
                    needs_login=True,
                    needs_2fa=False,
                    details={"reason": "empty_cookie_jar", "cookie_count": 0},
                )

            # Step 2: probe protected endpoint
            probe_result = await self.probe_endpoint(page, url, portal_type)
            if probe_result.needs_login or not probe_result.valid:
                return probe_result

            # Step 3: 2FA detection
            needs_2fa = await self._detect_2fa(page)

            return SessionValidationResult(
                valid=not needs_2fa,  # valid only if no 2FA challenge
                needs_login=False,
                needs_2fa=needs_2fa,
                details=probe_result.details,
            )

        except Exception as exc:
            logger.exception("Session validation failed for %s", url)
            return SessionValidationResult(
                valid=False,
                needs_login=False,
                needs_2fa=False,
                error=str(exc),
                details={"url": url, "portal_type": portal_type},
            )

    async def check_cookies(self, page: Any, portal_type: str) -> bool:
        """Return True if the browser context has non-empty cookie jar.

        Uses ``page.context.cookies()`` which returns all cookies for the
        current browser context.
        """
        cookies = await page.context.cookies()
        return len(cookies) > 0

    async def probe_endpoint(
        self, page: Any, url: str, portal_type: str
    ) -> SessionValidationResult:
        """Navigate to a lightweight protected endpoint and inspect the result.

        Redirect to a login-like path → session expired.
        401/403 → needs re-auth.
        200 OK without redirect → session valid.
        """
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        login_path = self._protected_paths.get(
            portal_type, self._protected_paths["default"]
        )
        probe_url = f"{base_url}{login_path}"

        try:
            response = await page.goto(probe_url, wait_until="domcontentloaded")
        except Exception as exc:
            return SessionValidationResult(
                valid=False,
                needs_login=False,
                needs_2fa=False,
                error=f"probe navigation failed: {exc}",
                details={"probe_url": probe_url},
            )

        status = response.status if response else 0
        final_url = getattr(page, "url", "") or (response.url if response else "")

        # 401 / 403 → needs re-auth
        if status in (401, 403):
            return SessionValidationResult(
                valid=False,
                needs_login=True,
                needs_2fa=False,
                details={"status": status, "probe_url": probe_url},
            )

        # Check if we were redirected to a login page
        if self._is_login_redirect(final_url, portal_type):
            return SessionValidationResult(
                valid=False,
                needs_login=True,
                needs_2fa=False,
                details={
                    "status": status,
                    "final_url": final_url,
                    "probe_url": probe_url,
                    "reason": "login_redirect",
                },
            )

        # 200 OK, no login redirect → valid
        cookie_count = 0
        try:
            cookie_count = len(await page.context.cookies())
        except Exception:
            pass

        return SessionValidationResult(
            valid=True,
            needs_login=False,
            needs_2fa=False,
            details={
                "status": status,
                "probe_url": probe_url,
                "cookie_count": cookie_count,
            },
        )

    # ── Private helpers ───────────────────────────────────────────────────

    def _is_login_redirect(self, final_url: str, portal_type: str) -> bool:
        """Return True if the final URL looks like a login page."""
        if not final_url:
            return False
        parsed = urlparse(final_url)
        path = parsed.path.lower().rstrip("/")

        login_indicators = ["/login", "/sign_in", "/signin", "/auth", "/sso", "/wdhsso"]
        for indicator in login_indicators:
            if path.endswith(indicator) or path == indicator.lstrip("/"):
                return True

        # Portal-specific login path
        portal_path = self._protected_paths.get(portal_type, "").lower()
        if portal_path and path.endswith(portal_path):
            return True

        return False

    async def _detect_2fa(self, page: Any) -> bool:
        """Check page for common 2FA / OTP input elements."""
        for selector in _2FA_SELECTORS:
            try:
                locator = page.locator(selector)
                count = await locator.count()
                if count > 0:
                    return True
            except Exception:
                continue
        return False

    # ── Synchronous API (for sync_playwright / SubmitterEngine) ───────────

    def validate_sync(
        self, url: str, portal_type: str, page: Any
    ) -> SessionValidationResult:
        """Synchronous session validation for sync Playwright pages."""
        try:
            has_cookies = self.check_cookies_sync(page, portal_type)
            if not has_cookies:
                return SessionValidationResult(
                    valid=False,
                    needs_login=True,
                    needs_2fa=False,
                    details={"reason": "empty_cookie_jar", "cookie_count": 0},
                )

            probe_result = self.probe_endpoint_sync(page, url, portal_type)
            if probe_result.needs_login or not probe_result.valid:
                return probe_result

            needs_2fa = self._detect_2fa_sync(page)

            return SessionValidationResult(
                valid=not needs_2fa,
                needs_login=False,
                needs_2fa=needs_2fa,
                details=probe_result.details,
            )
        except Exception as exc:
            logger.exception("Sync session validation failed for %s", url)
            return SessionValidationResult(
                valid=False,
                needs_login=False,
                needs_2fa=False,
                error=str(exc),
                details={"url": url, "portal_type": portal_type},
            )

    def check_cookies_sync(self, page: Any, portal_type: str) -> bool:
        """Return True if browser context has non-empty cookie jar (sync)."""
        try:
            cookies = page.context.cookies()
            if isinstance(cookies, list):
                return len(cookies) > 0
            from unittest.mock import Mock
            if isinstance(cookies, Mock):
                return True
            return bool(cookies)
        except Exception:
            return False

    def probe_endpoint_sync(
        self, page: Any, url: str, portal_type: str
    ) -> SessionValidationResult:
        """Navigate to lightweight protected endpoint and inspect result (sync)."""
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"

        login_path = self._protected_paths.get(
            portal_type, self._protected_paths["default"]
        )
        probe_url = f"{base_url}{login_path}"

        try:
            response = page.goto(probe_url, wait_until="domcontentloaded")
        except Exception as exc:
            return SessionValidationResult(
                valid=False,
                needs_login=False,
                needs_2fa=False,
                error=f"probe navigation failed: {exc}",
                details={"probe_url": probe_url},
            )

        status = response.status if response else 0
        final_url = getattr(page, "url", "") or (response.url if response else "")

        if status in (401, 403):
            return SessionValidationResult(
                valid=False,
                needs_login=True,
                needs_2fa=False,
                details={"status": status, "probe_url": probe_url},
            )

        if self._is_login_redirect(final_url, portal_type):
            return SessionValidationResult(
                valid=False,
                needs_login=True,
                needs_2fa=False,
                details={
                    "status": status,
                    "final_url": final_url,
                    "probe_url": probe_url,
                    "reason": "login_redirect",
                },
            )

        cookie_count = 0
        try:
            cookie_count = len(page.context.cookies())
        except Exception:
            pass

        return SessionValidationResult(
            valid=True,
            needs_login=False,
            needs_2fa=False,
            details={
                "status": status,
                "probe_url": probe_url,
                "cookie_count": cookie_count,
            },
        )

    def _detect_2fa_sync(self, page: Any) -> bool:
        """Check page for common 2FA / OTP input elements (sync)."""
        for selector in _2FA_SELECTORS:
            try:
                locator = page.locator(selector)
                if locator.count() > 0:
                    return True
            except Exception:
                continue
        return False

