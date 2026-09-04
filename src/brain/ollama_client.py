"""Ollama REST API client for local model inference."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Iterator, Optional, Union

import requests

from src.brain.config import get_brain_settings
from src.brain.model_registry import get_model_registry

logger = logging.getLogger(__name__)

# Spec §5.2 per-mode runtime profiles.
MODE_PROFILES: Dict[str, Dict[str, Any]] = {
    "tailor-resume": {"num_ctx": 4096, "num_predict": 900, "temperature": 0.3, "num_batch": 512},
    "tailor-letter": {"num_ctx": 4096, "num_predict": 700, "temperature": 0.6, "num_batch": 512},
    "qa-avatar": {"num_ctx": 2048, "num_predict": 512, "temperature": 0.7, "num_batch": 256},
}


class OllamaClient:
    """Client for Ollama REST API with per-mode profiles and registry model resolution."""

    # Token-usage meta from the last non-stream ``generate`` call (keys
    # ``prompt_eval_count``/``eval_count``; {} when the server omitted them,
    # None before any call or after an error). The stream path leaves it
    # untouched — per-chunk responses carry no final counts until the last
    # line, which the iterator does not parse.
    last_meta: Optional[Dict[str, Any]] = None

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        settings = get_brain_settings()
        self.base_url = (base_url or settings.BRAIN_OLLAMA_URL).rstrip("/")
        self.model = model or settings.BRAIN_OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else settings.BRAIN_INFERENCE_TIMEOUT
        self.session = requests.Session()
        self.registry = get_model_registry()
        self.last_meta = None

    def health_check(self, timeout: float = 1.0) -> bool:
        """Check if Ollama server is running."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=timeout)
            return response.status_code == 200
        except Exception:
            return False

    def is_available(self) -> bool:
        """Check if Ollama is available and the model exists."""
        return self.health_check()

    @staticmethod
    def resolve_profile(mode: str, facet: Optional[str] = None) -> str:
        """Map pipeline mode (and tailoring facet) to a MODE_PROFILES key."""
        if mode == "tailoring":
            return "tailor-letter" if facet == "letter" else "tailor-resume"
        return "qa-avatar"

    def resolve_model(self, mode: str, model: Optional[str]) -> str:
        """Per-call model resolution: explicit arg > registry > instance default."""
        if model:
            return model
        entry = (self.registry.get_model_for_mode(mode)
                 if getattr(self, "registry", None) else None)
        if entry and entry.get("model_name"):
            return entry["model_name"]
        return self.model

    def _build_options(
        self,
        mode: str = "avatar",
        user_options: Optional[Dict[str, Any]] = None,
        facet: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build optimized runtime options from the mode profile with hardware tuning."""
        profile = MODE_PROFILES[self.resolve_profile(mode, facet)]
        cpu_threads = min(8, max(1, os.cpu_count() or 4))
        opts: Dict[str, Any] = {
            "temperature": profile["temperature"],
            "top_p": 0.9,
            "num_predict": profile["num_predict"],
            "num_ctx": profile["num_ctx"],
            "num_batch": profile["num_batch"],
            "num_thread": cpu_threads,
        }
        # Hardware auto-detection: offload GPU layers if CUDA or flag is present
        if os.environ.get("BRAIN_GPU_ENABLED", "0").lower() in {"1", "true", "yes"}:
            opts["num_gpu"] = 99
        if user_options:
            opts.update(user_options)
        return opts

    def _payload(
        self,
        prompt: str,
        mode: str,
        model: Optional[str],
        keep_alive: str,
        options: Optional[Dict[str, Any]],
        fmt: Optional[Any],
        stream: bool,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.resolve_model(mode, model),
            "prompt": prompt,
            "stream": stream,
            "keep_alive": keep_alive,
            "options": self._build_options(mode=mode, user_options=options),
        }
        if fmt is not None:
            payload["format"] = fmt
        return payload

    def generate(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        mode: str = "avatar",
        keep_alive: str = "30m",
        model: Optional[str] = None,
        format: Optional[Any] = None,
        stream: bool = False,
    ) -> Union[str, Iterator[str]]:
        """Generate; stream=True returns a token iterator (spec §5.8).

        Non-stream calls record the response token counts in ``last_meta``
        (truncation watchdog input, spec §5.8); errors reset it to None.
        Stream calls leave ``last_meta`` untouched.
        """
        if stream:
            return self._stream(prompt, options, timeout, mode, keep_alive, model, format)
        payload = self._payload(prompt, mode, model, keep_alive, options, format, False)
        try:
            response = self.session.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception:
            self.last_meta = None
            raise
        self.last_meta = {k: data[k] for k in ("prompt_eval_count", "eval_count")
                          if k in data}
        return data["response"]

    def _stream(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]],
        timeout: Optional[int],
        mode: str,
        keep_alive: str,
        model: Optional[str],
        fmt: Optional[Any],
    ) -> Iterator[str]:
        """Stream token chunks from Ollama REST API in real-time."""
        payload = self._payload(prompt, mode, model, keep_alive, options, fmt, True)
        response = self.session.post(
            f"{self.base_url}/api/generate",
            json=payload,
            timeout=timeout or self.timeout,
            stream=True,
        )
        response.raise_for_status()
        for line in response.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode("utf-8"))
                    if "response" in data:
                        yield data["response"]
                except Exception:
                    continue

    def generate_stream(
        self,
        prompt: str,
        options: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        mode: str = "avatar",
        keep_alive: str = "30m",
        model: Optional[str] = None,
        format: Optional[Any] = None,
    ) -> Iterator[str]:
        """Back-compat alias for generate(..., stream=True)."""
        return self.generate(prompt, options, timeout, mode, keep_alive,
                             model=model, format=format, stream=True)

    def list_models(self) -> list:
        """List available models."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []
