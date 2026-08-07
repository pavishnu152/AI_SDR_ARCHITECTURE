"""
FastAPI application entrypoint.

Kept minimal at this milestone: config + logging wiring and a health route.
Agent routers (leads, pipeline runs) get added in Milestone 7 once the
agents and orchestrator actually exist — no point exposing endpoints for
logic that doesn't exist yet.
"""
from fastapi import FastAPI

from src.api.health import router as health_router
from src.core.config import get_settings
from src.core.logging import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="AI SDR — Multi-Agent Lead Research & Qualification",
    version="0.1.0",
)

app.include_router(health_router)
