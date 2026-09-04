"""Build prompts for each brain mode using Jinja2 templates."""
from __future__ import annotations

import json as _json
from pathlib import Path
from typing import List, Optional

from jinja2 import Environment, FileSystemLoader

from src.brain.mode_router import BrainMode
from src.brain.retriever import RetrievedChunk
from src.brain.tailor_schema import tailor_json_schema

PROMPTS_DIR = Path(__file__).parent / "prompts"
_jinja_env = Environment(
    loader=FileSystemLoader(str(PROMPTS_DIR)),
    autoescape=False,
    keep_trailing_newline=True,
)

# Cache templates on first access
_TEMPLATE_CACHE: dict[str, object] = {}


def _get_template(name: str):
    if name not in _TEMPLATE_CACHE:
        _TEMPLATE_CACHE[name] = _jinja_env.get_template(name)
    return _TEMPLATE_CACHE[name]


def build_prompt(
    query: str,
    mode: BrainMode,
    chunks: List[RetrievedChunk],
    job_desc: Optional[str] = None,
    section: Optional[str] = None,
    facet: Optional[str] = None,
) -> str:
    """Build the full prompt for the given mode.

    Prefix-cache order (spec §5.4): static instruction -> schema block -> JD ->
    chunks -> section+query. Single template source for synth and serving (P8);
    ``prompts/tailoring.j2`` stays untouched until the flip (O3).

    Args:
        query: The user's natural-language question or request.
        mode: Brain mode determining which template is used.
        chunks: Retrieved context chunks from BrainRetriever.
        job_desc: Optional job description (used by tailoring mode).
        section: Optional resume section token (tailoring mode).
        facet: "letter" selects the cover-letter template for tailoring.

    Returns:
        Rendered prompt string ready for LLM inference.
    """
    if mode == BrainMode.AVATAR:
        template = _get_template("avatar.j2")
    elif mode == BrainMode.TAILORING:
        template = _get_template("cover_letter.j2" if facet == "letter" else "tailor_resume.j2")
    else:
        template = _get_template("qa.j2")

    kwargs = {"query": query, "chunks": chunks, "job_desc": job_desc or ""}
    if mode == BrainMode.TAILORING and facet != "letter":
        kwargs["schema_block"] = _json.dumps(tailor_json_schema(), indent=1)
        kwargs["section"] = section or "skills"
    return template.render(**kwargs)
