#!/bin/sh
# Runs on every container start (not just first deploy): applies any
# pending Alembic migrations before the app starts serving traffic, then
# hands off to whatever CMD was passed (uvicorn in production, could be
# overridden to a shell for debugging). `set -e` means a failed migration
# stops the container from starting at all — starting an API server
# against a schema it doesn't match is worse than not starting.
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
