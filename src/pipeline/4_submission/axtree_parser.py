"""AXTree Perception Engine for accessibility tree parsing and live DOM BID injection."""

from dataclasses import dataclass
import inspect
import logging
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Default interactive roles extracted from Accessibility Tree
INTERACTIVE_ROLES: Set[str] = {
    "textbox",
    "button",
    "combobox",
    "checkbox",
    "radio",
    "link",
    "file_upload",
    "searchbox",
    "switch",
    "slider",
    "spinbutton",
    "menuitem",
    "tab",
    "listbox",
}

# JavaScript to inject unique sequential data-bid attributes into visible interactive DOM elements
INJECT_BID_JS: str = """
() => {
    try {
        const existing = document.querySelectorAll('[data-bid]');
        existing.forEach(el => el.removeAttribute('data-bid'));

        const selector = [
            'input:not([type="hidden"])',
            'button',
            'select',
            'textarea',
            'a[href]',
            '[role="button"]',
            '[role="link"]',
            '[role="checkbox"]',
            '[role="radio"]',
            '[role="combobox"]',
            '[role="textbox"]',
            '[role="menuitem"]',
            '[role="switch"]',
            '[role="tab"]',
            '[tabindex]:not([tabindex="-1"])'
        ].join(', ');

        const elements = Array.from(document.querySelectorAll(selector));
        let bidCounter = 1;

        for (const el of elements) {
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                continue;
            }
            const rect = el.getBoundingClientRect();
            if (rect.width <= 0 && rect.height <= 0) {
                continue;
            }

            el.setAttribute('data-bid', String(bidCounter));
            bidCounter++;
        }
        return bidCounter - 1;
    } catch (err) {
        return 0;
    }
}
"""


@dataclass
class AXNode:
    """Represents an interactive node extracted from the Accessibility Tree."""

    bid: int
    role: str
    name: str
    value: Optional[str] = None
    children_options: Optional[List[str]] = None


class AXTreeParser:
    """Parses Playwright accessibility tree snapshots into structured interactive AXNodes."""

    def __init__(self, interactive_roles: Optional[Set[str]] = None) -> None:
        self.interactive_roles = interactive_roles or INTERACTIVE_ROLES

    def extract_interactive_bids(self, snapshot: Dict[str, Any]) -> List[AXNode]:
        """Traverse accessibility snapshot, filter out non-interactive noise, and assign 1-based BIDs.

        Args:
            snapshot: Dictionary representing root accessibility snapshot from page.accessibility.snapshot().

        Returns:
            List of AXNode instances representing interactive elements.
        """
        if not snapshot or not isinstance(snapshot, dict):
            return []

        interactive_nodes: List[AXNode] = []
        counter = 1

        def traverse(node: Dict[str, Any]) -> None:
            nonlocal counter
            if not isinstance(node, dict):
                return

            role = str(node.get("role", "")).lower()
            if role in self.interactive_roles:
                raw_name = node.get("name", "")
                name = str(raw_name).strip() if raw_name is not None else ""
                raw_val = node.get("value")
                val = str(raw_val) if raw_val is not None else None

                children = node.get("children", [])
                options: List[str] = []
                if isinstance(children, list):
                    options = [
                        str(c.get("name", "")).strip()
                        for c in children
                        if isinstance(c, dict) and str(c.get("role", "")).lower() == "option" and c.get("name")
                    ]

                interactive_nodes.append(
                    AXNode(
                        bid=counter,
                        role=role,
                        name=name,
                        value=val,
                        children_options=options if options else None,
                    )
                )
                counter += 1

            for child in node.get("children", []):
                if isinstance(child, dict):
                    traverse(child)

        traverse(snapshot)
        return interactive_nodes


def inject_bid_attributes(page: Any) -> int:
    """Execute JavaScript in synchronous Playwright page to tag live DOM elements with data-bid.

    Args:
        page: Playwright Page instance.

    Returns:
        Total number of elements tagged with data-bid attributes.
    """
    if not page or not hasattr(page, "evaluate"):
        return 0

    try:
        res = page.evaluate(INJECT_BID_JS)
        return int(res) if res is not None else 0
    except Exception as e:
        logger.warning("Failed to inject data-bid attributes into DOM: %s", e)
        return 0


async def inject_bid_attributes_async(page: Any) -> int:
    """Execute JavaScript in asynchronous Playwright page to tag live DOM elements with data-bid.

    Args:
        page: Playwright Async Page instance.

    Returns:
        Total number of elements tagged with data-bid attributes.
    """
    if not page or not hasattr(page, "evaluate"):
        return 0

    try:
        res = page.evaluate(INJECT_BID_JS)
        if inspect.isawaitable(res):
            res = await res
        return int(res) if res is not None else 0
    except Exception as e:
        logger.warning("Failed to inject data-bid attributes into async DOM: %s", e)
        return 0
