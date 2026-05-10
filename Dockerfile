# syntax=docker/dockerfile:1.7

# ---------- Stage 1: builder ----------
FROM python:3.11-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libsndfile1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable

COPY pyproject.toml uv.lock ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

ENV TFHUB_CACHE_DIR=/opt/tfhub
RUN mkdir -p /opt/tfhub && \
    /app/.venv/bin/python -c "import tensorflow_hub as hub; hub.load('https://tfhub.dev/google/yamnet/1')"

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim-bookworm AS runtime

# libsndfile1 -> soundfile/librosa, libgomp1 -> sklearn/numpy/TF OpenMP, curl -> HEALTHCHECK
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
        libgomp1 \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1000 app \
    && useradd  --system --uid 1000 --gid app --home-dir /app --shell /sbin/nologin app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    TFHUB_CACHE_DIR=/opt/tfhub \
    TF_CPP_MIN_LOG_LEVEL=2 \
    PORT=8000 \
    WEB_CONCURRENCY=2

WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /opt/tfhub /opt/tfhub
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# Each uvicorn worker independently loads TF + the joblib model (~500MB).
# Lower WEB_CONCURRENCY on memory-constrained hosts.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/auth/health" || exit 1

# `exec` keeps uvicorn as PID 1 so SIGTERM reaches it for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
