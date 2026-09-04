"""Modular command handlers for Playwright browser actions."""

from __future__ import annotations

import abc
import inspect
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class BaseActionHandler(abc.ABC):
    """Abstract base class for atomic Playwright browser action handlers."""

    @abc.abstractmethod
    def execute(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        """Execute action synchronously."""
        pass

    @abc.abstractmethod
    async def execute_async(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        """Execute action asynchronously."""
        pass


class TypeActionHandler(BaseActionHandler):
    """Handles text typing and field filling."""

    def execute(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        text_to_fill = str(action.get("text", action.get("value", "")))
        page.fill(selector, text_to_fill)
        return True

    async def execute_async(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        text_to_fill = str(action.get("text", action.get("value", "")))
        await page.fill(selector, text_to_fill)
        return True


class ClickActionHandler(BaseActionHandler):
    """Handles element clicking."""

    def execute(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        page.click(selector)
        return True

    async def execute_async(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        await page.click(selector)
        return True


class SelectActionHandler(BaseActionHandler):
    """Handles dropdown option selection."""

    def execute(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        option_val = action.get("value") or action.get("text") or action.get("option", "")
        page.select_option(selector, str(option_val))
        return True

    async def execute_async(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        option_val = action.get("value") or action.get("text") or action.get("option", "")
        await page.select_option(selector, str(option_val))
        return True


class UploadActionHandler(BaseActionHandler):
    """Handles file attachment and resume uploads."""

    def execute(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        file_path = action.get("file_path") or action.get("path", "")
        page.set_input_files(selector, str(file_path))
        return True

    async def execute_async(self, selector: str, action: Dict[str, Any], page: Any) -> bool:
        file_path = action.get("file_path") or action.get("path", "")
        await page.set_input_files(selector, str(file_path))
        return True
