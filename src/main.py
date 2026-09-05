"""
FastAPI application entrypoint.

Milestone 7 wires up the real routers: auth (register/login) and leads
(create + run pipeline, read). Routers are kept in src/api/ as separate
modules per resource, included here rather than defining routes directly
on `app` — this is what lets each router file stay focused and testable
independently (see tests/api/test_auth.py, test_leads.py).
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.auth import router as auth_router
from src.api.health import router as health_router
from src.api.leads import router as leads_router
from src.api.middleware import RequestIDMiddleware
from src.core.config import settings
from src.core.logging import configure_logging

config = settings()
configure_logging(config.log_level)

app = FastAPI(
    title="AI SDR — Multi-Agent Lead Research & Qualification",
    version="0.1.0",
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(leads_router)
