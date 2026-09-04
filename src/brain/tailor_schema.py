"""Pydantic schema for sectioned tailor-brain plans (spec §3.3)."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field


class Bullet(BaseModel):
    text: str
    source: str
    bold: List[str] = Field(default_factory=list)


class Story(BaseModel):
    id: str
    why: str = ""
    emphasize: List[str] = Field(default_factory=list)


class TailorPlan(BaseModel):
    section: str = ""
    skills_to_emphasize: List[str] = Field(default_factory=list)
    stories: List[Story] = Field(default_factory=list)
    bullets: List[Bullet] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)


def tailor_json_schema() -> Dict[str, Any]:
    """JSON schema for Ollama structured output (`format` field, spec §5.3).

    Nested pydantic models emit $defs/$ref, which Ollama's schema-to-grammar
    converter may not resolve — inline them so the schema is flat (M1).
    """
    schema = TailorPlan.model_json_schema()
    defs = schema.pop("$defs", {})

    def _resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return _resolve(dict(defs[node["$ref"].rsplit("/", 1)[-1]]))
            return {k: _resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [_resolve(v) for v in node]
        return node

    return _resolve(schema)


def _strip_fences(raw: str) -> str:
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    return m.group(1) if m else raw


def parse_tailor_plan(raw: str, repair: Optional[Callable[[str], str]] = None) -> Optional[TailorPlan]:
    """Parse raw model output into TailorPlan; one optional repair turn (spec §5.3)."""
    def attempt(text: str) -> Optional[TailorPlan]:
        try:
            return TailorPlan.model_validate(json.loads(_strip_fences(text).strip()))
        except (json.JSONDecodeError, ValueError):
            first, last = text.find("{"), text.rfind("}")
            if first != -1 and last > first:
                try:
                    return TailorPlan.model_validate(json.loads(text[first:last + 1]))
                except (json.JSONDecodeError, ValueError):
                    return None
            return None

    plan = attempt(raw)
    if plan is None and repair is not None:
        plan = attempt(repair(raw))
    return plan
