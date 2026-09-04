"""Input validation and sanitization utilities.

Prevents common injection attacks:
- SQL injection patterns
- XSS payloads (script tags, event handlers, javascript: URIs)
- Path traversal sequences (../, ..\)
- Control characters and null bytes
"""

import html
import re
from typing import Optional
from urllib.parse import urlparse


# Dangerous patterns to reject outright.
_SQL_INJECTION_PATTERNS = re.compile(
    r"(--|;|\/\*|\*\/|@@|@@@|"
    r"\b(select|union|insert|update|delete|drop|alter|create|truncate|exec|execute)\b|"
    r"\b(or|and)\b\s+\d+\s*=\s*\d+|"
    r"'\s*(or|and)\s+')",
    re.IGNORECASE,
)

_XSS_PATTERNS = re.compile(
    r"(<\s*script|<\s*/\s*script|javascript\s*:|on\w+\s*=|<\s*img[^>]+onerror|"
    r"<\s*iframe|<\s*object|<\s*embed|<\s*svg[^>]+onload)",
    re.IGNORECASE,
)

_PATH_TRAVERSAL_PATTERNS = re.compile(r"(\.\.[/\\]|%2e%2e[/\\%])", re.IGNORECASE)

_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Acceptable job id: alphanumeric, underscore, hyphen — max 64 chars.
_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")

# Permissive URL scheme check.
_SAFE_URL_SCHEMES = {"http", "https"}

# Email regex — not RFC-5322-complete, but good enough for input gating.
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# Max lengths to prevent memory/DoS attacks.
_MAX_STRING_LENGTH = 10_000
_MAX_URL_LENGTH = 2_048
_MAX_JOB_ID_LENGTH = 64
_MAX_EMAIL_LENGTH = 254


class InputValidator:
    """Static helper methods for input validation and sanitization."""

    # ------------------------------------------------------------------
    # Validators — return bool; raise on invalid.
    # ------------------------------------------------------------------

    @staticmethod
    def validate_job_id(job_id: str) -> bool:
        """Reject empty, over-long, or pattern-violating job IDs."""
        if not job_id or not isinstance(job_id, str):
            return False
        if len(job_id) > _MAX_JOB_ID_LENGTH:
            return False
        return bool(_JOB_ID_PATTERN.match(job_id))

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate that a URL is well-formed and uses a safe scheme."""
        if not url or not isinstance(url, str):
            return False
        if len(url) > _MAX_URL_LENGTH:
            return False
        if _PATH_TRAVERSAL_PATTERNS.search(url):
            return False
        if _XSS_PATTERNS.search(url):
            return False

        try:
            parsed = urlparse(url)
        except Exception:
            return False

        if parsed.scheme not in _SAFE_URL_SCHEMES:
            return False
        if not parsed.netloc:
            return False
        return True

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email format and length."""
        if not email or not isinstance(email, str):
            return False
        if len(email) > _MAX_EMAIL_LENGTH:
            return False
        return bool(_EMAIL_PATTERN.match(email))

    # ------------------------------------------------------------------
    # Sanitizers — return cleaned string.
    # ------------------------------------------------------------------

    @staticmethod
    def sanitize_string(text: str) -> str:
        """Strip control chars, HTML-escape, and trim dangerous patterns.

        Returns the sanitised string. Raises ValueError when the input
        contains SQL-injection or XSS markers.
        """
        if not isinstance(text, str):
            return ""

        if len(text) > _MAX_STRING_LENGTH:
            text = text[:_MAX_STRING_LENGTH]

        # Reject dangerous payloads outright.
        if _SQL_INJECTION_PATTERNS.search(text):
            raise ValueError("Input contains disallowed SQL patterns")
        if _XSS_PATTERNS.search(text):
            raise ValueError("Input contains disallowed HTML/JS patterns")
        if _PATH_TRAVERSAL_PATTERNS.search(text):
            raise ValueError("Input contains disallowed path traversal sequences")

        # Strip control characters.
        text = _CONTROL_CHAR_PATTERN.sub("", text)
        # HTML-escape remaining angle brackets and ampersands.
        text = html.escape(text, quote=True)
        return text.strip()

    @staticmethod
    def sanitize_optional(text: Optional[str]) -> Optional[str]:
        """Sanitize a nullable string field, returning None for empty input."""
        if text is None:
            return None
        cleaned = InputValidator.sanitize_string(text)
        return cleaned or None
