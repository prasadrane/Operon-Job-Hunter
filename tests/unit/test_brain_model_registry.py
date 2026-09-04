import json
from pathlib import Path

from src.brain.model_registry import ModelRegistry


def _write(tmp_path: Path, data) -> Path:
    p = tmp_path / "models.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_legacy_registry_fallback_for_any_mode(tmp_path):
    """models.json without mode fields: any mode resolves to the active entry (P2)."""
    reg = ModelRegistry(_write(tmp_path, {"models": [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True},
    ]}))
    m = reg.get_model_for_mode("tailoring")
    assert m and m["model_name"] == "career-brain-q4"
    assert reg.get_model_for_mode("qa")["model_name"] == "career-brain-q4"


def test_mode_pointer_wins_over_fallback(tmp_path):
    reg = ModelRegistry(_write(tmp_path, {
        "models": [
            {"version": "v1-q4", "model_name": "career-brain-q4", "active": True},
            {"version": "tailor-v1", "model_name": "career-brain-tailor-v1", "mode": "tailoring"},
            {"version": "qa-v1", "model_name": "career-brain-qa-v1", "mode": "qa"},
        ],
        "active_modes": {"tailoring": "tailor-v1", "qa": "qa-v1"},
    }))
    assert reg.get_model_for_mode("tailoring")["model_name"] == "career-brain-tailor-v1"
    assert reg.get_model_for_mode("qa")["model_name"] == "career-brain-qa-v1"
    assert reg.get_model_for_mode("avatar")["model_name"] == "career-brain-q4"  # fallback


def test_set_active_for_mode_roundtrip(tmp_path):
    path = _write(tmp_path, {"models": [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True},
        {"version": "tailor-v1", "model_name": "career-brain-tailor-v1", "mode": "tailoring"},
    ]})
    reg = ModelRegistry(path)
    reg.set_active_for_mode("tailoring", "tailor-v1")
    # rollback = flip back
    assert ModelRegistry(path).get_model_for_mode("tailoring")["version"] == "tailor-v1"
    ModelRegistry(path).set_active_for_mode("tailoring", "v1-q4")
    assert ModelRegistry(path).get_model_for_mode("tailoring")["version"] == "v1-q4"


def test_set_active_unknown_version_raises(tmp_path):
    reg = ModelRegistry(_write(tmp_path, {"models": [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True}]}))
    import pytest
    with pytest.raises(ValueError):
        reg.set_active_for_mode("tailoring", "nope-v9")


def test_get_active_model_unchanged(tmp_path):
    reg = ModelRegistry(_write(tmp_path, {"models": [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True}]}))
    assert reg.get_active_model()["version"] == "v1-q4"


def test_missing_registry_resolves_none(tmp_path):
    reg = ModelRegistry(tmp_path / "absent.json")
    assert reg.get_model_for_mode("qa") is None
