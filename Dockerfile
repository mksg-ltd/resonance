# Multi-stage build for resonance FastAPI service

# --- Builder stage ---
FROM python:3.14-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen || uv sync --no-dev

# Copy source
COPY src/ src/
COPY README.md ./
RUN uv sync --no-dev --frozen || uv sync --no-dev

# --- Runtime stage ---
FROM python:3.14-slim

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

USER appuser

CMD ["uvicorn", "resonance.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
