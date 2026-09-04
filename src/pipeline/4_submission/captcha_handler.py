"""Captcha detection and human-in-the-loop solver handler."""

import importlib
import logging
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

CAPTCHA_SELECTORS: List[str] = [
    # Cloudflare Turnstile & Challenges
    "iframe[src*='challenges.cloudflare.com']",
    "iframe[src*='turnstile']",
    ".cf-turnstile",
    "#turnstile-wrapper",
    "#challenge-running",
    "#cf-challenge",
    "div[class*='cf-turnstile']",

    # Google reCAPTCHA
    "iframe[src*='recaptcha']",
    "iframe[src*='google.com/recaptcha']",
    ".g-recaptcha",
    "div.recaptcha",
    "#g-recaptcha-response",

    # hCaptcha
    "iframe[src*='hcaptcha']",
    "iframe[src*='hcaptcha.com']",
    ".h-captcha",
    "div.hcaptcha",

    # Arkose Labs / FunCaptcha
    "iframe[src*='arkoselabs']",
    "iframe[src*='funcaptcha']",

    # 2FA & Security Verification
    "input[data-automation-id='securityCode']",
    "input[autocomplete='one-time-code']",
    "input[name*='verificationCode' i]",
    "input[name*='securityCode' i]",
]

CAPTCHA_TEXT_INDICATORS: List[str] = [
    "cf-turnstile",
    "g-recaptcha",
    "hcaptcha",
    "verify you are human",
    "please verify you are human",
    "please verify you are a human",
    "checking your browser before accessing",
    "enter verification code",
    "two-factor authentication",
    "two-step verification",
    "security verification",
    "security check",
]


class CaptchaHandler:
    """Detects bot challenges, captchas, and 2FA prompts on the page."""

    def __init__(
        self,
        timeout_sec: int = 60,
        poll_interval: float = 1.0,
        capsolver_api_key: Optional[str] = None,
        captcha_auto_solve: bool = False,
        capsolver_timeout_sec: int = 120,
    ) -> None:
        """Initialize captcha handler.

        Args:
            timeout_sec: HITL timeout waiting for human solve
            poll_interval: Seconds between HITL polls
            capsolver_api_key: CapSolver API key (None = no auto-solve)
            captcha_auto_solve: Enable automatic CapSolver
            capsolver_timeout_sec: CapSolver task timeout
        """
        self.timeout_sec = timeout_sec
        self.poll_interval = poll_interval
        self.capsolver_api_key = capsolver_api_key
        self.captcha_auto_solve = captcha_auto_solve
        self.capsolver_timeout_sec = capsolver_timeout_sec
        self._capsolver_client = None

    def detect_captcha(self, page: Any) -> bool:
        """Inspect page DOM, frames, and text for active CAPTCHA or 2FA challenge."""
        if page is None:
            return False

        # 1. Inspect DOM selector presence
        for selector in CAPTCHA_SELECTORS:
            try:
                locator = page.locator(selector)
                if locator and locator.count() > 0:
                    logger.info("Captcha detected by selector: %s", selector)
                    return True
            except Exception:
                pass

        # 2. Inspect page text content indicators
        try:
            if hasattr(page, "content"):
                content = str(page.content()).lower()
                for indicator in CAPTCHA_TEXT_INDICATORS:
                    if indicator in content:
                        logger.info("Captcha detected by text indicator: %s", indicator)
                        return True
        except Exception:
            pass

        return False

    def wait_for_human_solve(
        self,
        page: Any,
        timeout_sec: Optional[int] = None,
        poll_interval: Optional[float] = None,
    ) -> bool:
        """Wait for human user to solve CAPTCHA / 2FA in persistent browser window."""
        timeout = timeout_sec if timeout_sec is not None else self.timeout_sec
        interval = poll_interval if poll_interval is not None else self.poll_interval
        start_time = time.time()

        logger.warning(
            "⚠️ CAPTCHA / Security verification detected. Waiting up to %s seconds for human solve...",
            timeout,
        )

        while time.time() - start_time < timeout:
            time.sleep(interval)
            try:
                if not self.detect_captcha(page):
                    logger.info("✅ CAPTCHA solved or challenge passed!")
                    return True
            except Exception as e:
                logger.warning("Error checking captcha state during polling: %s", e)

        logger.error("❌ CAPTCHA wait timed out after %s seconds.", timeout)
        try:
            from src.core.db.error_log import log_error
            log_error(
                source="submission",
                component="captcha_handler",
                error_type="CAPTCHA_TIMEOUT",
                message=f"CAPTCHA wait timed out after {timeout} seconds",
                metadata={"timeout": timeout},
            )
        except Exception:
            pass
        return False

    def handle_captcha(
        self,
        page: Any,
        site_key: str,
        page_url: str,
        captcha_type: str = "recaptcha",
    ) -> Optional[str]:
        """Handle detected captcha with auto-solve or HITL fallback.

        Attempts CapSolver if enabled + API key present. Falls back to
        HITL (wait_for_human_solve) if auto-solve disabled, no API key,
        or CapSolver fails.

        Args:
            page: Playwright page object
            site_key: Captcha site key from page
            page_url: URL where captcha appears
            captcha_type: Type of captcha ("recaptcha", "hcaptcha", "turnstile")

        Returns:
            Solved token string on success, None if HITL fallback or timeout
        """
        # Check if auto-solve is enabled and API key available
        if not self.captcha_auto_solve or not self.capsolver_api_key:
            logger.info("CapSolver auto-solve disabled or no API key, falling back to HITL")
            return self._fallback_to_hitl(page)

        # Attempt auto-solve with CapSolver
        try:
            return self._auto_solve_captcha(page, site_key, page_url, captcha_type)
        except Exception as e:
            logger.warning("CapSolver auto-solve failed: %s. Falling back to HITL", e)
            return self._fallback_to_hitl(page)

    def _auto_solve_captcha(
        self,
        page: Any,
        site_key: str,
        page_url: str,
        captcha_type: str,
    ) -> Optional[str]:
        """Attempt to solve captcha via CapSolver API.

        Args:
            page: Playwright page object
            site_key: Captcha site key
            page_url: URL where captcha appears
            captcha_type: Type of captcha

        Returns:
            Solved token string

        Raises:
            CapSolverError: If API returns error
            CapSolverTimeoutError: If task times out
        """
        # Lazy import to avoid circular dependency
        cs_mod = importlib.import_module("src.pipeline.4_submission.capsolver_client")
        CapSolverClient = cs_mod.CapSolverClient

        if self._capsolver_client is None:
            self._capsolver_client = CapSolverClient(
                api_key=self.capsolver_api_key,
                timeout_sec=self.capsolver_timeout_sec,
            )

        logger.info("Attempting CapSolver auto-solve for %s captcha", captcha_type)

        # Route to appropriate solver method
        if captcha_type == "recaptcha":
            token = self._capsolver_client.solve_recaptcha(site_key=site_key, page_url=page_url)
        elif captcha_type == "hcaptcha":
            token = self._capsolver_client.solve_hcaptcha(site_key=site_key, page_url=page_url)
        elif captcha_type == "turnstile":
            token = self._capsolver_client.solve_turnstile(site_key=site_key, page_url=page_url)
        else:
            raise ValueError(f"Unsupported captcha type: {captcha_type}")

        # Inject token into page if possible
        self._inject_captcha_token(page, token, captcha_type)

        return token

    def _inject_captcha_token(
        self,
        page: Any,
        token: str,
        captcha_type: str,
    ) -> None:
        """Inject solved token into page DOM.

        Args:
            page: Playwright page object
            token: Solved captcha token
            captcha_type: Type of captcha
        """
        try:
            if captcha_type == "recaptcha":
                # Set reCAPTCHA response field
                page.evaluate(f"""
                    document.getElementById('g-recaptcha-response').innerHTML = '{token}';
                    if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {{
                        Object.keys(window.___grecaptcha_cfg.clients).forEach(key => {{
                            var client = window.___grecaptcha_cfg.clients[key];
                            if (client.callback) {{
                                client.callback('{token}');
                            }}
                        }});
                    }}
                """)
            elif captcha_type == "hcaptcha":
                # Set hCaptcha response field
                page.evaluate(f"""
                    document.getElementById('h-captcha-response').innerHTML = '{token}';
                """)
            elif captcha_type == "turnstile":
                # Set Turnstile response field
                page.evaluate(f"""
                    document.querySelector('[name="cf-turnstile-response"]').value = '{token}';
                """)
            logger.info("Injected %s token into page", captcha_type)
        except Exception as e:
            logger.warning("Failed to inject captcha token: %s", e)

    def _fallback_to_hitl(self, page: Any) -> Optional[str]:
        """Fall back to human-in-the-loop solve.

        Args:
            page: Playwright page object

        Returns:
            None (HITL is blocking, returns None to signal caller)
        """
        logger.warning("Falling back to HITL for captcha solve")
        solved = self.wait_for_human_solve(page, timeout_sec=self.timeout_sec)
        # Return None to signal HITL was used (token not available)
        return None if not solved else None
