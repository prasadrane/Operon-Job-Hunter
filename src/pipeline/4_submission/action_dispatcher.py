"""Action Dispatcher executing structured browser actions via Playwright [data-bid='{bid}'] selectors."""

import inspect
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


from .handlers import (
    BaseActionHandler,
    ClickActionHandler,
    SelectActionHandler,
    TypeActionHandler,
    UploadActionHandler,
)

_HANDLERS: Dict[str, BaseActionHandler] = {
    "type": TypeActionHandler(),
    "fill": TypeActionHandler(),
    "click": ClickActionHandler(),
    "select": SelectActionHandler(),
    "select_option": SelectActionHandler(),
    "upload_file": UploadActionHandler(),
    "file_upload": UploadActionHandler(),
    "set_input_files": UploadActionHandler(),
}


class ActionDispatcher:
    """Dispatches atomic structured actions to Playwright pages targeting data-bid identifiers."""

    def __init__(self, custom_handlers: Optional[Dict[str, BaseActionHandler]] = None) -> None:
        self.handlers = dict(_HANDLERS)
        if custom_handlers:
            self.handlers.update(custom_handlers)

    def execute(self, action: Dict[str, Any], page: Any) -> bool:
        """Execute a structured browser action on a synchronous Playwright page.

        Args:
            action: Dictionary specifying command ('type', 'click', 'select_option', 'upload_file', 'stop') and parameters.
            page: Playwright Page instance.

        Returns:
            True if action was successfully executed or gracefully acknowledged, False otherwise.
        """
        if not action or not isinstance(action, dict):
            return False

        command = action.get("command")
        if command == "stop":
            logger.info("WebSurfer requested stop: reason=%s", action.get("reason", "unknown"))
            return True

        bid = action.get("bid")
        if bid is None or not page:
            return False

        selector = f"[data-bid='{bid}']"

        try:
            # Check visibility if is_visible method is available
            if hasattr(page, "is_visible"):
                visible = page.is_visible(selector)
                # If page.is_visible returns a coroutine in unexpected async context, fallback safely
                if inspect.isawaitable(visible):
                    logger.warning("execute() received an async page object; please use execute_async() instead.")
                    return False
                if not visible:
                    logger.warning("Target element with selector '%s' is not visible on page", selector)
                    return False

            handler = self.handlers.get(command)
            if not handler:
                logger.warning("Unrecognized command '%s' in action payload: %s", command, action)
                return False

            return handler.execute(selector, action, page)

        except Exception as e:
            logger.error("Failed to execute command '%s' on selector '%s': %s", command, selector, e)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="submission",
                    component="action_dispatcher",
                    error_type="BROWSER_ACTION_ERROR",
                    message=f"Failed to execute command '{command}' on selector '{selector}': {e}",
                    metadata={"command": command, "selector": selector},
                )
            except Exception:
                pass
            return False

    async def execute_async(self, action: Dict[str, Any], page: Any) -> bool:
        """Execute a structured browser action on an asynchronous Playwright page.

        Args:
            action: Dictionary specifying command ('type', 'click', 'select_option', 'upload_file', 'stop') and parameters.
            page: Playwright Async Page instance.

        Returns:
            True if action was successfully executed or gracefully acknowledged, False otherwise.
        """
        if not action or not isinstance(action, dict):
            return False

        command = action.get("command")
        if command == "stop":
            logger.info("WebSurfer requested stop (async): reason=%s", action.get("reason", "unknown"))
            return True

        bid = action.get("bid")
        if bid is None or not page:
            return False

        selector = f"[data-bid='{bid}']"

        try:
            if hasattr(page, "is_visible"):
                visible = page.is_visible(selector)
                if inspect.isawaitable(visible):
                    visible = await visible
                if not visible:
                    logger.warning("Target async element '%s' is not visible on page", selector)
                    return False

            handler = self.handlers.get(command)
            if not handler:
                logger.warning("Unrecognized async command '%s' in action payload: %s", command, action)
                return False

            return await handler.execute_async(selector, action, page)

        except Exception as e:
            logger.error("Failed to execute async command '%s' on selector '%s': %s", command, selector, e)
            try:
                from src.core.db.error_log import log_error
                log_error(
                    source="submission",
                    component="action_dispatcher",
                    error_type="BROWSER_ACTION_ERROR",
                    message=f"Failed to execute async command '{command}' on selector '{selector}': {e}",
                    metadata={"command": command, "selector": selector},
                )
            except Exception:
                pass
            return False
