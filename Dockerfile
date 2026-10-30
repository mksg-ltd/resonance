# --- Frontend build stage ---
FROM node:22.13.1-alpine AS frontend
RUN corepack enable && corepack prepare pnpm@9.15.4 --activate
WORKDIR /build/vue-ui
COPY vue-ui/package.json vue-ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY vue-ui/ ./
RUN pnpm build

# --- Python dependency stage ---
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project
COPY src/ src/
COPY --from=frontend /build/src/resonance/static/app/ src/resonance/static/app/
COPY README.md ./
RUN uv sync --no-dev --frozen

# --- Runtime stage ---
FROM python:3.14-slim
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/pyproject.toml /app/
COPY ui/ /app/ui/
RUN mkdir -p /app/state && chown appuser:appuser /app/state
ENV RESONANCE__JOURNAL_PATH=/app/state/playlist-operations.sqlite3
ENV FORWARDED_ALLOW_IPS=127.0.0.1
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
ENTRYPOINT ["python", "-m", "resonance.container_entrypoint"]
CMD ["uvicorn", "resonance.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
