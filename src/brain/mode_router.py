"""Route queries to avatar, tailoring, or QA mode."""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class BrainMode(str, Enum):
    """Interaction modes for the Career Brain."""
    AVATAR = "avatar"
    TAILORING = "tailoring"
    QA = "qa"


# Keyword patterns for each mode
AVATAR_PATTERNS = [
    r"tell me about (your|a time|when you)",
    r"your experience",
    r"describe (a time|when|how you)",
    r"walk me through",
    r"what was your (role|approach|biggest)",
    r"how did you (handle|approach|solve|lead)",
    r"give me an example of",
    r"tell me about yourself",
    r"about you\b",
    r"your skills",
]

TAILORING_PATTERNS = [
    r"tailor",
    r"customi[sz]e",
    r"adapt (my|this|the) (resume|story|bullet)",
    r"rewrite for",
    r"match (this|the) (job|role|position)",
    r"for this (job|role|position|opening)",
    r"optimize (my|the|this) (resume|cv|cover)",
]

QA_PATTERNS = [
    r"^(what|which|how many|how much|when|where|who|is|are|do|does|can|could)\b",
    r"what (metrics|results|technologies|skills|certifications)",
    r"list (your|the|all)",
    r"how (long|many|much)",
]


def route_mode(
    query: str,
    mode: str = "auto",
    job_desc: Optional[str] = None,
) -> BrainMode:
    """Route a query to the appropriate brain mode.

    Args:
        query: The user's input text.
        mode: Explicit mode override ("auto", "avatar", "tailoring", "qa").
        job_desc: Optional job description — presence triggers tailoring.

    Returns:
        BrainMode enum value.
    """
    # Explicit mode override
    if mode != "auto":
        try:
            return BrainMode(mode)
        except ValueError:
            pass

    query_lower = query.lower().strip()

    # Job description present → tailoring
    if job_desc and len(job_desc.strip()) > 20:
        return BrainMode.TAILORING

    # Check tailoring patterns first (most specific)
    for pattern in TAILORING_PATTERNS:
        if re.search(pattern, query_lower):
            return BrainMode.TAILORING

    # Check avatar patterns
    for pattern in AVATAR_PATTERNS:
        if re.search(pattern, query_lower):
            return BrainMode.AVATAR

    # Check QA patterns
    for pattern in QA_PATTERNS:
        if re.search(pattern, query_lower):
            return BrainMode.QA

    # Default fallback: QA
    return BrainMode.QA
