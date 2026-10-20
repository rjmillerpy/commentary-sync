# API image: the FastAPI app served by uvicorn on port 8000.
#
#   docker build -t commentary-sync-api .
#
# Multi-stage: `builder` installs the Python dependencies with uv; `runtime`
# starts from a clean base and copies in only the virtualenv and the app code.
# Build tooling, the lockfile, tests and local caches never reach the final
# image.

# uv comes from Astral's image (a named stage so Dependabot can bump it).
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

# ── builder: resolve and install dependencies into /opt/venv ────────────────
FROM python:3.12-slim AS builder

# UV_PROJECT_ENVIRONMENT: build the venv at the path the runtime stage uses
# (venvs hold absolute paths, so it must not move).
# UV_LINK_MODE=copy: the cache is a build mount, so copy files out of it
# instead of hard-linking to something that won't exist in the image.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

WORKDIR /build

# Only the two dependency files: this layer is cached until one of them
# changes, so editing app code doesn't trigger a reinstall.
# --locked: exactly uv.lock (fails if it is stale); --no-dev: no test or lint
# tools; --no-install-project: dependencies only.
# --all-packages --no-editable: workspace packages are copied into the venv.
COPY pyproject.toml uv.lock ./
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project --all-packages --no-editable

# ── runtime: what actually runs ─────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# PYTHONDONTWRITEBYTECODE: no .pyc files (the app user can't write them anyway).
# PYTHONUNBUFFERED: logs reach `docker logs` immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Pinned, so a missing matcher package fails loudly instead of quietly
# falling back to the baseline (app/sync/matcher.py).

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

# Run as an unprivileged user.
RUN useradd --create-home --uid 1000 app

# An explicit list, not `COPY . .`: a new file in the repo (a recording, a
# cache) can't end up in the image by accident. Left root-owned, so the app
# user can read its code but not change it.
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY --chmod=755 docker-entrypoint.sh ./

USER app

EXPOSE 8000

# The entrypoint applies pending migrations, then execs the command.
ENTRYPOINT ["./docker-entrypoint.sh"]
# Exec form: uvicorn is PID 1 and receives SIGTERM directly, so `docker stop`
# lets in-flight requests finish and the lifespan close the pool.
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
