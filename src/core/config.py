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
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    # --- LLM ---
    anthropic_api_key: str = ""
    research_scoring_model: str = "claude-haiku-4-5-20251001"
    drafting_guardrail_model: str = "claude-sonnet-5"

    # --- Database ---
    database_url: str = "postgresql+psycopg2://ai_sdr:ai_sdr@localhost:5432/ai_sdr"

    # --- Auth ---
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    # --- ICP ---
    icp_config_path: str = "configs/icp_ai_native_b2b.yaml"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. `lru_cache` here means Settings() is only
    constructed once per process (env parsed once), and every module that
    calls get_settings() gets the same object — standard FastAPI pattern
    for dependency-injected config.
    """
    return Settings()
