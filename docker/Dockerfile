# syntax=docker/dockerfile:1
#
# Multi-stage build: a "builder" stage installs the app + its dependencies
# into an isolated virtualenv, and the "runtime" stage copies only that
# venv (not pip's cache, not build tooling) into a fresh slim image. This
# keeps the shipped image smaller and reduces its attack surface — the
# runtime image never has a C compiler or pip's download cache sitting in
# it for an attacker (or a curious `docker exec`) to find.
#
# NOTE on layer caching (a known, documented limitation, not an oversight):
# the classic "copy just the dependency file, install deps, THEN copy
# source" trick — which lets Docker reuse the dependency-install layer on
# every rebuild where only application code changed — doesn't cleanly
# apply here. This project installs via `pip install .` against a
# src-layout package, and setuptools needs the actual package files
# present to resolve that install, not just pyproject.toml's metadata. The
# correct production fix is a pip-compile-generated, dependencies-only
# requirements.txt installed before the source is copied (see Future
# Improvements in docs/architecture.md) — not done here to avoid adding a
# new tool/process for a portfolio-stage build. Practical effect: a
# code-only change currently invalidates the dependency-install layer too,
# making rebuilds slower than they could be. Real, documented, not hidden.

FROM python:3.11-slim AS builder

WORKDIR /build

COPY pyproject.toml ./
COPY src/ ./src/
COPY configs/ ./configs/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


FROM python:3.11-slim AS runtime

# Never run production containers as root — a dependency RCE or container
# escape has far less blast radius as an unprivileged user than as root.
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY src/ ./src/
COPY configs/ ./configs/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY docker/entrypoint.sh ./entrypoint.sh

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x entrypoint.sh && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

# Dependency-free healthcheck (stdlib urllib only) — doesn't rely on curl
# or wget being present in the slim base image, which they aren't.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
