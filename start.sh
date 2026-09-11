#!/bin/bash
set -e

poetry run alembic upgrade head
exec poetry run uvicorn src.main:app --host 0.0.0.0 --port $PORT