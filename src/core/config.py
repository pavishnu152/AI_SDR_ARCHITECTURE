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

    # --- CORS ---
    # Comma-separated origins the frontend dashboard is served from. Defaults
    # cover Vite's dev server (5173) and its production preview server
    # (4173) — the two ports frontend/ actually runs on locally. An
    # explicit allow-list instead of "*" is still the right default even
    # though this API uses bearer tokens (not cookies, so "*" wouldn't be a
    # CSRF issue here specifically) — it's the pattern that stays correct
    # if auth ever moves to cookies later, and it's what you'd be expected
    # to already have in a real deployment.
    cors_allowed_origins: str = "http://localhost:5173,http://localhost:4173"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings instance. `lru_cache` here means Settings() is only
    constructed once per process (env parsed once), and every module that
    calls get_settings() gets the same object — standard FastAPI pattern
    for dependency-injected config.
    """
    return Settings()
