import importlib
from pathlib import Path

from src.core.config import get_settings


def test_validator_jsonl_follows_profile_dir(monkeypatch, tmp_path):
    (tmp_path / "MASTER_RESUME.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setenv("PROFILE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        from src.brain import validator
        importlib.reload(validator)
        assert Path(validator.master_resume_jsonl_path()) == tmp_path / "MASTER_RESUME.jsonl"
    finally:
        get_settings.cache_clear()


def test_companies_yaml_follows_profile_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("PROFILE_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.companies_yaml_path == tmp_path / "companies.yaml"
    finally:
        get_settings.cache_clear()
