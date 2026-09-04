# tests/unit/test_brain_ollama_client.py
import pytest
from unittest.mock import patch, MagicMock
from src.brain.ollama_client import OllamaClient


@pytest.fixture
def client():
    return OllamaClient(base_url="http://localhost:11434", model="career-brain")


def test_generate_success(client):
    mock_response = MagicMock()
    mock_response.json.return_value = {"response": "I led Kafka governance for 5 teams."}
    mock_response.raise_for_status = MagicMock()

    with patch.object(client.session, "post", return_value=mock_response) as mock_post:
        result = client.generate("Tell me about Kafka")
        assert result == "I led Kafka governance for 5 teams."
        mock_post.assert_called_once()


def test_generate_timeout(client):
    with patch.object(client.session, "post", side_effect=Exception("timeout")):
        with pytest.raises(Exception):
            client.generate("Tell me about Kafka", timeout=1)


def test_health_check_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch.object(client.session, "get", return_value=mock_response):
        assert client.health_check() is True


def test_health_check_failure(client):
    with patch.object(client.session, "get", side_effect=Exception("connection refused")):
        assert client.health_check() is False


def test_is_available(client):
    with patch.object(client, "health_check", return_value=True):
        assert client.is_available() is True


class _FakeResponse:
    def __init__(self, payload=None, lines=None):
        self._payload = payload or {"response": "ok"}
        self._lines = lines or []
        self.status_code = 200
        self.sent_json = None

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload

    def iter_lines(self):
        return iter(self._lines)


def _client_with_fake_session(monkeypatch, tmp_path, registry_models):
    import json as _json
    from src.brain.model_registry import ModelRegistry
    from src.brain.ollama_client import OllamaClient

    reg_path = tmp_path / "models.json"
    reg_path.write_text(_json.dumps({"models": registry_models}), encoding="utf-8")
    monkeypatch.setattr("src.brain.ollama_client.get_model_registry",
                        lambda: ModelRegistry(reg_path))
    c = OllamaClient()
    fake = _FakeResponse()
    monkeypatch.setattr(c.session, "post",
                        lambda url, json=None, timeout=None, stream=False:
                        (setattr(fake, "sent_json", json), fake)[1])
    return c, fake


def test_mode_profiles_match_spec(monkeypatch, tmp_path):
    c, _ = _client_with_fake_session(monkeypatch, tmp_path, [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True}])
    from src.brain.ollama_client import MODE_PROFILES
    assert MODE_PROFILES["tailor-resume"]["num_ctx"] == 4096
    assert MODE_PROFILES["tailor-resume"]["num_predict"] == 900
    assert MODE_PROFILES["tailor-resume"]["temperature"] == 0.3
    assert MODE_PROFILES["tailor-letter"]["temperature"] == 0.6
    assert MODE_PROFILES["qa-avatar"]["num_ctx"] == 2048
    assert MODE_PROFILES["qa-avatar"]["num_predict"] == 512
    opts = c._build_options(mode="tailoring")
    assert opts["num_ctx"] == 4096  # silent-truncation fix (num_ctx was 1536)


def test_generate_resolves_model_per_call_from_registry(monkeypatch, tmp_path):
    c, fake = _client_with_fake_session(monkeypatch, tmp_path, [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True},
        {"version": "tailor-v1", "model_name": "career-brain-tailor-v1",
         "mode": "tailoring", "active": True},
    ])
    from src.brain.model_registry import ModelRegistry
    c.registry = ModelRegistry(tmp_path / "models.json")
    c.generate("p", mode="tailoring")
    assert fake.sent_json["model"] == "career-brain-tailor-v1"
    c.generate("p", mode="tailoring", model="override-me")
    assert fake.sent_json["model"] == "override-me"


def test_generate_passes_format_schema(monkeypatch, tmp_path):
    c, fake = _client_with_fake_session(monkeypatch, tmp_path, [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True}])
    c.generate("p", mode="tailoring", format={"type": "object"})
    assert fake.sent_json["format"] == {"type": "object"}
    c.generate("p", mode="qa")
    assert "format" not in fake.sent_json


def test_generate_stream_true_returns_iterator(monkeypatch, tmp_path):
    import json as _json
    c, fake = _client_with_fake_session(monkeypatch, tmp_path, [
        {"version": "v1-q4", "model_name": "career-brain-q4", "active": True}])
    fake._lines = [_json.dumps({"response": "He"}).encode(),
                   _json.dumps({"response": "llo"}).encode()]
    out = c.generate("p", mode="qa", stream=True)
    assert list(out) == ["He", "llo"]
