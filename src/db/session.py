"""
DB engine/session setup.

Why a generator-based `get_db` dependency: FastAPI calls the generator,
hands the yielded session to the route, then resumes the generator after
the response is sent — guaranteeing the session (and its connection) is
closed even if the route raises. Manually opening/closing sessions inside
every route is how connection leaks happen in production.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
