---
status: completed
author: mk
tags:
  [
    fastapi,
    configuration,
    api,
    embeddings,
    playlists,
    historical,
    architecture-evolved,
  ]
title: "FastAPI Service & Configuration"
phase: launch
created: 2026-03-18
updated: 2026-10-27
---

# FastAPI Service & Configuration

**Status**: Completed in the evolved architecture. FastAPI, shared application
operations, CLI/API adapters, environment settings, and container deployment are in
place. The original YAML/Jellyfin assumptions were superseded by PRDs 09 and 11; user
authentication was added later in PRD-12.

---

## Overview

Restructure resonance from CLI-only scripts into a FastAPI service with YAML-driven
configuration, embedding provider abstraction, and API endpoints for search, ingestion,
and playlist management. This is the foundation everything else builds on — Jellyfin
plugin (PRD-04), lyrics crawling (PRD-05), and any future frontend all consume these
endpoints.

## Goals

- FastAPI application serving all resonance functionality as API endpoints
- YAML config file + pydantic-settings for typed, validated configuration
- Embedding provider abstraction (OpenAI, Ollama, Sentence Transformers)
- Swagger UI available in dev mode as the working interface
- Retain CLI tools (ingest, search) that call the same config/provider layer
- Pre-commit hooks, Makefile, testing — production-grade project plumbing
- Open-source ready: users install alongside Jellyfin, configure via YAML

## Non-Goals

- Standalone web frontend (Swagger UI is sufficient for now; Jellyfin plugin later)
- Auth/roles (single-user self-hosted; multi-user deferred)
- Hot-reloading config changes — restart is acceptable
- Database beyond Qdrant (no Postgres/SQLite — playlist state lives in Jellyfin plugin)

## Architecture

```
┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐
│ Jellyfin Plugin │  │  Swagger UI  │  │  Future Frontend  │
│   (PRD-04)      │  │  (dev mode)  │  │   (optional)      │
└────────┬────────┘  └──────┬───────┘  └────────┬──────────┘
         └──────────────────┼────────────────────┘
                            │ HTTP
                    ┌───────▼───────┐
                    │  FastAPI App  │
                    │  (resonance)  │
                    └───────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
         ┌────▼───┐   ┌────▼────┐  ┌─────▼─────┐
         │ Qdrant │   │ Config  │  │ Embedding  │
         │        │   │ (YAML)  │  │ Provider   │
         └────────┘   └─────────┘  └───────────┘
```

All clients (Jellyfin plugin, Swagger UI, CLI, future frontend) hit the same
FastAPI endpoints. The API contract is the product.

## Design

### Configuration

#### Hierarchy (each layer overrides the previous)

```
code defaults → config.yaml → environment variables
```

#### Config File

Main config stays minimal — most users only touch this:

```yaml
# config.yaml

embedding:
  provider: openai # openai | ollama | sentence-transformers

qdrant:
  url: http://localhost:6333
  collection: lyrics
  api_key: null # for Qdrant Cloud

chunking:
  gap_threshold_sec: 10.0
  min_chunk_lines: 2

jellyfin:
  url: null # future: Jellyfin API integration (PRD-04/05)
  api_key: null

server:
  host: 0.0.0.0
  port: 8000
  debug: false # enables Swagger UI
```

Provider-specific settings live in separate files under `conf.d/`:

```yaml
# conf.d/openai.yaml
api_key: ${OPENAI_API_KEY}    # env var reference, never plaintext
model: text-embedding-3-small

# conf.d/ollama.yaml
base_url: http://localhost:11434
model: nomic-embed-text
```

Only the file matching `embedding.provider` is loaded. Users configure one
provider and ignore the rest — no wall of irrelevant settings.

**Note:** `conf.d/` directory merging only if pydantic-settings supports it
natively or with minimal glue. If it requires heavy custom code, fall back
to a single file with provider sections. Don't over-engineer the loader.

#### Music directory

Hardcoded to `/data/media/music/english` for now. No `library.music_dir`
config — it creates confusion about host paths vs container paths vs Jellyfin
paths. When Jellyfin API integration lands (PRD-04/05 research), ingest will
go through the Jellyfin API and this goes away entirely.

#### Pydantic Settings

```python
class Settings(BaseSettings):
    """Validated config with env var override support."""
    embedding: EmbeddingConfig        # just provider name
    qdrant: QdrantConfig
    chunking: ChunkingConfig
    jellyfin: JellyfinConfig | None = None
    server: ServerConfig

    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        env_nested_delimiter="__",
    )
```

Provider config (OpenAI, Ollama, etc.) loaded separately based on
`embedding.provider` value — from `conf.d/{provider}.yaml` if available.

### Embedding Provider Abstraction

```python
class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...
```

Implementations:

- `OpenAIEmbedder` — current approach, uses OpenAI API
- `OllamaEmbedder` — local models via Ollama (nomic-embed-text, mxbai-embed-large)
- `SentenceTransformerEmbedder` — direct HuggingFace models, no server needed

A fully self-hosted stack (Jellyfin + Qdrant + Ollama) with zero cloud dependencies
is a key differentiator for the project.

### API Endpoints

#### Search

- `POST /api/search` — semantic lyric search
  - Body: `{ query: str, artist?: str, limit?: int }`
  - Returns ranked results grouped by song, with lyrics preview

#### Ingest

- `POST /api/ingest` — trigger ingestion run
  - Body: `{ force?: bool }`
  - Reads from hardcoded `/data/media/music/english` (until Jellyfin API integration)
  - Returns job status (count of files processed, chunks created)

#### Config

- `GET /api/config` — current configuration (keys redacted)
- `PUT /api/config` — update configuration (admin only, later)

#### Collections

- `GET /api/collections` — list Qdrant collections
- `DELETE /api/collections/{name}` — drop a collection

#### Health

- `GET /health` — service health check (Qdrant connectivity, config valid)

### Project Structure

```
resonance/
├── src/resonance/
│   ├── __init__.py
│   ├── app.py               # FastAPI application factory
│   ├── config.py             # Pydantic settings + YAML loading
│   ├── models.py             # Domain models (existing)
│   ├── parser.py             # LRC parsing (existing)
│   ├── chunker.py            # Chunking (existing)
│   ├── embedders/            # Provider abstraction
│   │   ├── __init__.py       # Re-exports, factory function
│   │   ├── base.py           # EmbeddingProvider protocol
│   │   ├── openai.py         # OpenAI implementation
│   │   └── ollama.py         # Ollama implementation
│   ├── routes/               # FastAPI route modules
│   │   ├── __init__.py
│   │   ├── search.py
│   │   ├── ingest.py
│   │   ├── config.py
│   │   └── health.py
│   ├── ingest.py             # Ingestion logic (refactored from CLI)
│   └── search.py             # Search logic (refactored from CLI)
├── tests/
│   ├── conftest.py
│   ├── test_config.py
│   ├── test_embedders.py
│   ├── test_search.py
│   ├── test_ingest.py
│   └── test_chunker.py
├── docs/prds/
├── config.yaml.example       # Example config (checked in)
├── pyproject.toml
├── docker-compose.yml
├── Makefile
├── .pre-commit-config.yaml
├── CLAUDE.md
└── uv.lock
```

### Tooling & Dev Workflow

Adopted from reference projects (nool, passage):

- **Ruff** — lint + format (120 chars, double quotes)
- **ty** — type checking (relaxed for false positives)
- **pytest** — tests (real Qdrant, mock external APIs like OpenAI)
- **Pre-commit hooks** — ruff, ty, trailing whitespace, YAML checks, conventional commits
- **Makefile** — `make run`, `make test`, `make lint`, `make install`
- **uv** — package management
- **Type hints** on all functions
- **Conventional commits** — `feat:`, `fix:`, `docs:`, etc.

## Implementation Plan

### Phase 1 — Project Plumbing

- [ ] Pre-commit hooks (.pre-commit-config.yaml)
- [ ] Makefile (run, test, lint, install)
- [ ] CLAUDE.md with project conventions
- [ ] pyproject.toml updates (FastAPI deps, ruff/ty/pytest config)
- [ ] config.yaml.example

### Phase 2 — Config Layer

- [ ] Pydantic settings model with YAML loading
- [ ] Environment variable override support
- [ ] Config validation (e.g., OpenAI key required when provider is openai)
- [ ] Refactor existing ingest.py and search.py to use config instead of hardcoded values

### Phase 3 — Embedding Provider Abstraction

- [ ] EmbeddingProvider protocol
- [ ] OpenAI implementation (extract from current ingest.py)
- [ ] Ollama implementation
- [ ] Factory function: `create_embedder(config) -> EmbeddingProvider`
- [ ] Dimension auto-detection for known models

### Phase 4 — FastAPI Application

- [ ] App factory with lifespan (Qdrant client, embedder init)
- [ ] Health endpoint
- [ ] Search endpoint (reuse existing search logic)
- [ ] Ingest endpoint (reuse existing ingest logic)
- [ ] Config endpoint (read-only, keys redacted)
- [ ] Collections endpoint
- [ ] Swagger UI enabled when `server.debug: true`

### Phase 5 — Docker & Deployment

- [ ] Multi-stage Dockerfile
- [ ] Update docker-compose.yml (add resonance service alongside Qdrant)
- [ ] config.yaml volume mount
- [ ] Health check in compose

## Decisions

- **Switching embedding models** — warn only, don't auto-re-ingest. Re-ingestion
  can be expensive (API costs, time). User triggers it explicitly.
- **Multiple collections** — yes, supported. Each collection stores its provider,
  model, and dimensions as Qdrant collection metadata. Search/ingest reads this
  from the collection instead of requiring the user to pass it. No more dimension
  mismatch footgun.
- **Playlist persistence** — not in scope for this PRD. Per-user state belongs in
  the Jellyfin plugin (PRD-04), backed by Jellyfin's own storage/plugin metadata.
- **Ingestion execution** — async endpoint (`POST /api/ingest`), no background job
  runner. No web-based monitoring needed yet.

---

## Changelog

- 2026-03-19: Resolved open questions — warn on model switch, collection-level
  metadata for dimensions, SQLite for playlists, async ingest endpoint. Simplified
  config: removed embedding block (provider settings in conf.d/), removed
  library.music_dir (hardcoded until Jellyfin API).
- 2026-03-19: Expanded from "User Configuration" to full FastAPI service PRD. Absorbed
  search/playlist features from superseded PRD-02. Added project structure, API design,
  tooling setup, and implementation phases.
- 2026-03-18: Initial draft (as "User Configuration")
