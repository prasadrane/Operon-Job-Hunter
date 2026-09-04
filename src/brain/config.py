"""Brain service configuration."""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class BrainSettings(BaseSettings):
    """Career Brain service settings. Loaded from BRAIN_* env vars."""

    BRAIN_ENABLED: bool = True
    BRAIN_OLLAMA_URL: str = "http://localhost:11434"
    BRAIN_OLLAMA_MODEL: str = "career-brain"
    BRAIN_TRAINING_DATA_PATH: Path = Path("data/brain/training_pairs.jsonl")
    BRAIN_RETRIEVAL_TOP_K: int = Field(default=3, ge=1, le=20)
    BRAIN_FACTGUARD_ENABLED: bool = True
    BRAIN_DEFAULT_MODE: Literal["auto", "avatar", "tailoring", "qa"] = "auto"
    BRAIN_INFERENCE_TIMEOUT: int = Field(default=180, ge=5, le=600)
    BRAIN_FALLBACK_TO_CLOUD: bool = True
    BRAIN_TEACHER_MODEL: str = "qwen3.8-max"
    BRAIN_CACHE_MAX_SIZE: int = Field(default=256, ge=0, le=4096)
    BRAIN_TELEMETRY_DIR: Path = Path("data/brain/telemetry")

    model_config = {"env_prefix": "", "case_sensitive": True}


@lru_cache()
def get_brain_settings() -> BrainSettings:
    return BrainSettings()
