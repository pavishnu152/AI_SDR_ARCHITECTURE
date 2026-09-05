"""
Centralized app configuration.

Why pydantic-settings instead of raw os.getenv() calls scattered around the
codebase: every setting is typed, validated once at startup (fail fast if a
required var is missing), and testable by overriding `Settings` instead of
monkeypatching environment variables in every test.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- LLM ---
    # Gemini API through Google's OpenAI-compatible endpoint.
    # The existing agents can continue using the OpenAI Python SDK;
    # only the provider endpoint, API key, and model IDs change.
    gemini_api_key: str = ""
    gemini_base_url: str = (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    # --- Dev/testing ---
    # When true, agents skip the real Gemini call and return canned mock
    # output instead. Lets you exercise the full pipeline (DB, orchestrator,
    # frontend) without burning the Gemini free-tier daily quota.
    mock_llm: bool = False

    # Tiered by task cost/risk:
    # faster/cheaper model for research + scoring
    # stronger model for drafting + guardrail
    research_scoring_model: str = "gemini-3.6-flash"
    drafting_guardrail_model: str = "gemini-3.6-flash"

    # --- Database ---
    database_url: str = (
        "postgresql+psycopg2://ai_sdr:ai_sdr@localhost:5432/ai_sdr"
    )

    # --- Auth ---
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- ICP ---
    icp_config_path: str = "configs/icp_ai_native_b2b.yaml"

    # --- CORS ---
    # Comma-separated origins the frontend dashboard is served from.
    cors_allowed_origins: str = (
        "http://localhost:5173,http://localhost:4173"
    )

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


@lru_cache
def settings() -> Settings:
    """
    Cached settings instance. `lru_cache` here means Settings() is only
    constructed once per process (env parsed once), and every module that
    calls settings() gets the same object — standard FastAPI pattern
    for dependency-injected config.
    """
    return Settings()