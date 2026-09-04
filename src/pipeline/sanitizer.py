"""DOM sanitizer for pipeline data.

Strips control characters, normalizes typography, enforces field bounds.
Deterministic, no LLM calls. Does not mutate input.
"""
import copy
import re
from typing import Any

# Default field bounds
DEFAULT_BOUNDS = {
    "first_name": 60,
    "custom_qa": 2000,
}

# Regex patterns for sanitization
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_NULL_BYTE_RE = re.compile(r"\x00")

# Typography replacements
_TYPO_MAP = {
    "“": '"',  # left double curly quote
    "”": '"',  # right double curly quote
    "‘": "'",  # left single curly quote
    "’": "'",  # right single curly quote
    "—": "-",  # em-dash
    "–": "-",  # en-dash
    "​": "",   # zero-width space
    "‌": "",   # zero-width non-joiner
    "‍": "",   # zero-width joiner
    "﻿": "",   # BOM / zero-width no-break space
}


def _sanitize_string(value: str) -> str:
    """Sanitize a single string value."""
    # Handle lone surrogates gracefully by encoding with surrogateescape
    try:
        # Try encoding to catch surrogates
        value.encode("utf-8", errors="surrogateescape")
        # Remove lone surrogates by replacing them
        value = value.encode("utf-8", errors="surrogateescape").decode(
            "utf-8", errors="replace"
        )
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: replace problematic chars
        value = value.encode("ascii", errors="replace").decode("ascii")

    # Strip NULL bytes
    value = _NULL_BYTE_RE.sub("", value)

    # Strip ANSI escape sequences
    value = _ANSI_ESCAPE_RE.sub("", value)

    # Normalize typography
    for char, replacement in _TYPO_MAP.items():
        value = value.replace(char, replacement)

    return value


def _sanitize_value(value: Any) -> Any:
    """Recursively sanitize a value."""
    if isinstance(value, str):
        return _sanitize_string(value)
    elif isinstance(value, dict):
        return {k: _sanitize_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    else:
        return value


def _apply_field_bounds(data: dict) -> dict:
    """Apply field bounds to the data dict (top-level fields only)."""
    result = dict(data)
    for field, max_len in DEFAULT_BOUNDS.items():
        if field in result and isinstance(result[field], str):
            if len(result[field]) > max_len:
                result[field] = result[field][:max_len]
    return result


def sanitize_dom(data: dict, user_overridden: bool = False) -> dict:
    """Sanitize DOM data.

    Strips control chars, normalizes typography, enforces field bounds.
    Does not mutate input. Returns sanitized copy.

    Args:
        data: Input dict to sanitize
        user_overridden: If True, FactGuard advisory bypassed but DOM
                        sanitization still enforced
    """
    # Deep copy to avoid mutating input
    sanitized = copy.deepcopy(data)

    # Recursively sanitize all values
    sanitized = _sanitize_value(sanitized)

    # Apply field bounds
    if isinstance(sanitized, dict):
        sanitized = _apply_field_bounds(sanitized)

    return sanitized


def validate_field_bounds(data: dict, schema: dict) -> list[str]:
    """Validate field bounds against schema.

    Returns list of violation messages (empty if no violations).

    Args:
        data: Data dict to validate
        schema: Schema dict with field names as keys and bounds config as values.
                Each bound config has 'max_length' key.
    """
    violations = []
    for field, config in schema.items():
        if field in data:
            max_length = config.get("max_length")
            if max_length is not None and isinstance(data[field], str):
                if len(data[field]) > max_length:
                    violations.append(
                        f"Field '{field}' exceeds max length: "
                        f"{len(data[field])} > {max_length}"
                    )
    return violations
