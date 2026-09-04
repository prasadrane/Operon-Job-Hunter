"""Per-call telemetry JSONL appender (spec §5.8, P7)."""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from src.brain.config import get_brain_settings


def append_telemetry(record: Dict[str, Any]) -> None:
    settings = get_brain_settings()
    path = settings.BRAIN_TELEMETRY_DIR / "brain_calls.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", time.time())
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
