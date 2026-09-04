"""Wizard State Manager: Checkpoint serialization and multi-step resume-on-interruption."""

from dataclasses import asdict, dataclass, field
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class WizardStepState:
    step_index: int
    step_name: str
    fields_filled: Dict[str, Any] = field(default_factory=dict)
    dom_hash: Optional[str] = None
    timestamp: float = field(default_factory=time.time)


class WizardStateManager:
    """Manages persistent session checkpoints for multi-step ATS wizards (e.g. Workday)."""

    def __init__(
        self,
        sessions_dir: str = "./data/wizard_sessions",
        ttl_seconds: int = 86400,
    ) -> None:
        self.sessions_dir = sessions_dir
        self.ttl_seconds = ttl_seconds
        os.makedirs(self.sessions_dir, exist_ok=True)

    def _get_session_path(self, session_id: str) -> str:
        safe_id = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
        return os.path.join(self.sessions_dir, f"{safe_id}.json")

    def save_checkpoint(self, session_id: str, state: WizardStepState) -> None:
        """Append or update step checkpoint in session store."""
        path = self._get_session_path(session_id)
        steps_data: List[Dict[str, Any]] = []

        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    steps_data = json.load(f)
                    if not isinstance(steps_data, list):
                        steps_data = []
            except Exception:
                steps_data = []

        # Filter out existing entries for the same step index
        steps_data = [s for s in steps_data if s.get("step_index") != state.step_index]
        steps_data.append(asdict(state))
        steps_data.sort(key=lambda s: s.get("step_index", 0))

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(steps_data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save wizard checkpoint for session %s: %s", session_id, e)

    def has_active_session(self, session_id: str) -> bool:
        """Check if a valid, unexpired session checkpoint exists."""
        path = self._get_session_path(session_id)
        if not os.path.exists(path):
            return False

        try:
            with open(path, "r", encoding="utf-8") as f:
                steps_data = json.load(f)
                if not steps_data:
                    return False
                latest_ts = max(s.get("timestamp", 0) for s in steps_data)
                if time.time() - latest_ts > self.ttl_seconds:
                    self.clear_session(session_id)
                    return False
                return True
        except Exception:
            return False

    def get_latest_checkpoint(self, session_id: str) -> Optional[WizardStepState]:
        """Retrieve the most advanced completed step state for an active session."""
        if not self.has_active_session(session_id):
            return None

        path = self._get_session_path(session_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                steps_data = json.load(f)
                if not steps_data:
                    return None
                latest_dict = sorted(steps_data, key=lambda s: s.get("step_index", 0))[-1]
                return WizardStepState(
                    step_index=latest_dict["step_index"],
                    step_name=latest_dict["step_name"],
                    fields_filled=latest_dict.get("fields_filled", {}),
                    dom_hash=latest_dict.get("dom_hash"),
                    timestamp=latest_dict.get("timestamp", time.time()),
                )
        except Exception:
            return None

    def get_all_steps(self, session_id: str) -> List[WizardStepState]:
        """Retrieve all completed step states for an active session."""
        if not self.has_active_session(session_id):
            return []

        path = self._get_session_path(session_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                steps_data = json.load(f)
                return [
                    WizardStepState(
                        step_index=s["step_index"],
                        step_name=s["step_name"],
                        fields_filled=s.get("fields_filled", {}),
                        dom_hash=s.get("dom_hash"),
                        timestamp=s.get("timestamp", time.time()),
                    )
                    for s in sorted(steps_data, key=lambda x: x.get("step_index", 0))
                ]
        except Exception:
            return []

    def clear_session(self, session_id: str) -> None:
        """Purge session file upon completion or invalidation."""
        path = self._get_session_path(session_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass
