"""Tests for src/core/config.py — currently just the CORS origin parsing,
the one piece of actual logic in an otherwise pass-through Settings class."""
from src.core.config import Settings


def test_cors_allowed_origins_list_splits_and_strips():
    settings = Settings(cors_allowed_origins="http://a.com, http://b.com ,http://c.com")

    assert settings.cors_allowed_origins_list == [
        "http://a.com",
        "http://b.com",
        "http://c.com",
    ]


def test_cors_allowed_origins_list_ignores_empty_entries():
    settings = Settings(cors_allowed_origins="http://a.com,,  ,http://b.com")

    assert settings.cors_allowed_origins_list == ["http://a.com", "http://b.com"]


def test_cors_allowed_origins_list_defaults_to_vite_dev_and_preview_ports():
    settings = Settings()

    assert settings.cors_allowed_origins_list == [
        "http://localhost:5173",
        "http://localhost:4173",
    ]
