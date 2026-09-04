import importlib


def test_sample_mode_footer(monkeypatch):
    from src.core.config import get_settings
    monkeypatch.setenv("PROFILE_DATA_DIR", "./data/sample")
    get_settings.cache_clear()
    mod = importlib.import_module("src.pipeline.3_tailoring.pdf_renderer")
    sample_mode_footer_text = getattr(mod, "sample_mode_footer_text")
    assert sample_mode_footer_text() == "SAMPLE CANDIDATE — CareerGraph-AI demo"
