# =========================================================
# Multi-stage Dockerfile for SapthaEvent
# - Stage 1: builder installs deps into a venv
# - Stage 2: slim runtime image, non-root user, HEALTHCHECK
# =========================================================

# ---------- Stage 1: builder ----------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System build deps for cryptography, pillow, reportlab, grpcio, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libssl-dev \
        libffi-dev \
        libjpeg-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

# Install into an isolated venv so we can copy it cleanly to the runtime stage
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=8080 \
    FLASK_ENV=production

# Runtime libs only (no compilers)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (HOME required by some libs that write caches)
RUN groupadd --system app && \
    useradd --system --gid app --home /home/app --create-home app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . /app

USER app

EXPOSE 8080

# Healthcheck hits a lightweight endpoint. Uses /ping if present, else /.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/ping" || \
        curl -fsS "http://127.0.0.1:${PORT}/" || exit 1

# gunicorn.conf.py pins workers=1 (APScheduler safety) + threads for concurrency
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
