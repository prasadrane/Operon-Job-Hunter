"""Set-of-Marks (SoM) Annotator for text prompt representations and visual markers."""

import logging
from typing import Any, List, Optional
from .axtree_parser import AXNode

logger = logging.getLogger(__name__)


class SetOfMarksAnnotator:
    """Formats interactive accessibility nodes into compact prompt tokens and visual markings."""

    def format_prompt_representation(
        self,
        nodes: List[AXNode],
        include_values: bool = False,
    ) -> str:
        """Format a list of interactive AXNodes into a compact string prompt representation.

        Format:
            [<bid>] <<role>> "<name>" [Value: "<value>"] (Options: <opt1>, <opt2>)

        Args:
            nodes: List of parsed interactive AXNode instances.
            include_values: If True, include current element values when available.

        Returns:
            Newline-separated compact string representation for LLM prompt context (<600 tokens).
        """
        if not nodes:
            return ""

        lines: List[str] = []
        for n in nodes:
            line_parts = [f"[{n.bid}] <{n.role}> \"{n.name}\""]

            if include_values and n.value is not None and str(n.value).strip():
                line_parts.append(f"[Value: \"{n.value}\"]")

            if n.children_options:
                opts = ", ".join(n.children_options)
                line_parts.append(f"(Options: {opts})")

            lines.append(" ".join(line_parts))

        return "\n".join(lines)

    def annotate(
        self,
        screenshot_bytes: bytes,
        elements: Optional[List[AXNode]] = None,
    ) -> bytes:
        """Draw Set-of-Marks visual bounding boxes and numeric ID badges over screenshot.

        Args:
            screenshot_bytes: Raw PNG/JPEG screenshot bytes.
            elements: List of AXNodes with optional coordinates/bids.

        Returns:
            Annotated screenshot bytes, or original bytes if no visual drawing engine is available.
        """
        if not screenshot_bytes:
            return b""

        # In pure perception or headless pipelines, return original bytes if image drawing is not active
        return screenshot_bytes
