# tests/unit/test_brain_cache_telemetry.py
import json
from collections import OrderedDict

from src.brain.inference import BrainInference, make_cache_key
from src.brain.telemetry import append_telemetry


def test_cache_key_stable_and_hashed():
    k1 = make_cache_key("tailoring", "long jd " * 200, "skills", "query")
    k2 = make_cache_key("tailoring", "long jd " * 200, "skills", "query")
    assert k1 == k2 and "long jd" not in k1
    assert make_cache_key("tailoring", "long jd " * 200, "experience@x", "query") != k1


def test_lru_evicts_oldest(monkeypatch):
    monkeypatch.setenv("BRAIN_CACHE_MAX_SIZE", "2")
    from src.brain.config import get_brain_settings
    get_brain_settings.cache_clear()
    b = BrainInference.__new__(BrainInference)  # bypass __init__ IO
    from src.brain.config import get_brain_settings as gs
    b.settings = gs()
    b._cache = OrderedDict()
    from src.brain.response_formatter import BrainResponse
    for i in range(3):
        key = f"k{i}"
        b._cache_put(key, BrainResponse(answer=str(i), mode="qa", confidence=1.0))
    assert "k0" not in b._cache and "k2" in b._cache and len(b._cache) == 2


def test_telemetry_appends_jsonl(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_TELEMETRY_DIR", str(tmp_path))
    from src.brain.config import get_brain_settings
    get_brain_settings.cache_clear()
    append_telemetry({"mode": "qa", "cache_hit": False})
    lines = (tmp_path / "brain_calls.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert json.loads(lines[-1])["mode"] == "qa"
