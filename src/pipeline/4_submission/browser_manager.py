"""Browser manager for persistent Patchright sessions with built-in anti-detection."""

import logging
import os
from typing import Any, Dict, List, Optional
from patchright.sync_api import BrowserContext, Playwright

from src.core.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/127.0.0.0 Safari/537.36"
)


class BrowserManager:
    """Manages persistent Patchright browser context lifecycle.

    Patchright is a drop-in Playwright fork with built-in anti-detection:
    WebDriver masking, Chrome runtime injection, plugin/language spoofing,
    and WebGL/Canvas fingerprint randomization — no init scripts needed.
    """

    def __init__(
        self,
        user_data_dir: Optional[str] = None,
        headless: bool = True,
        viewport: Optional[Dict[str, int]] = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        settings = get_settings()
        self.user_data_dir = user_data_dir or settings.browser_profile_dir or "./data/browser_profile"
        self.headless = headless
        self.viewport = viewport or {"width": 1920, "height": 1080}
        self.user_agent = user_agent
        os.makedirs(self.user_data_dir, exist_ok=True)

    def _clean_stale_locks(self) -> None:
        """Remove leftover Chromium singleton lockfiles that block browser launching."""
        if not os.path.exists(self.user_data_dir):
            return
        lock_files = ["SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"]
        for root, _, files in os.walk(self.user_data_dir):
            for file in files:
                if file in lock_files or file.startswith("Singleton"):
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        logger.debug("Removed stale lockfile: %s", file_path)
                    except Exception as e:
                        logger.warning("Failed to remove stale lockfile %s: %s", file_path, e)

    def create_context(self, playwright: Playwright) -> BrowserContext:
        """Launch and configure persistent browser context.

        Patchright handles anti-detection natively — no stealth init scripts
        or playwright-stealth injection needed.
        """
        self._clean_stale_locks()
        launch_args: List[str] = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--window-position=0,0",
            "--ignore-certificate-errors",
            "--ignore-certificate-errors-spki-list",
        ]

        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                viewport=self.viewport,
                user_agent=self.user_agent,
                args=launch_args,
            )
        except Exception as err:
            logger.warning("First launch attempt failed (%s), retrying after lock cleanup...", err)
            self._clean_stale_locks()
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                viewport=self.viewport,
                user_agent=self.user_agent,
                args=launch_args,
            )

        return context
