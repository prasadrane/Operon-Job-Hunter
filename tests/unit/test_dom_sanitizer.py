"""Tests for DOM sanitizer - Red phase (failing tests)."""
import pytest


def test_null_bytes_stripped():
    """NULL bytes (\\x00) stripped from all string fields."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"name": "John\x00Doe", "desc": "hello\x00world"}
    result = sanitize_dom(data)
    assert "\x00" not in result["name"]
    assert "\x00" not in result["desc"]
    assert result["name"] == "JohnDoe"
    assert result["desc"] == "helloworld"


def test_ansi_escape_sequences_removed():
    """ANSI escape sequences (\\x1b[...m) removed."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"text": "\x1b[31mRed text\x1b[0m", "code": "foo\x1b[1mbar\x1b[0mbaz"}
    result = sanitize_dom(data)
    assert "\x1b" not in result["text"]
    assert result["text"] == "Red text"
    assert result["code"] == "foobarbaz"


def test_curly_quotes_replaced():
    """Curly quotes replaced with standard ASCII."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {
        "quote1": "“Hello”",  # curly double quotes
        "quote2": "‘World’",  # curly single quotes
    }
    result = sanitize_dom(data)
    assert result["quote1"] == '"Hello"'
    assert result["quote2"] == "'World'"


def test_field_bounds_first_name_truncated():
    """First Name exceeding 60 chars truncated to max length."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"first_name": "A" * 100}
    result = sanitize_dom(data)
    assert len(result["first_name"]) == 60


def test_field_bounds_custom_qa_truncated():
    """Custom QA exceeding 2000 chars truncated to max length."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"custom_qa": "B" * 3000}
    result = sanitize_dom(data)
    assert len(result["custom_qa"]) == 2000


def test_user_overridden_still_sanitizes_dom():
    """When user_overridden=True, DOM sanitization still enforced."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"text": "\x00\x1b[31m“Hello”\x00"}
    result = sanitize_dom(data, user_overridden=True)
    assert "\x00" not in result["text"]
    assert "\x1b" not in result["text"]
    assert "“" not in result["text"]
    assert "”" not in result["text"]


def test_user_overridden_bypasses_factguard():
    """When user_overridden=True, FactGuard advisory bypassed but DOM still clean."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"first_name": "A" * 100, "text": "\x00dirty"}
    result = sanitize_dom(data, user_overridden=True)
    # DOM sanitization still happens
    assert "\x00" not in result["text"]
    # Field bounds still enforced (sanitization is deterministic, not LLM-based)
    assert len(result["first_name"]) == 60


def test_invalid_utf8_surrogates_no_crash():
    """Invalid UTF-8 surrogates handled gracefully (no crash)."""
    from src.pipeline.sanitizer import sanitize_dom

    # Python strings can contain lone surrogates via surrogateescape
    data = {"text": "hello\ud800world\udc00"}
    result = sanitize_dom(data)
    assert isinstance(result, dict)
    assert "text" in result
    # Should not crash, result should be a valid string
    assert "hello" in result["text"]
    assert "world" in result["text"]


def test_does_not_mutate_input():
    """Must not mutate input dict (return copy)."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"name": "John\x00Doe", "first_name": "A" * 100}
    original_name = data["name"]
    original_first = data["first_name"]
    result = sanitize_dom(data)
    # Input unchanged
    assert data["name"] == original_name
    assert data["first_name"] == original_first
    # Output is different object
    assert result is not data


def test_validate_field_bounds_returns_violations():
    """validate_field_bounds returns list of violation messages."""
    from src.pipeline.sanitizer import validate_field_bounds

    schema = {
        "first_name": {"max_length": 60},
        "custom_qa": {"max_length": 2000},
    }
    data = {
        "first_name": "A" * 100,  # violation
        "custom_qa": "B" * 1500,  # OK
    }
    violations = validate_field_bounds(data, schema)
    assert len(violations) == 1
    assert "first_name" in violations[0]


def test_validate_field_bounds_no_violations():
    """validate_field_bounds returns empty list when no violations."""
    from src.pipeline.sanitizer import validate_field_bounds

    schema = {
        "first_name": {"max_length": 60},
    }
    data = {"first_name": "Short"}
    violations = validate_field_bounds(data, schema)
    assert violations == []


def test_nested_dict_sanitized():
    """Nested dicts also get sanitized."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"outer": {"inner": "hello\x00world"}}
    result = sanitize_dom(data)
    assert "\x00" not in result["outer"]["inner"]


def test_list_values_sanitized():
    """List values containing strings get sanitized."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"items": ["hello\x00world", "foo\x1b[31mbar"]}
    result = sanitize_dom(data)
    assert "\x00" not in result["items"][0]
    assert "\x1b" not in result["items"][1]


def test_non_string_values_untouched():
    """Non-string values (int, bool, None) pass through unchanged."""
    from src.pipeline.sanitizer import sanitize_dom

    data = {"count": 42, "flag": True, "empty": None}
    result = sanitize_dom(data)
    assert result["count"] == 42
    assert result["flag"] is True
    assert result["empty"] is None
