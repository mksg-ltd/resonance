# Resonance Development Guide

Instructions for contributors and coding agents working in this repository.

## Product

Resonance is a self-hosted semantic discovery service for a Navidrome music library.
It retrieves metadata and structured lyrics through Navidrome APIs, chunks synced
lyrics, embeds sections, and stores them in Qdrant. Users search by meaning, review
lyric excerpts, and explicitly save verified private playlists. Resonance does not
play audio.

The main pipeline is Navidrome → normalized track and lyrics → chunking → embedding
→ Qdrant → semantic search → user-reviewed Navidrome playlist.

## Current Release Status

Resonance is in v1 preparation and is **not yet release-ready**. The README and
[roadmap](docs/roadmap.md) are the public status sources of truth.

- Implemented: Navidrome-backed indexing and semantic search; authenticated Vue
  search, review, and playlist creation; admin collection setup; background ingestion
  progress with cooperative stop/resume; authenticated FastMCP transport scaffold.
- Acceptance still needed: real-library search quality, ingestion UI progress/stop/
  resume, and private playlist behavior with a regular non-admin account.
- Not implemented: user-facing MCP tools, full per-library refresh/reconciliation,
  playback, Jellyfin integration, and seed/theme playlist generation.
- Open-source readiness: PRD-10 is scoped and in progress. The repository includes the
  AGPL-3.0-only license text and package metadata records the same identifier. Final
  distribution inventory and other readiness gates remain outstanding.

The full repository, including `docs/prds/`, `docs/plans/`, and historical
`docs/superpowers/` records, is intended to be public. The Docker image deliberately
packages runtime code/assets rather than the project documentation.

## Architecture and Stack

- FastAPI + Uvicorn expose the HTTP API under `/api`; the Vue app is served at `/`.
- Transport-independent operations live in `src/resonance/application/` and are
  called by CLI and FastAPI adapters. Do not put application policy in route or CLI
  modules.
- Navidrome is the identity, library, track, and lyrics source. No music filesystem
  mount, local lyrics scan, or M3U creation path is supported.
- Qdrant stores indexed lyric sections and collection metadata. SQLite stores only
  playlist-save operation records; it is not a track mapping database.
- Embedding profiles ship in `src/resonance/data/embedding_profiles.yaml`. Endpoint
  URLs and credentials come from environment settings.
- Vue 3/Vite is built into the Python image. `/ui` is a separate operator PoC.
- FastMCP is mounted at `/mcp/`, currently with no user-facing tools.
- Docker Compose is the sole Compose file. Persistent local artifacts live under
  ignored `data/` subdirectories. Do not add production data or model caches to Git.

## Authentication and Data Boundaries

- Users authenticate with their own Navidrome credentials. Resonance keeps bounded
  sessions and credentials in process memory and issues process-signed tokens. A
  restart clears sessions; users must sign in again.
- The exact `RESONANCE_ADMIN_USER` username receives admin capabilities; there is no
  Resonance role database.
- Collection access is filtered using the caller's current Navidrome library access.
  Ingestion and collection deletion require the configured admin username.
- Keep passwords, API keys, tokens, full lyrics, and private library data out of logs,
  fixtures, screenshots, and public documentation. Never print or parse `.env` from
  Make targets.
- Hosted embedding endpoints receive lyric text and search queries. Do not claim all
  deployments are private/offline; describe the selected provider's data flow.
- Compose binds Resonance, Qdrant, and TEI host ports to loopback. Remote use requires
  HTTPS and exact trusted TLS-proxy addresses. Preserve the accepted public `Host`
  and reject unknown hosts at the reverse proxy.

## Persistent State

`data/` is ignored by Git and Docker build context. Current subdirectories are:

- `data/qdrant_storage/` — Qdrant collections and indexed lyric sections.
- `data/tei_cache/` — locally downloaded TEI model data.
- `data/resonance/` — Compose playlist-operation journal at `/app/state`.
- `data/local/` — host-run CLI/API playlist-operation journal.

The first Compose startup after the bind-mount migration imports the former
`playlist_state` named-volume journal into `data/resonance/`; preserve that volume
until the import is confirmed. Do not delete either journal casually: losing it removes
safe retry protection for uncertain playlist creation outcomes. Back up `data/` and
the legacy volume during the transition.

## Commands

- `make run` — start Qdrant/TEI dependencies and the local debug API (docs at `/docs`).
- `make ui` — start Vite at `127.0.0.1:5173`; it proxies `/api` to FastAPI.
- `make prod` — build and start the Compose stack. It recreates services; do not run
  during an active ingestion job.
- `make prod-down` — stop the full Compose stack without deleting persistent data.
- `make test` — run pytest.
- `make lint` — Ruff check and format check.
- `make install` — `uv sync` and pre-commit hooks.
- `make build` — build the Docker image locally.
- `uv run pytest -v` — verbose test output.
- `uv run ruff check src/ --fix` — auto-fix lint issues.

## Code Quality and Conventions

- Python 3.14+, `uv`, 120-character lines, double quotes, type hints.
- Ruff lint/format and `ty` type checks; pytest with mocked external APIs and local
  in-memory Qdrant for unit/integration coverage.
- Conventional commits: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`.
- Dataclasses hold domain models in `models.py`; environment settings are loaded once
  and stored in `app.state`.
- Preserve idempotent playlist saves and never automatically retry a create request
  whose Navidrome outcome is unknown. Use the same operation ID and exact request.
- Ingestion never deletes or recreates a collection automatically. Identical partial
  writes can resume. Changed lyrics require a new collection until refresh exists.
- Malformed per-track lyric content may be skipped and counted; failure to enumerate
  the Navidrome library remains a failed ingestion.

## Repository Map

```text
src/resonance/
├── application/       # Shared indexing, ingestion, search, library, and save policy
├── navidrome.py       # Subsonic API, paging, lyrics, and playlist verification
├── state.py           # SQLite playlist-save operation journal
├── models.py          # Domain models and server response DTOs
├── config.py          # Pydantic environment settings
├── data/              # Bundled embedding-profile catalog
├── embedders/         # OpenAI-compatible/TEI and Ollama clients
├── routes/            # Thin HTTP adapters and auth dependencies
├── mcp/               # FastMCP transport scaffold
└── chunker.py         # Tags, time gaps, and minimum-line lyric chunking
```

Use `README.md` for operator setup and API behavior, `docs/README.md` for product
history/document navigation, `docs/prds/` for product requirements, and `docs/plans/`
for implementation records. Treat dated plans and `docs/superpowers/` as historical
records; verify current behavior against source code and the roadmap.
