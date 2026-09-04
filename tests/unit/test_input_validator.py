"""Unit tests for InputValidator."""

import pytest
from src.core.security.input_validator import InputValidator


# ---------------------------------------------------------------------------
# validate_job_id
# ---------------------------------------------------------------------------


class TestValidateJobId:
    def test_accepts_alphanumeric(self):
        assert InputValidator.validate_job_id("job_abc123") is True

    def test_accepts_hyphens(self):
        assert InputValidator.validate_job_id("job-abc-123") is True

    def test_rejects_empty(self):
        assert InputValidator.validate_job_id("") is False

    def test_rejects_none(self):
        assert InputValidator.validate_job_id(None) is False

    def test_rejects_over_length(self):
        assert InputValidator.validate_job_id("a" * 65) is False

    def test_rejects_sql_injection(self):
        assert InputValidator.validate_job_id("job' OR 1=1--") is False

    def test_rejects_xss(self):
        assert InputValidator.validate_job_id("<script>alert(1)</script>") is False

    def test_rejects_path_traversal(self):
        assert InputValidator.validate_job_id("../../etc/passwd") is False

    def test_rejects_spaces(self):
        assert InputValidator.validate_job_id("job abc") is False

    def test_rejects_special_chars(self):
        assert InputValidator.validate_job_id("job@abc!") is False


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------


class TestValidateUrl:
    def test_accepts_https(self):
        assert InputValidator.validate_url("https://example.com/jobs/123") is True

    def test_accepts_http(self):
        assert InputValidator.validate_url("http://example.com") is True

    def test_rejects_empty(self):
        assert InputValidator.validate_url("") is False

    def test_rejects_none(self):
        assert InputValidator.validate_url(None) is False

    def test_rejects_javascript_scheme(self):
        assert InputValidator.validate_url("javascript:alert(1)") is False

    def test_rejects_file_scheme(self):
        assert InputValidator.validate_url("file:///etc/passwd") is False

    def test_rejects_data_scheme(self):
        assert InputValidator.validate_url("data:text/html,<script>alert(1)</script>") is False

    def test_rejects_path_traversal(self):
        assert InputValidator.validate_url("https://example.com/../../etc/passwd") is False

    def test_rejects_xss_in_url(self):
        assert InputValidator.validate_url("https://example.com/<script>alert(1)</script>") is False

    def test_rejects_over_length(self):
        assert InputValidator.validate_url("https://x.com/" + "a" * 2100) is False

    def test_rejects_no_netloc(self):
        assert InputValidator.validate_url("https://") is False


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------


class TestValidateEmail:
    def test_accepts_valid(self):
        assert InputValidator.validate_email("user@example.com") is True

    def test_accepts_plus_tag(self):
        assert InputValidator.validate_email("user+tag@example.com") is True

    def test_rejects_empty(self):
        assert InputValidator.validate_email("") is False

    def test_rejects_none(self):
        assert InputValidator.validate_email(None) is False

    def test_rejects_no_at(self):
        assert InputValidator.validate_email("userexample.com") is False

    def test_rejects_no_domain(self):
        assert InputValidator.validate_email("user@") is False

    def test_rejects_over_length(self):
        assert InputValidator.validate_email("a" * 250 + "@x.com") is False


# ---------------------------------------------------------------------------
# sanitize_string
# ---------------------------------------------------------------------------


class TestSanitizeString:
    def test_passes_clean_string(self):
        assert InputValidator.sanitize_string("hello world") == "hello world"

    def test_strips_control_chars(self):
        assert "\x00" not in InputValidator.sanitize_string("hello\x00world")

    def test_escapes_html(self):
        result = InputValidator.sanitize_string("a < b & c > d")
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_raises_on_sql_injection(self):
        with pytest.raises(ValueError, match="SQL"):
            InputValidator.sanitize_string("'; DROP TABLE users; --")

    def test_raises_on_xss(self):
        with pytest.raises(ValueError, match="HTML"):
            InputValidator.sanitize_string("<script>alert('xss')</script>")

    def test_raises_on_path_traversal(self):
        with pytest.raises(ValueError, match="path traversal"):
            InputValidator.sanitize_string("../../etc/passwd")

    def test_truncates_oversized_input(self):
        result = InputValidator.sanitize_string("a" * 20_000)
        assert len(result) <= 10_000

    def test_strips_whitespace(self):
        assert InputValidator.sanitize_string("  hello  ") == "hello"

    def test_non_string_returns_empty(self):
        assert InputValidator.sanitize_string(None) == ""  # type: ignore[arg-type]

    def test_sanitize_optional_none(self):
        assert InputValidator.sanitize_optional(None) is None

    def test_sanitize_optional_empty(self):
        assert InputValidator.sanitize_optional("") is None

    def test_sanitize_optional_value(self):
        assert InputValidator.sanitize_optional("hello") == "hello"
