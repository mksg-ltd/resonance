# resonance — Claude Code Instructions

## Project Overview

Semantic search engine for song lyrics. Users search by meaning/theme ("songs about letting go") instead of keywords. Shared Python application operations serve CLI and FastAPI; future Vue and FastMCP clients consume the FastAPI contracts. Navidrome is the production library source.

**Core pipeline:** Navidrome metadata/synced lyrics → normalized Track → chunk → embed (TEI-compatible/OpenAI/Ollama) → Qdrant → semantic search using server song IDs.

## Stack

- **API:** FastAPI + uvicorn
- **Config:** Bundled embedding profile YAML + pydantic-settings environment settings
- **Vector DB:** Qdrant (Docker)
- **Embeddings:** TEI through its OpenAI-compatible API; explicit OpenAI/Ollama configurations also supported
- **Web UI:** Vue 3/Vite scaffold built into the Python image at `/app/`; operator PoC at `/ui`
- **Package manager:** uv
- **Build:** hatchling

## Architecture

Transport-independent application operations live in `application/`. CLI and FastAPI
are thin adapters; no CLI imports route-owned business logic. Navidrome supplies song
identity, metadata, and structured lyrics, with no music filesystem mount.

Settings load from `.env`/environment using pydantic-settings. Supported embedding
profiles ship in `resonance/data/embedding_profiles.yaml`; endpoint and credential
values come from environment settings. There is no user-maintained provider config
directory.
Native collections bind server/account/library and effective embedding/index settings.
Qdrant owns actual section-completion state. SQLite is only for native playlist-save
operations, not track mapping. The current HTML is an operator PoC. Treat ingestion,
library selection, and embedding configuration as admin operations; semantic search
and private playlist creation are user-facing operations intended for a Vue UI and
equivalent MCP tools over the FastAPI API. A playback client/tool handles playback. Multi-user auth and identity mapping,
full per-library refresh, MCP, and seed/theme playlist generation remain future scope.

## Commands

- `make run` — start dev server (debug mode, Swagger UI at /docs, auto-reload)
- `pnpm --dir vue-ui dev` — Vue/Vite dev server at 127.0.0.1:5173; `/api` is proxied to FastAPI
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

- Shared application layer — source/index policy is independent of FastAPI/argparse
- Package splits use `__init__.py` re-exports (e.g., `embedders/`, `routes/`)
- Tests use FastAPI TestClient with mocked external APIs (OpenAI, Qdrant)
- Domain models are dataclasses in `models.py`
- Config loaded once at startup, stored in `app.state`
- Production discovery uses an explicit Navidrome library ID; filesystem scanning, raw-LRC, and local M3U paths are retired

## Project Structure

```
src/resonance/
├── application/       # Shared indexing, ingestion, search, library and save policy
├── navidrome.py       # Form POST API, paging, metadata/lyrics, XML playlists
├── state.py           # Transactional SQLite save-operation journal
├── models.py          # Track, lyric primitives, server response DTOs
├── config.py          # Pydantic environment settings
├── data/              # Bundled embedding profile catalog
├── embedders/         # OpenAI-compatible/TEI and Ollama clients
├── routes/            # Thin HTTP adapters and native auth
├── ingest.py          # Native ingestion CLI
├── search.py          # Semantic search CLI
├── library.py         # Read-only native inspection CLI
├── playlists.py       # Native save/status CLI
└── chunker.py         # Tags/gaps/min-lines lyric chunking
```

## Gotchas

- Embedding runtime settings use `RESONANCE__EMBEDDING__PROFILE`, `BASE_URL`, and
  `API_KEY`; legacy shell `OPENAI_API_KEY` remains a fallback for OpenAI.
- Collection metadata in Qdrant stores profile/provider/model/dimensions — collections are self-describing
- Native ingest never deletes/recreates a collection automatically. Identical partial writes can resume; changed indexed lyrics require a new collection until refresh is implemented. HTTP uses Navidrome-verified sessions; ingestion and collection deletion require `RESONANCE_ADMIN_USER`.
- `.venv` lives at project root (not in `src/`)
- PRDs in `docs/prds/`, plans in `docs/plans/`

- Navidrome 0.64.2 omits `public=false` in JSON; native saves verify explicit XML visibility.
- Never parse `.env` through Make or print credentials/lyrics in default logs.
- `docker-compose.dev.yml` was intentionally removed; dev commands use the sole Compose file.

- Native create/status uses globally unique operation keys; never automatically retry unknown-ID creation. Keep the SQLite journal durable. Browser authentication uses an HttpOnly cookie and same-origin API calls; Navidrome-dependent CLI commands prompt for credentials. Configure only trusted TLS proxy IPs for forwarded HTTPS headers. Compose binds local debug HTTP to loopback.
- A TLS reverse proxy must preserve the accepted public `Host` and reject unknown hosts; configure its exact peer IP/CIDR in `RESONANCE__TRUSTED_PROXY_IPS` before forwarding HTTPS headers.
