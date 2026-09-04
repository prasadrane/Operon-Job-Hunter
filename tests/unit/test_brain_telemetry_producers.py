# tests/unit/test_brain_telemetry_producers.py
import json
from unittest.mock import MagicMock


def _client_with(meta):
    from src.brain.ollama_client import OllamaClient
    c = OllamaClient.__new__(OllamaClient)
    c.base_url, c.model, c.timeout = "http://x", "m", 5
    c.session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"response": "ok", **meta}
    c.session.post.return_value = resp
    return c


def test_generate_captures_last_meta():
    c = _client_with({"prompt_eval_count": 1200, "eval_count": 300})
    assert c.generate("p", mode="tailoring") == "ok"
    assert c.last_meta == {"prompt_eval_count": 1200, "eval_count": 300}


def test_last_meta_reset_between_calls():
    c = _client_with({})
    c.generate("p", mode="qa")
    assert c.last_meta == {}
