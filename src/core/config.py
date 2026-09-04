"""Global configuration and settings management for OperonJobHuntAI."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and defaults."""

    # Pipeline threshold
    min_fit_score: float = 72.0
    resume_target_pages: int = 1

    # --- Candidate profile indirection (portfolio-safe) ---
    # Real personal profiles live OUTSIDE the repo; default ships the fictional sample persona.
    profile_dir: str = Field(
        default="./data/sample",
        validation_alias=AliasChoices("PROFILE_DATA_DIR", "PROFILE_DIR", "profile_dir"),
    )
    companies_config_path: str = ""  # empty => derive from profile_dir

    def profile_path(self, name: str) -> Path:
        """Resolve a file inside the active candidate profile directory."""
        return Path(self.profile_dir) / name

    @property
    def master_resume_md_path(self) -> Path:
        return self.profile_path("MASTER_RESUME.md")

    @property
    def master_resume_jsonl_path(self) -> Path:
        return self.profile_path("MASTER_RESUME.jsonl")

    @property
    def companies_yaml_path(self) -> Path:
        if self.companies_config_path:
            return Path(self.companies_config_path)
        return self.profile_path("companies.yaml")

    # Storage paths & Checkpointers
    db_path: str = "./data/careergraph.db"
    browser_profile_dir: str = "./data/browser_profile"
    artifacts_dir: str = "./data/artifacts"
    h1b_data_path: str = "./data/h1b_sponsors.json"
    checkpointer_driver: str = "sqlite"
    postgres_checkpointer_url: Optional[str] = None
    node_timeout_seconds: float = 45.0

    # Candidate profile & Compiler backend
    active_candidate_id: str = "default"
    pdf_compiler_backend: str = "reportlab"  # "reportlab" | "typst"

    # API Keys & LLM Providers
    primary_llm_provider: str = "alibaba"  # "alibaba" | "gemini" | "openrouter"
    gemini_api_key: Optional[str] = None
    openrouter_api_key: Optional[str] = None
    alibaba_api_key: Optional[str] = None
    alibaba_base_url: str = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1/chat/completions"
    alibaba_model: str = "qwen3.6-flash"

    # Telegram Bot
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # Server configuration
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    debug: bool = False

    # Security hardening
    rate_limit_enabled: bool = True
    rate_limit_rpm: int = 60  # requests per minute per client
    cors_origins: str = "*"  # comma-separated allowed origins; "*" for dev

    # Browser Use integration (Tier 2 submission)
    browser_use_enabled: bool = True
    browser_use_vision: str = "auto"  # "auto" | "true" | "false"
    browser_use_max_steps: int = 30
    browser_use_max_failures: int = 3
    browser_use_timeout_seconds: int = 90
    browser_use_model: str = "qwen-vl-max"
    browser_use_fallback_provider: str = "gemini"
    browser_use_fallback_model: str = "gemini-2.5-flash"

    # Submission audit logging
    submission_audit_enabled: bool = True

    # CapSolver integration
    capsolver_api_key: Optional[str] = None
    capsolver_timeout_sec: int = 120
    captcha_auto_solve: bool = False

    # Credential vault (OS keyring for secure credential storage)
    credential_backend: str = "keyring"  # "keyring" | "env" | "file"
    credential_service_name: str = "careergraph"
    credential_file_path: str = "./data/credentials.json"  # for file backend

    # ── P5b: Adzuna public API (free tier requires app_id/app_key) ───────────
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""

    # P5c: when False, ApplicationAgent never resumes past the submit interrupt.
    auto_submit_enabled: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
