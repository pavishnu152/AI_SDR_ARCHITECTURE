"""
Health check endpoint. Trivial on purpose right now — it exists so:
1. Deployment platforms (Render/Railway) have something to poll to know
   the container is alive.
2. We have a working, testable route before any real business logic
   exists, to prove the FastAPI app + test harness are wired correctly.
"""
from fastapi import APIRouter

from src.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict:
    settings = get_settings()
    return {"status": "ok", "env": settings.app_env}
