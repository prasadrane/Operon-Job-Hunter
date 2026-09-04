"""WebSurfer Micro-Agent with strict rolling memory buffer (<= 5 turns) and pluggable decision engine."""

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class WebSurferAgent:
    """Micro-agent managing reactive browser perception, rolling memory buffer, and action decisions."""

    def __init__(
        self,
        max_buffer_turns: int = 5,
        decision_engine: Optional[Callable[[str, Dict[str, Any], List[Dict[str, Any]]], Dict[str, Any]]] = None,
    ) -> None:
        """Initialize WebSurferAgent with rolling memory buffer cap and decision engine.

        Args:
            max_buffer_turns: Maximum number of recent interaction turns to retain in memory (default <= 5).
            decision_engine: Optional pluggable callback for deciding structured actions from prompt & profile.
        """
        self.max_buffer_turns = max(1, max_buffer_turns)
        self.history_buffer: List[Dict[str, Any]] = []
        self.completed_bids: Set[int] = set()
        self.decision_engine = decision_engine

    def record_turn_action(
        self,
        turn_idx: int,
        action: Dict[str, Any],
        observation: Optional[Any] = None,
    ) -> None:
        """Record an executed action turn into the rolling memory buffer with FIFO eviction.

        Args:
            turn_idx: Sequential integer index of the turn.
            action: Structured action payload executed.
            observation: Optional observation or outcome description.
        """
        entry: Dict[str, Any] = {
            "turn_idx": turn_idx,
            **action,
        }
        if observation is not None:
            entry["observation"] = observation

        bid = action.get("bid")
        if bid is not None:
            try:
                self.completed_bids.add(int(bid))
            except (ValueError, TypeError):
                pass

        self.history_buffer.append(entry)

        while len(self.history_buffer) > self.max_buffer_turns:
            self.history_buffer.pop(0)

    def clear_history(self) -> None:
        """Clear all entries in the rolling memory buffer and reset completed BIDs."""
        self.history_buffer.clear()
        self.completed_bids.clear()

    def decide_action(
        self,
        available_nodes_prompt: str,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Decide the next structured action based on AXTree prompt representation and profile.

        Args:
            available_nodes_prompt: String representation of interactive AXNodes from SoM annotator.
            profile: Candidate profile dictionary containing field values.

        Returns:
            Structured action dictionary (e.g., type, click, select_option, upload_file, stop).
        """
        profile = profile or {}

        if self.decision_engine is not None:
            return self.decision_engine(available_nodes_prompt, profile, self.history_buffer)

        return self._default_rule_decide(available_nodes_prompt, profile)

    def decide_next_action(
        self,
        prompt_view: str,
        profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Alias for decide_action."""
        return self.decide_action(prompt_view, profile)

    def _default_rule_decide(
        self,
        prompt: str,
        profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Rule-guided heuristic decision engine matching prompt nodes against candidate profile."""
        if not prompt or not isinstance(prompt, str):
            return {"command": "stop", "reason": "EMPTY_PROMPT"}

        # Node regex: [<bid>] <<role>> "<name>"(Options: <opts>)
        pattern = re.compile(r'\[(\d+)\]\s*<([^>]+)>\s*"([^"]+)"(?:\s*\(Options:\s*([^)]+)\))?', re.IGNORECASE)
        lines = prompt.strip().split("\n")

        button_actions: List[Dict[str, Any]] = []

        for line in lines:
            match = pattern.search(line)
            if not match:
                continue

            bid_str, role, name, options_str = match.groups()
            bid = int(bid_str)
            if bid in self.completed_bids:
                continue

            role = role.lower().strip()
            name_lower = name.lower().strip()

            # 1. Textbox inputs
            if role in ("textbox", "searchbox"):
                if "first" in name_lower and "name" in name_lower:
                    val = profile.get("first_name", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "last" in name_lower and "name" in name_lower:
                    val = profile.get("last_name", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "full name" in name_lower or (name_lower == "name" and "first" not in name_lower and "last" not in name_lower):
                    val = profile.get("full_name") or f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "email" in name_lower:
                    val = profile.get("email", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "phone" in name_lower or "mobile" in name_lower:
                    val = profile.get("phone", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "linkedin" in name_lower:
                    val = profile.get("linkedin", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "github" in name_lower:
                    val = profile.get("github", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "website" in name_lower or "portfolio" in name_lower:
                    val = profile.get("website", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}
                elif "city" in name_lower or "location" in name_lower or "address" in name_lower:
                    val = profile.get("city") or profile.get("location") or profile.get("address", "")
                    if val:
                        return {"command": "type", "bid": bid, "text": val}

            # 2. Combobox / Dropdown selection
            elif role in ("combobox", "listbox", "select"):
                if "country" in name_lower:
                    val = profile.get("country", "")
                    if val:
                        return {"command": "select_option", "bid": bid, "value": val}
                elif "state" in name_lower:
                    val = profile.get("state", "")
                    if val:
                        return {"command": "select_option", "bid": bid, "value": val}
                elif options_str:
                    # Check if any profile key matches an option
                    options = [o.strip() for o in options_str.split(",")]
                    for opt in options:
                        if opt.lower() in [str(v).lower() for v in profile.values() if isinstance(v, (str, int))]:
                            return {"command": "select_option", "bid": bid, "value": opt}

            # 3. File upload
            elif role in ("file_upload", "upload"):
                if "resume" in name_lower or "cv" in name_lower:
                    resume_path = profile.get("resume_path") or profile.get("resume_pdf_path", "")
                    if resume_path:
                        return {"command": "upload_file", "bid": bid, "file_path": resume_path}
                elif "cover" in name_lower:
                    cover_path = profile.get("cover_letter_path", "")
                    if cover_path:
                        return {"command": "upload_file", "bid": bid, "file_path": cover_path}

            # 4. Action Buttons (Submit, Save and Continue, Next, etc.)
            elif role in ("button", "link"):
                if any(kw in name_lower for kw in ("save and continue", "continue", "next step", "next", "submit", "apply")):
                    button_actions.append({"command": "click", "bid": bid})

        # If an uncompleted action button was found and all inputs are processed, click button
        if button_actions:
            return button_actions[0]

        # Check for standalone button lines without strict regex match
        for line in lines:
            if "<button>" in line and any(kw in line.lower() for kw in ("save and continue", "continue", "next", "submit", "apply")):
                bid_match = re.search(r'\[(\d+)\]', line)
                if bid_match:
                    btn_bid = int(bid_match.group(1))
                    if btn_bid not in self.completed_bids:
                        return {"command": "click", "bid": btn_bid}

        return {"command": "stop", "reason": "READY_FOR_HITL"}
