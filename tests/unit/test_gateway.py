"""Unit tests for the multi-provider LLM gateway and failover chain."""

import io
import json
import urllib.error
import pytest
from unittest.mock import MagicMock, patch

from src.core.gateway.base import BaseLLMProvider, is_rate_limit_error, is_fatal_http_error
from src.core.gateway.gemini import GeminiProvider
from src.core.gateway.openrouter import OpenRouterProvider
from src.core.gateway.alibaba import AlibabaProvider
from src.core.gateway.facade import LLMGateway, get_gateway
from src.core.config import Settings


# ── 1. Base Provider & Helpers Tests ─────────────────────────────────────────

def test_base_provider_subclass():
    class DummyProvider(BaseLLMProvider):
        def generate(self, prompt: str, json_mode: bool = False, temperature: float = 0.2, system_prompt = None, model = None) -> str:
            return f"Echo: {prompt}"

    p = DummyProvider(api_key="test-key", model="dummy-model")
    assert p.is_available() is True
    assert p.generate("hello") == "Echo: hello"

    p_empty = DummyProvider(api_key=None)
    assert p_empty.is_available() is False


def test_is_rate_limit_error_detection():
    assert is_rate_limit_error(Exception("429 Too Many Requests")) is True
    assert is_rate_limit_error(Exception("Resource has been exhausted (e.g. check quota)")) is True
    assert is_rate_limit_error(Exception("rate limit exceeded")) is True
    assert is_rate_limit_error("error code: 429") is True
    assert is_rate_limit_error(Exception("Internal Server Error 500")) is False


def test_is_fatal_http_error_detection():
    assert is_fatal_http_error(Exception("HTTP Error 400: Bad Request")) is True
    assert is_fatal_http_error(Exception("HTTP Error 401: Unauthorized")) is True
    assert is_fatal_http_error(Exception("HTTP Error 404: Not Found")) is True
    assert is_fatal_http_error(Exception("HTTP Error 500: Server Error")) is False


def test_base_provider_post_json_success():
    class DummyProvider(BaseLLMProvider):
        def generate(self, prompt: str, json_mode: bool = False, temperature: float = 0.2, system_prompt = None, model = None) -> str:
            return ""

    provider = DummyProvider(api_key="key")
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"status": "ok"}).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = provider._post_json("https://api.example.com", {"data": 123}, {"Header": "val"})
        assert res == {"status": "ok"}


def test_base_provider_post_json_http_error():
    class DummyProvider(BaseLLMProvider):
        def generate(self, prompt: str, json_mode: bool = False, temperature: float = 0.2, system_prompt = None, model = None) -> str:
            return ""

    provider = DummyProvider(api_key="key")
    fp = io.BytesIO(b'{"error": "bad request"}')
    http_error = urllib.error.HTTPError("https://api.example.com", 400, "Bad Request", {}, fp)

    with patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(RuntimeError, match="HTTP error 400"):
            provider._post_json("https://api.example.com", {}, {})


# ── 2. Gemini Provider Tests ────────────────────────────────────────────────

def test_gemini_provider_generate_success():
    provider = GeminiProvider(api_key="fake-gemini-key", model="gemini-2.5-flash")
    assert provider.is_available() is True

    fake_response = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": "Hello from Gemini!"}]
                }
            }
        ]
    }

    with patch.object(provider, "_post_json", return_value=fake_response) as mock_post:
        result = provider.generate(
            prompt="Tell me a joke",
            json_mode=True,
            temperature=0.7,
            system_prompt="You are a witty assistant."
        )

        assert result == "Hello from Gemini!"
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        url = kwargs.get("url") or mock_post.call_args[0][0]
        payload = kwargs.get("payload") or mock_post.call_args[0][1]

        assert "models/gemini-2.5-flash:generateContent" in url
        assert "key=fake-gemini-key" in url
        assert payload["contents"][0]["parts"][0]["text"] == "Tell me a joke"
        assert payload["generationConfig"]["temperature"] == 0.7
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        assert payload["systemInstruction"]["parts"][0]["text"] == "You are a witty assistant."


def test_gemini_provider_empty_candidate():
    provider = GeminiProvider(api_key="fake-gemini-key")
    with patch.object(provider, "_post_json", return_value={"candidates": []}):
        with pytest.raises(ValueError, match="No candidates returned"):
            provider.generate("Test")


def test_gemini_provider_missing_key():
    provider = GeminiProvider(api_key="")
    assert provider.is_available() is False
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        provider.generate("Test")


def test_gemini_provider_rate_limit_conversion():
    provider = GeminiProvider(api_key="fake-gemini-key")
    with patch.object(provider, "_post_json", side_effect=Exception("Resource has been exhausted (quota)")):
        with pytest.raises(RuntimeError, match="Gemini rate limited"):
            provider.generate("Test")


# ── 3. OpenRouter Provider Tests ─────────────────────────────────────────────

def test_openrouter_provider_generate_success():
    provider = OpenRouterProvider(api_key="fake-openrouter-key", model="deepseek/deepseek-chat")
    assert provider.is_available() is True

    fake_response = {
        "choices": [
            {
                "message": {"content": '{"analysis": "strong match"}'}
            }
        ]
    }

    with patch.object(provider, "_post_json", return_value=fake_response) as mock_post:
        result = provider.generate(
            prompt="Analyze resume",
            json_mode=True,
            temperature=0.1,
            system_prompt="System prompt test"
        )

        assert result == '{"analysis": "strong match"}'
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        url = kwargs.get("url") or mock_post.call_args[0][0]
        payload = kwargs.get("payload") or mock_post.call_args[0][1]
        headers = kwargs.get("headers") or mock_post.call_args[0][2]

        assert url == "https://openrouter.ai/api/v1/chat/completions"
        assert headers["Authorization"] == "Bearer fake-openrouter-key"
        assert payload["model"] == "deepseek/deepseek-chat"
        assert payload["temperature"] == 0.1
        assert payload["response_format"] == {"type": "json_object"}
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"


def test_openrouter_provider_missing_key():
    provider = OpenRouterProvider(api_key=None)
    assert provider.is_available() is False
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY is not configured"):
        provider.generate("Test")


def test_openrouter_provider_rate_limit_conversion():
    provider = OpenRouterProvider(api_key="fake-openrouter-key")
    with patch.object(provider, "_post_json", side_effect=Exception("429 rate limit exceeded")):
        with pytest.raises(RuntimeError, match="OpenRouter rate limited"):
            provider.generate("Test")


# ── 4. Alibaba Provider Tests ────────────────────────────────────────────────

def test_alibaba_provider_generate_openai_format():
    provider = AlibabaProvider(api_key="fake-alibaba-key", model="qwen-plus")
    assert provider.is_available() is True

    fake_response = {
        "choices": [
            {
                "message": {"content": "Alibaba OpenAI response"}
            }
        ]
    }

    with patch.object(provider, "_post_json", return_value=fake_response) as mock_post:
        result = provider.generate("Test prompt", temperature=0.5)
        assert result == "Alibaba OpenAI response"
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        payload = kwargs.get("payload") or mock_post.call_args[0][1]
        headers = kwargs.get("headers") or mock_post.call_args[0][2]
        assert headers["Authorization"] == "Bearer fake-alibaba-key"
        assert payload["model"] == "qwen-plus"


def test_alibaba_provider_generate_anthropic_format():
    provider = AlibabaProvider(
        api_key="fake-alibaba-key",
        model="qwen3.6-flash",
        base_url="https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic/v1/messages"
    )
    fake_response = {
        "content": [
            {"type": "thinking", "text": "let me think..."},
            {"type": "text", "text": "Alibaba Anthropic response"}
        ]
    }

    with patch.object(provider, "_post_json", return_value=fake_response) as mock_post:
        result = provider.generate("Test prompt")
        assert result == "Alibaba Anthropic response"
        mock_post.assert_called_once()
        kwargs = mock_post.call_args.kwargs
        headers = kwargs.get("headers") or mock_post.call_args[0][2]
        assert headers["x-api-key"] == "fake-alibaba-key"
        assert headers["anthropic-version"] == "2023-06-01"


def test_alibaba_provider_missing_key():
    provider = AlibabaProvider(api_key=None)
    assert provider.is_available() is False
    with pytest.raises(ValueError, match="ALIBABA_API_KEY is not configured"):
        provider.generate("Test")


def test_alibaba_provider_rate_limit_conversion():
    provider = AlibabaProvider(api_key="fake-alibaba-key")
    with patch.object(provider, "_post_json", side_effect=Exception("429 Too Many Requests")):
        with pytest.raises(RuntimeError, match="Alibaba rate limited"):
            provider.generate("Test")


# ── 5. LLMGateway & Failover Chain Tests ─────────────────────────────────────

def test_gateway_failover_spec():
    """Exact test specified in Task 3 Step 1 of the implementation plan."""
    gateway = LLMGateway()
    with patch.object(gateway.alibaba_provider, "generate", side_effect=Exception("Primary unavailable")), \
         patch.object(gateway.gemini_provider, "generate", side_effect=Exception("Rate limit 429")), \
         patch.object(gateway.openrouter_provider, "generate", return_value="OpenRouter response"):
        res = gateway.generate("Hello test")
        assert res == "OpenRouter response"


def test_gateway_primary_success():
    gemini = GeminiProvider(api_key="gemini-key")
    openrouter = OpenRouterProvider(api_key="openrouter-key")
    alibaba = AlibabaProvider(api_key="alibaba-key")

    gateway = LLMGateway(gemini_provider=gemini, openrouter_provider=openrouter, alibaba_provider=alibaba)

    with patch.object(gemini, "generate", return_value="Gemini response") as mock_gemini:
        res = gateway.generate("Hello world")
        assert res == "Gemini response"
        mock_gemini.assert_called_once_with(
            prompt="Hello world",
            json_mode=False,
            temperature=0.2,
            system_prompt=None,
            model=None
        )


def test_gateway_failover_gemini_to_openrouter():
    gemini = GeminiProvider(api_key="gemini-key")
    openrouter = OpenRouterProvider(api_key="openrouter-key")
    alibaba = AlibabaProvider(api_key="alibaba-key")

    gateway = LLMGateway(gemini_provider=gemini, openrouter_provider=openrouter, alibaba_provider=alibaba)

    with patch.object(gemini, "generate", side_effect=Exception("Rate limit 429")), \
         patch.object(openrouter, "generate", return_value="OpenRouter response") as mock_openrouter:
        res = gateway.generate("Hello test")
        assert res == "OpenRouter response"
        mock_openrouter.assert_called_once()


def test_gateway_failover_all_the_way_to_alibaba():
    gemini = GeminiProvider(api_key="gemini-key")
    openrouter = OpenRouterProvider(api_key="openrouter-key")
    alibaba = AlibabaProvider(api_key="alibaba-key")

    gateway = LLMGateway(gemini_provider=gemini, openrouter_provider=openrouter, alibaba_provider=alibaba)

    with patch.object(gemini, "generate", side_effect=Exception("Gemini 500 error")), \
         patch.object(openrouter, "generate", side_effect=Exception("OpenRouter 429 rate limit")), \
         patch.object(alibaba, "generate", return_value="Alibaba fallback response"):
        res = gateway.generate("Hello fallback test")
        assert res == "Alibaba fallback response"


def test_gateway_empty_response_triggers_failover():
    gemini = GeminiProvider(api_key="gemini-key")
    openrouter = OpenRouterProvider(api_key="openrouter-key")
    alibaba = AlibabaProvider(api_key="alibaba-key")

    gateway = LLMGateway(gemini_provider=gemini, openrouter_provider=openrouter, alibaba_provider=alibaba)

    # Empty string response from Gemini should trigger fallback
    with patch.object(gemini, "generate", return_value="   "), \
         patch.object(openrouter, "generate", return_value="Valid OpenRouter response"):
        res = gateway.generate("Hello empty test")
        assert res == "Valid OpenRouter response"


def test_gateway_all_providers_fail():
    gemini = GeminiProvider(api_key="gemini-key")
    openrouter = OpenRouterProvider(api_key="openrouter-key")
    alibaba = AlibabaProvider(api_key="alibaba-key")

    gateway = LLMGateway(gemini_provider=gemini, openrouter_provider=openrouter, alibaba_provider=alibaba)

    with patch.object(gemini, "generate", side_effect=Exception("Gemini Down")), \
         patch.object(openrouter, "generate", side_effect=Exception("OpenRouter Down")), \
         patch.object(alibaba, "generate", side_effect=Exception("Alibaba Down")):
        with pytest.raises(RuntimeError, match="All providers in the fallback chain failed"):
            gateway.generate("Test all fail")


def test_gateway_singleton():
    custom_settings = Settings(gemini_api_key="custom-gemini-key")
    gw = get_gateway(settings=custom_settings)
    assert isinstance(gw, LLMGateway)
    assert gw.gemini_provider.is_available() is True


def test_gateway_alibaba_primary_order():
    settings = Settings(
        primary_llm_provider="alibaba",
        alibaba_api_key="sk-alibaba-test",
        alibaba_model="qwen3.6-flash",
        alibaba_base_url="https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions",
    )
    gw = LLMGateway(settings=settings)
    assert gw.providers[0] == gw.alibaba_provider
    assert gw.alibaba_provider.model == "qwen3.6-flash"
    assert gw.alibaba_provider.base_url == "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"

