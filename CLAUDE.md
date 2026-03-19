# lrc-match — Claude Code Instructions

## Project Overview

Semantic search engine for song lyrics. Users search by meaning/theme ("songs about letting go") instead of keywords. API-first — designed to be consumed by a Jellyfin plugin, Swagger UI, or any HTTP client.

**Core pipeline:** LRC files → parse → chunk (by section tags or time gaps) → embed (OpenAI/Ollama) → store in Qdrant → semantic search via cosine similarity.

## Stack

- **API:** FastAPI + uvicorn
- **Config:** YAML + pydantic-settings
- **Vector DB:** Qdrant (Docker)
- **Embeddings:** OpenAI (default), Ollama (local alternative)
- **Package manager:** uv
- **Build:** hatchling

## Architecture

API-first design. All functionality exposed as FastAPI endpoints. Three clients share the same API:

1. **Jellyfin plugin** (future) — renders UI inside Jellyfin, calls our API
2. **Swagger UI** — enabled in debug mode, the dev interface
3. **CLI tools** — `lrc-ingest`, `lrc-search` for command-line use

Config is YAML-first. Most users configure via `config/config.yml` and never touch a web UI. Provider-specific settings (API keys, model names) live in `config/conf.d/{provider}.yaml`.

## Commands

- `make run` — start dev server (debug mode, Swagger UI at /docs, auto-reload)
- `make test` — run pytest
- `make lint` — ruff check + format check
- `make install` — uv sync + pre-commit hooks
- `make build` — Docker build
- `uv run pytest -v` — verbose test output
- `uv run ruff check src/ --fix` — auto-fix lint issues

## Code Quality

- Pre-commit hooks: ruff (lint/format), ty (type checking), prettier (YAML/JSON/MD), conventional commits
- 120-character line length, double quotes
- Type hints on all functions
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`

## Conventions

- No services layer — route handlers contain business logic directly
- Package splits use `__init__.py` re-exports (e.g., `embedders/`, `routes/`)
- Tests use FastAPI TestClient with mocked external APIs (OpenAI, Qdrant)
- Domain models are dataclasses in `models.py`
- Config loaded once at startup, stored in `app.state`
- Music directory hardcoded to `/data/media/music/english` (until Jellyfin API integration)

## Project Structure

```
src/lrc_match/
├── app.py            # FastAPI application factory
├── config.py          # Pydantic settings + YAML loading
├── models.py          # Domain models (LrcLine, LrcChunk, LrcLyric)
├── parser.py          # LRC file parsing
├── chunker.py         # Chunking strategies (tags, gaps)
├── ingest.py          # Ingestion pipeline + CLI
├── search.py          # Search logic + CLI
├── embedders/         # Provider abstraction
│   ├── base.py        # EmbeddingProvider protocol
│   ├── openai.py      # OpenAI implementation
│   └── ollama.py      # Ollama implementation
└── routes/            # FastAPI route modules
    ├── search.py
    ├── ingest.py
    ├── config.py
    ├── collections.py
    └── health.py
```

## Gotchas

- Env var for OpenAI key is `OPENAI_API_KEY` (normalized from legacy `OPEN_AI_KEY`)
- Collection metadata in Qdrant stores provider/model/dimensions — collections are self-describing
- Ingest recreates collection by default (deletes existing data). Use `force=false` to skip if data exists.
- `.venv` lives at project root (not in `src/`)
- PRDs in `docs/prds/`, plans in `docs/plans/`
