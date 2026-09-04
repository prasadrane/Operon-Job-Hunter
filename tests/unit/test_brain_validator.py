import pytest
from src.brain.validator import validate_training_pair, ValidationResult


def test_valid_pair():
    pair = {
        "messages": [
            {"role": "system", "content": "You are Alex Rivera."},
            {"role": "user", "content": "Tell me about Kafka."},
            {"role": "assistant", "content": "I established Kafka governance for 5 teams."},
        ],
        "metadata": {"source_chunk_id": "story_7", "mode": "avatar"},
    }
    result = validate_training_pair(pair)
    assert result.is_valid
    assert len(result.errors) == 0


def test_missing_roles():
    pair = {
        "messages": [
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "Answer."},
        ],
        "metadata": {},
    }
    result = validate_training_pair(pair)
    assert not result.is_valid
    assert "missing roles" in result.errors[0].lower() or "missing" in result.errors[0].lower()


def test_empty_content():
    pair = {
        "messages": [
            {"role": "system", "content": ""},
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": ""},
        ],
        "metadata": {},
    }
    result = validate_training_pair(pair)
    assert not result.is_valid


def test_response_too_long():
    pair = {
        "messages": [
            {"role": "system", "content": "System."},
            {"role": "user", "content": "Question?"},
            {"role": "assistant", "content": "x " * 900},  # 900 words > MAX_RESPONSE_WORDS (800)
        ],
        "metadata": {},
    }
    result = validate_training_pair(pair)
    assert not result.is_valid
    assert "too long" in result.errors[0].lower()
