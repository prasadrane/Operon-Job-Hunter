from src.core.config import Settings


def test_p5b_defaults_are_conservative():
    s = Settings(_env_file=None)
    assert s.adzuna_app_id == ""
    assert s.adzuna_app_key == ""


def test_p5c_auto_submit_defaults_off():
    assert Settings(_env_file=None).auto_submit_enabled is False

