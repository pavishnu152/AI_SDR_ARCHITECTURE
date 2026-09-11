import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Make `src` importable when alembic is invoked from the project root
# (matches how pyproject.toml's pytest config does the same thing).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings  # noqa: E402
from src.db.models import Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Autogenerate compares the live DB against Base.metadata — every model in
# db/models.py is registered on this Base, so a new model automatically
# gets picked up by `alembic revision --autogenerate` with no extra wiring.
target_metadata = Base.metadata

# Pull the DB URL from our own Settings (single source of truth — env vars,
# .env file, same as the running app) instead of duplicating it as a
# separate hardcoded value in alembic.ini. This is the one line that makes
# `alembic upgrade head` connect to whatever DATABASE_URL the app itself
# would use, in every environment (local dev, Docker, CI) without editing
# alembic.ini per environment.
config.set_main_option("sqlalchemy.url", settings().database_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
