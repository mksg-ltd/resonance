# FastAPI Service & Configuration Implementation Plan

Created: 2026-03-19
Status: PENDING
Approved: Yes
Iterations: 0
Branch: spec/fastapi-service
PRD: docs/prds/06-fastapi-service.md

> **Status Lifecycle:** PENDING → COMPLETE → VERIFIED
> **Iterations:** Tracks implement→verify cycles (incremented by verify phase)
>
> - PENDING: Initial state, awaiting implementation
> - COMPLETE: All tasks implemented
> - VERIFIED: All checks passed
>
> **Branch:** All spec work happens on a dedicated `spec/fastapi-service` branch, created at implementation start

## Summary

**Goal:** Restructure lrc-match from CLI-only scripts into a FastAPI service with YAML-driven config (pydantic-settings), embedding provider abstraction, and API endpoints for search, ingestion, config, and health.

**Architecture:** API-first design — FastAPI serves all functionality. Swagger UI is the dev interface. Jellyfin plugin, CLI, and any future frontend are all API clients. Config is YAML-first with env var overrides. Provider-specific settings live in `conf.d/` files.

**Tech Stack:** FastAPI, pydantic-settings (YAML), uvicorn, Qdrant, OpenAI/Ollama embeddings, pytest, ruff, ty, pre-commit, Make.

## Scope

### In Scope

- Project plumbing: pre-commit hooks, Makefile, CLAUDE.md, pyproject.toml tool config
- Config layer: pydantic-settings with YAML loading + env var overrides
- Provider-specific config in `conf.d/` directory
- Embedding provider abstraction: Protocol + OpenAI implementation + Ollama stub
- FastAPI app with routes: search, ingest, config (read-only), collections, health
- Swagger UI in debug mode
- Collection metadata: store provider/model/dimensions per collection in Qdrant
- Refactor existing ingest.py and search.py to use config + provider layer
- Docker multi-stage build + updated compose
- Tests for config, embedders, routes

### Out of Scope

- Standalone web frontend (Swagger UI is sufficient)
- Auth/roles (single-user, deferred)
- Playlist persistence (Jellyfin plugin concern)
- Sentence Transformers embedder (Ollama stub is enough for now)
- Jellyfin API integration (separate PRD-04/05)
- music_dir configuration (hardcoded to `/data/media/music/english`)

## Prerequisites

- Python 3.14+ with uv installed
- Docker for Qdrant
- OpenAI API key (for OpenAI provider)

## Context for Implementer

- **Patterns to follow:** Passage project's pre-commit, Makefile, pyproject.toml tooling config. Adapted for FastAPI (no Django-specific hooks like djlint).
- **Conventions:** 120 char lines, double quotes, type hints on all functions, conventional commits. No services layer — route handlers contain business logic directly. Package splits (e.g., `embedders/`, `routes/`) use `__init__.py` re-exports.
- **Key files to read first:**
  - `src/lrc_match/ingest.py` — current ingestion pipeline, OpenAI + Qdrant usage, hardcoded values
  - `src/lrc_match/search.py` — current search, same hardcoded patterns
  - `src/lrc_match/models.py` — domain models (LrcLine, LrcChunk, LrcLyric)
  - `src/lrc_match/chunker.py` — chunking strategies (tag-based and gap-based)
  - `src/lrc_match/parser.py` — LRC file parsing
- **Gotchas:**
  - Current code uses `OPEN_AI_KEY` env var (not `OPENAI_API_KEY`) — normalize during refactor
  - Current `DATA_DIR = Path("data")` is hardcoded — will become `/data/media/music/english`
  - `ingest.py` recreates collection on every run (deletes existing data) — keep this behavior but add `force` flag
  - `search.py` duplicates MODELS dict — extract to shared config
  - Qdrant URL hardcoded to `http://localhost:6333` in both files
- **Domain context:** LRC files are timestamped lyrics. They get parsed → chunked into sections → embedded → stored as vectors in Qdrant. Search embeds a query and finds similar chunks via cosine similarity.

## Feature Inventory — Files Being Refactored

| Old File | Functions/Classes | Mapped to Task |
|----------|-------------------|----------------|
| `src/lrc_match/ingest.py` | `embed_texts()`, `setup_collection()`, `main()`, `MODELS` dict, `DATA_DIR`, OpenAI/Qdrant client creation | Task 3 (embedder extraction), Task 5 (ingest route) |
| `src/lrc_match/search.py` | `search()`, `main()`, `MODELS` dict, OpenAI/Qdrant client creation | Task 3 (embedder extraction), Task 5 (search route) |
| `src/lrc_match/models.py` | `LrcLine`, `LrcChunk`, `LrcLyric` | Unchanged — no task needed |
| `src/lrc_match/parser.py` | `parse_lrc_lines()`, `TIMESTAMP_RE` | Unchanged — no task needed |
| `src/lrc_match/chunker.py` | `chunk_song()`, `chunk_by_tags()`, `chunk_by_gaps()`, `has_section_tags()` | Unchanged — no task needed |

### Feature Mapping Verification

- [x] All old files listed above
- [x] All functions/classes identified
- [x] Every feature has a task number or "Unchanged"
- [x] No features accidentally omitted

## Progress Tracking

**MANDATORY: Update this checklist as tasks complete. Change `[ ]` to `[x]`.**

- [ ] Task 1: Project plumbing (pre-commit, Makefile, CLAUDE.md, pyproject.toml)
- [ ] Task 2: Config layer (pydantic-settings + YAML)
- [ ] Task 3: Embedding provider abstraction
- [ ] Task 4: FastAPI app skeleton + health endpoint
- [ ] Task 5: Search + ingest + config + collections routes
- [ ] Task 6: Docker multi-stage build + updated compose

**Total Tasks:** 6 | **Completed:** 0 | **Remaining:** 6

## Implementation Tasks

### Task 1: Project Plumbing

**Objective:** Set up pre-commit hooks, Makefile, CLAUDE.md, and update pyproject.toml with ruff/ty/pytest config and FastAPI dependencies. This establishes the dev workflow before any code changes.

**Dependencies:** None

**Files:**

- Create: `.pre-commit-config.yaml`
- Create: `Makefile`
- Create: `CLAUDE.md`
- Modify: `pyproject.toml`

**Key Decisions / Notes:**

- Pre-commit config adapted from passage (`.pre-commit-config.yaml`): ruff lint+format, ty type checker, pre-commit-hooks (trailing whitespace, EOF, YAML/JSON/TOML checks, merge conflict, case conflict, large files, debug statements, mixed line endings), prettier (JSON/MD/YAML), conventional commits. No djlint (no templates).
- Ruff config from passage's `pyproject.toml`: 120 chars, double quotes, comprehensive rule set. Remove Django-specific rules (DJ). Add per-file-ignores for tests.
- ty config from passage: relaxed rules for false positives.
- pytest config: no `DJANGO_SETTINGS_MODULE`, just `python_files = ["test_*.py"]`.
- Makefile targets: `help`, `run` (uvicorn), `test` (pytest), `lint` (ruff), `install` (uv sync + pre-commit install), `build` (docker build).
- CLAUDE.md: project overview, stack, conventions, commands, gotchas. Follow passage's CLAUDE.md structure.
- Add FastAPI dependencies to pyproject.toml: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `pyyaml`. Add dev deps: `ruff`, `ty`, `pytest`, `httpx` (for FastAPI test client), `pre-commit`.
- Remove `python-dotenv` dependency (replaced by pydantic-settings env loading).
- Keep `openai` and `qdrant-client` deps.
- Update `[project.scripts]` to add `lrc-server = "lrc_match.app:cli"` alongside existing CLI scripts.
- The `.venv` lives at project root (not in `src/` like passage) since there's no separate `src/` package dir issue.
- ty hook: `entry: bash -c 'uv run ty check src/'` (adjust path since .venv at root).
- Ruff files filter: `files: ^src/.*\.py$` to match existing structure.

**Definition of Done:**

- [ ] `pre-commit install` succeeds and hooks run on commit
- [ ] `make help` lists all available targets
- [ ] `make lint` runs ruff without errors on existing code
- [ ] `make test` runs pytest (may have no tests yet, that's OK)
- [ ] CLAUDE.md accurately describes the project

**Verify:**

- `uv sync && uv run pre-commit install && uv run pre-commit install --hook-type commit-msg`
- `make help`
- `make lint`
- `make test`

---

### Task 2: Config Layer

**Objective:** Create pydantic-settings config model that loads from YAML + env vars. Provider-specific config in `conf.d/` directory. Create `config.yaml.example`.

**Dependencies:** Task 1

**Files:**

- Create: `src/lrc_match/config.py`
- Create: `config.yaml.example`
- Create: `conf.d/openai.yaml.example`
- Create: `conf.d/ollama.yaml.example`
- Create: `tests/test_config.py`

**Key Decisions / Notes:**

- pydantic-settings does NOT natively support `conf.d/` directory loading. Keep it simple: the main `Settings` class loads `config.yaml`. A separate `load_provider_config()` function reads `conf.d/{provider}.yaml` if it exists, returning a provider-specific pydantic model. This is minimal glue, not a framework.
- Config hierarchy: code defaults → config.yaml → env vars. No CLI flags (config is for the service, CLI tools use argparse for their own args).
- Env var pattern: `LRC_MATCH__QDRANT__URL` overrides `qdrant.url` (using `env_nested_delimiter="__"` and `env_prefix="LRC_MATCH__"`).
- Config sections: `embedding` (just `provider` field), `qdrant` (url, collection, api_key), `chunking` (gap_threshold_sec, min_chunk_lines), `jellyfin` (url, api_key — both optional/null), `server` (host, port, debug).
- Provider configs: `OpenAIProviderConfig` (api_key, model), `OllamaProviderConfig` (base_url, model). Loaded from `conf.d/openai.yaml` or `conf.d/ollama.yaml` based on `embedding.provider`.
- `api_key` fields use `SecretStr` for redaction in logs/API responses.
- YAML loading: use `pyyaml` to load the file, then pass the dict to Settings. pydantic-settings-yaml exists but adds a dependency for minimal gain — just `yaml.safe_load()` + `Settings(**data)`.
- Config file discovery: check `./config.yaml` first, then `~/.config/lrc-match/config.yaml`. Env var `LRC_MATCH_CONFIG` to override path.
- Env var expansion in YAML values (e.g., `api_key: ${OPENAI_API_KEY}`) — use `os.path.expandvars()` on string values before passing to pydantic. Simple, no custom parser.
- Test with tmp_path fixtures: write YAML to temp file, load config, verify values. Test env var override. Test missing config file uses defaults. Test provider config loading.

**Definition of Done:**

- [ ] `Settings` loads from YAML file with all sections validated
- [ ] Env vars override YAML values (e.g., `LRC_MATCH__QDRANT__URL`)
- [ ] Provider config loads from `conf.d/{provider}.yaml`
- [ ] Missing config file falls back to code defaults
- [ ] `config.yaml.example` documents all options with comments
- [ ] All config tests pass

**Verify:**

- `uv run pytest tests/test_config.py -v`

---

### Task 3: Embedding Provider Abstraction

**Objective:** Create `EmbeddingProvider` protocol with OpenAI implementation (extracted from current `ingest.py`) and Ollama stub. Factory function creates the right provider from config.

**Dependencies:** Task 2

**Files:**

- Create: `src/lrc_match/embedders/__init__.py`
- Create: `src/lrc_match/embedders/base.py`
- Create: `src/lrc_match/embedders/openai.py`
- Create: `src/lrc_match/embedders/ollama.py`
- Create: `tests/test_embedders.py`

**Key Decisions / Notes:**

- `EmbeddingProvider` protocol in `base.py`: `embed(texts: list[str]) -> list[list[float]]` and `dimensions` property. Also `model_name` property (for collection metadata).
- `OpenAIEmbedder` in `openai.py`: extracted from current `ingest.py:32-35`. Takes `api_key` and `model` from config. Known dimensions map: `{"text-embedding-3-small": 1536, "text-embedding-3-large": 3072}`. Batch size from config (default 64).
- `OllamaEmbedder` in `ollama.py`: stub implementation using `httpx` to call Ollama's `/api/embed` endpoint. Takes `base_url` and `model` from config. Known dimensions: `{"nomic-embed-text": 768, "mxbai-embed-large": 1024}`. This is a real implementation, not a mock — but we won't test it against a running Ollama instance in CI.
- `create_embedder(settings: Settings) -> EmbeddingProvider` factory in `__init__.py`. Reads `settings.embedding.provider`, loads provider config from `conf.d/`, returns the right embedder.
- `__init__.py` re-exports: `EmbeddingProvider`, `OpenAIEmbedder`, `OllamaEmbedder`, `create_embedder`.
- Tests: mock OpenAI API response, verify `OpenAIEmbedder.embed()` returns correct shape. Test factory creates right type based on config. Test dimension auto-detection.

**Definition of Done:**

- [ ] `OpenAIEmbedder` produces embeddings (tested with mocked OpenAI API)
- [ ] `OllamaEmbedder` has working implementation (tested with mocked HTTP)
- [ ] `create_embedder()` returns correct provider based on config
- [ ] Dimensions auto-detected for known models
- [ ] All embedder tests pass

**Verify:**

- `uv run pytest tests/test_embedders.py -v`

---

### Task 4: FastAPI App Skeleton + Health Endpoint

**Objective:** Create the FastAPI application factory with lifespan management (Qdrant client + embedder initialization). Add health endpoint. Wire up Swagger UI toggle.

**Dependencies:** Task 2, Task 3

**Files:**

- Create: `src/lrc_match/app.py`
- Create: `src/lrc_match/routes/__init__.py`
- Create: `src/lrc_match/routes/health.py`
- Create: `tests/test_health.py`
- Create: `tests/conftest.py`

**Key Decisions / Notes:**

- `app.py` contains the FastAPI application factory function `create_app(settings: Settings | None = None) -> FastAPI`.
- Lifespan context manager: creates Qdrant client and embedder on startup, stores in `app.state`. Cleans up on shutdown.
- Swagger UI: enabled when `settings.server.debug` is True. Use `docs_url="/docs"` when debug, `docs_url=None` when not.
- Health endpoint at `GET /health`: checks Qdrant connectivity (`qdrant_client.get_collections()`), returns `{"status": "healthy", "qdrant": "connected", "provider": "openai"}` or appropriate error.
- `conftest.py`: shared fixtures. `test_settings` fixture returns Settings with test defaults. `test_app` fixture creates app with test settings. `test_client` fixture returns `httpx.AsyncClient` (or `TestClient` from FastAPI).
- CLI entry point: `def cli()` in `app.py` that calls `uvicorn.run()` with settings from config. This is what `lrc-server` script points to.
- All routes mounted under `/api/` prefix via APIRouter, except `/health` which is at root.

**Definition of Done:**

- [ ] `create_app()` returns a working FastAPI instance
- [ ] `GET /health` returns 200 with status JSON when Qdrant is reachable
- [ ] `GET /health` returns 503 when Qdrant is unreachable
- [ ] Swagger UI available at `/docs` when `server.debug: true`
- [ ] Swagger UI disabled when `server.debug: false`
- [ ] `make run` starts uvicorn and serves the app
- [ ] Health endpoint test passes

**Verify:**

- `uv run pytest tests/test_health.py -v`
- `make run &` then `curl http://localhost:8000/health` (manual check)

---

### Task 5: Search + Ingest + Config + Collections Routes

**Objective:** Create API routes for search, ingest, config (read-only), and collections. Refactor existing `ingest.py` and `search.py` logic to use config + embedder from app state instead of hardcoded values.

**Dependencies:** Task 4

**Files:**

- Create: `src/lrc_match/routes/search.py`
- Create: `src/lrc_match/routes/ingest.py`
- Create: `src/lrc_match/routes/config.py`
- Create: `src/lrc_match/routes/collections.py`
- Modify: `src/lrc_match/routes/__init__.py` (register all routers)
- Modify: `src/lrc_match/ingest.py` (refactor to use embedder + config, keep CLI)
- Modify: `src/lrc_match/search.py` (refactor to use embedder + config, keep CLI)
- Create: `tests/test_routes.py`

**Key Decisions / Notes:**

- **Search route** (`POST /api/search`):
  - Request body: `SearchRequest(query: str, artist: str | None = None, limit: int = 15, collection: str | None = None)`
  - If `collection` not specified, use default from config.
  - Get embedder and qdrant client from `request.app.state`.
  - Embed query, search Qdrant, return results grouped by song (deduplicate sections from same song — keep highest scoring section).
  - Response: `SearchResponse(query: str, results: list[SearchResult], total: int)` where `SearchResult` has `artist`, `title`, `score`, `section`, `position`, `total_sections`, `lyrics_preview`.

- **Ingest route** (`POST /api/ingest`):
  - Request body: `IngestRequest(force: bool = False)`
  - Reads from hardcoded `/data/media/music/english` (per PRD decision).
  - If `force=False` and collection exists with points, skip (return existing count).
  - If `force=True`, recreate collection.
  - **Collection metadata:** When creating a collection, store `{"provider": "openai", "model": "text-embedding-3-small", "dimensions": 1536}` as collection metadata via Qdrant's collection metadata field. This is the fix for the "collection doesn't know its own model" problem.
  - Use embedder from app state (not hardcoded OpenAI).
  - Response: `IngestResponse(files_processed: int, chunks_created: int, collection: str, skipped: int)`.
  - Note: This is a synchronous endpoint. For a large library it could take minutes. That's acceptable for now.

- **Config route** (`GET /api/config`):
  - Returns current config as JSON with secrets redacted (SecretStr renders as `"**********"`).
  - No `PUT` for now (restart to apply changes).

- **Collections route**:
  - `GET /api/collections` — list all collections with their metadata (provider, model, dimensions, point count).
  - `DELETE /api/collections/{name}` — drop a collection.

- **Refactor `ingest.py`:**
  - Extract the pipeline logic into a function `run_ingest(qdrant: QdrantClient, embedder: EmbeddingProvider, settings: Settings, force: bool) -> IngestResult` that both the route and CLI `main()` call.
  - CLI `main()` stays as argparse entry point but creates config + embedder first.
  - Remove hardcoded `MODELS` dict, `DATA_DIR`, direct OpenAI/Qdrant client creation.

- **Refactor `search.py`:**
  - Extract into `run_search(qdrant: QdrantClient, embedder: EmbeddingProvider, query: str, collection: str, artist: str | None, limit: int) -> list[SearchResult]` callable by both route and CLI.
  - CLI `main()` stays but uses config + embedder.
  - Remove hardcoded `MODELS` dict, direct OpenAI/Qdrant client creation.

- **Tests:** Use FastAPI TestClient. Mock Qdrant client and embedder in fixtures. Test search returns results, ingest processes files (use a small test LRC fixture), config endpoint redacts secrets, collections endpoint lists/deletes.

**Definition of Done:**

- [ ] `POST /api/search` returns ranked, deduplicated results
- [ ] `POST /api/ingest` processes LRC files and stores in Qdrant with collection metadata
- [ ] `GET /api/config` returns config with secrets redacted
- [ ] `GET /api/collections` lists collections with metadata
- [ ] `DELETE /api/collections/{name}` drops a collection
- [ ] Existing CLI tools (`lrc-ingest`, `lrc-search`) still work using the new config/embedder layer
- [ ] All route tests pass

**Verify:**

- `uv run pytest tests/test_routes.py -v`
- `uv run pytest tests/ -v` (all tests still pass)

---

### Task 6: Docker Multi-Stage Build + Updated Compose

**Objective:** Create a multi-stage Dockerfile for the FastAPI service and update docker-compose.yml to run lrc-match alongside Qdrant.

**Dependencies:** Task 4, Task 5

**Files:**

- Create: `Dockerfile`
- Create: `.dockerignore`
- Modify: `docker-compose.yml`

**Key Decisions / Notes:**

- **Dockerfile** (multi-stage, adapted from passage):
  - Stage 1 (builder): Python 3.14 slim, copy uv binary, `uv sync --no-dev --frozen`.
  - Stage 2 (runtime): Python 3.14 slim, copy venv from builder, copy src/. Non-root user.
  - Entrypoint: `uvicorn lrc_match.app:create_app --factory --host 0.0.0.0 --port 8000`.
  - No Node.js stage needed (no frontend build).

- **docker-compose.yml:**
  - Add `lrc-match` service alongside existing `qdrant` service.
  - Volume mount for `config.yaml` and `conf.d/` directory.
  - Volume mount for music library (default: `/data/media/music/english`).
  - Depends on qdrant.
  - Health check: `curl -f http://localhost:8000/health`.
  - Environment: `LRC_MATCH__SERVER__DEBUG=true` for dev.

- **.dockerignore:** `.venv`, `__pycache__`, `.git`, `qdrant_storage`, `data/`, `.pytest_cache`, `htmlcov`, `*.pyc`.

**Definition of Done:**

- [ ] `docker build` succeeds
- [ ] `docker compose up` starts both Qdrant and lrc-match
- [ ] Health check passes in compose
- [ ] Config and music directory are properly mounted

**Verify:**

- `docker build -t lrc-match:dev .`
- `docker compose up -d && sleep 5 && curl http://localhost:8000/health && docker compose down`

## Testing Strategy

- **Unit tests:** Config loading (YAML, env vars, defaults, provider config), embedder factory, dimension auto-detection.
- **Integration tests:** FastAPI routes via TestClient with mocked Qdrant client and embedder. Health endpoint with real/mocked Qdrant connectivity.
- **Manual verification:** `make run`, then Swagger UI at `localhost:8000/docs`. Test search and ingest via Swagger forms.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| pydantic-settings YAML loading requires custom glue | Med | Low | Keep it minimal: `yaml.safe_load()` → `Settings(**data)`. No framework. |
| Ingest endpoint blocks for minutes on large libraries | Med | Med | Document this. Async endpoint runs in a thread. Future: background task. |
| Collection metadata API differs across Qdrant versions | Low | Med | Use `collection_params` or payload-based metadata. Test against current Qdrant version. |
| Existing CLI tools break during refactor | Med | High | Keep CLI `main()` functions working throughout. Run both CLI and API tests. |

## ADR Reference

No ADR needed — follows existing patterns from reference projects (passage, nool), adapted for FastAPI. The API-first architecture was decided in PRD-06 through discussion.

## Open Questions

None — all resolved during PRD discussion.

### Deferred Ideas

- Sentence Transformers embedder (local HuggingFace models, no server)
- Background job runner for long ingestion runs
- Config PUT endpoint for runtime updates
- "Seed song" search (pick a song, find similar sections)
- Incremental ingestion with manifest tracking
