---
status: completed
approved: true
iterations: 0
branch: spec/embedding-profile-configuration
base_branch: main
base_commit: 3f39013b3a582e8d0e9f19e0d5f6af8a2b1ee998
prd: docs/prds/11-embedding-profile-configuration.md
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [cleanup, embeddings, navidrome]
---

# Proof-of-Concept Cleanup Implementation Plan

## Summary

**Goal:** Make embedding selection environment-driven and catalog-backed, and remove superseded local-file/LRC ingestion, legacy file collection search, and M3U file creation.
**Architecture:** Package a profile YAML catalog; resolve profile IDs through shared application configuration. Keep OpenAI-compatible and Ollama transports mapped by the catalog. Preserve Navidrome application operations and shared timestamp chunking.
**Tech Stack:** Python 3.14, Pydantic Settings, YAML, OpenAI SDK, httpx, FastAPI, Qdrant.

## Scope

### In Scope

- Profile catalog and `.env` configuration for active profile, service URL, and optional API key.
- Profile resolution in CLI, FastAPI ingestion, and collection-driven search.
- Remove the legacy filesystem scanner, raw LRC parser/visualizer, file-payload search path, and local M3U route.
- Preserve Navidrome-native library, ingest, search, and private playlist behavior.
- Preserve `LrcLine`, `LrcChunk`, gap chunking, and literal section-tag chunking.
- Remove stale docs, runtime registrations, dependencies, and tests exclusive to removed features.

### Out of Scope

- UI for settings, profile switching, or local model lifecycle management.
- Running/restarting TEI or Ollama, hosted credentials setup, reindexing, collection renames, or vector changes.
- Adding new profile models beyond existing, valid profile definitions.
- Automatically interpreting section metadata that Navidrome does not return.

## Prerequisites

- Current Navidrome application paths are on branch `main` at `3f39013`.
- User explicitly approved removal of local-file/LRC paths and M3U file creation.
- Existing local, ignored `.env` and Qdrant data must not be printed, staged, or modified.

## Context for Implementer

- **Patterns:** `src/resonance/config.py` uses nested Pydantic settings; `src/resonance/embedders/__init__.py` owns embedder resolution/cache; API routes call `application.*` functions.
- **Conventions:** Preserve Navidrome `config_name` profile IDs in Qdrant metadata where possible. Errors use `ApplicationError`/`fail`. Never include secrets in profile metadata or logs.
- **Key files:** `src/resonance/navidrome.py` yields timestamped `LrcLine`s; `src/resonance/application/ingest.py` calls `chunk_song_data`; `src/resonance/application/indexing.py` stores profile provenance; `src/resonance/routes/navidrome.py` is the supported playlist endpoint.
- **Gotchas:** TEI serves its configured startup model; profile selection validates the intended model but cannot switch a running TEI model. Protocol is catalog data, not inferred from the host name. Native search validates source binding and profile metadata.
- **Chunking:** Navidrome `structuredLyrics` is converted from `start` and `value`; gap splitting is active. Tag splitting only activates if markers literally occur in line text. Keep both algorithms and do not promise server-provided section labels.
- **Artifact directory:** `/tmp/resonance-poc-cleanup-20261025`
- **Test framework constraints:** Pytest exists. The agent did not add or run tests; the user later reported `86 passed in 4.47s`. Update/remove stale test code only where required to reflect explicitly removed behavior.
- **Review approach:** Multi-agent delegation is disabled for this turn. The plan and final diff received separate manual requirement-compliance and code-quality passes; these are not independent reviews.

## Runtime Environment

- **Start command:** No runtime deployment required for this configuration/refactor task.
- **Ports:** None required.
- **Health check:** Not applicable; verify route registration and CLI argument/config resolution by static inspection.
- **Restart procedure:** Not applicable. User will select/restart embedding service separately.
- **Code identity:** Source checkout and package import paths are the target; do not connect to live Navidrome, embedding, or Qdrant services.

## Feature Inventory

| Old file                                             | Function, class, route, or behavior                           | New location                                                 | Task or agreed removal      |
| ---------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------ | --------------------------- |
| `src/resonance/config.py`                            | Named YAML provider loader and provider config models         | Packaged profile catalog + runtime settings                  | Task 1                      |
| `src/resonance/embedders/__init__.py`                | Filename-based provider factory                               | Profile ID resolver using catalog                            | Task 1                      |
| `src/resonance/ingest.py`, `src/resonance/search.py` | `--provider` filename selection                               | `--profile` plus deprecated alias                            | Task 1                      |
| `src/resonance/routes/ingest.py`                     | Required request `provider` YAML stem                         | Optional profile override/configured default                 | Task 1                      |
| `src/resonance/application/search.py`                | Search path for file-based/legacy collections and file fields | Navidrome-native search only                                 | Task 2                      |
| `src/resonance/scanner.py`                           | Audio discovery, tag metadata, embedded and sidecar lyrics    | None                                                         | Remove in Task 2            |
| `src/resonance/parser.py`                            | Raw LRC file/text parsing                                     | Navidrome structured lyrics parser remains in `navidrome.py` | Remove in Task 2            |
| `src/resonance/models.py`                            | `SongData` and filesystem fields                              | Keep `Track`, `LrcLine`, `LrcChunk`                          | Remove `SongData` in Task 2 |
| `src/resonance/chunks.py`                            | `resonance-chunks` raw-LRC viewer                             | None                                                         | Remove in Task 2            |
| `src/resonance/routes/playlists.py`                  | `POST /api/playlists` local M3U writer                        | `/api/navidrome/playlists` remains                           | Remove in Task 2            |
| `src/resonance/application/search.py`                | Legacy `filename`, `audio_path`, LRC-source fields            | Navidrome result fields only                                 | Remove in Task 2            |
| `pyproject.toml`                                     | `mutagen`, `resonance-chunks` entry point                     | None                                                         | Remove in Task 2            |
| README/CLAUDE/PRD-09                                 | Claims that file/LRC/M3U paths remain supported               | Navidrome-only supported path docs                           | Update in Task 3            |
| Scanner/model/M3U tests and legacy route fixtures    | Exclusive coverage of removed features                        | None; remove/update stale assertions                         | Remove/update in Task 3     |

## Progress Tracking

- [x] Task 1: Replace per-user embedding YAML configs with bundled profile catalog and `.env` selection.
- [x] Task 2: Remove local-file/LRC ingestion and legacy collection search; preserve Navidrome chunking/search.
- [x] Task 3: Remove local M3U route and clean registrations, dependencies, docs, and obsolete test code.

**Total Tasks:** 3 | **Completed:** 3 | **Remaining:** 0

## Implementation Tasks

### Task 1: Catalog-backed embedding profile configuration

**Objective:** Resolve profile IDs from a packaged YAML catalog and use `.env` for active profile, base URL, and optional API key.

**Dependencies:** None

**Files:**

- Create: `src/resonance/data/embedding_profiles.yaml`
- Modify: `src/resonance/config.py`, `src/resonance/embedders/__init__.py`, `src/resonance/embedders/openai.py`, `src/resonance/embedders/ollama.py`, `src/resonance/ingest.py`, `src/resonance/search.py`, `src/resonance/routes/ingest.py`, `src/resonance/routes/search.py`, `src/resonance/routes/config.py`, `.env.example`, `README.md`, `docker-compose.yml`
- Remove: `config/*.yaml` provider profiles/examples after catalog is complete

**Key Decisions / Notes:**

- Catalog fields: stable ID, `model_id`, dimensions, and transport (`openai-compatible` or `ollama`). Endpoint and API key remain runtime values.
- Env names: `RESONANCE__EMBEDDING__PROFILE`, `RESONANCE__EMBEDDING__BASE_URL`, `RESONANCE__EMBEDDING__API_KEY`.
- `--profile` becomes canonical; retain `--provider` CLI/API compatibility aliases where low-cost. Missing profile uses configured default. Collection search uses stored profile ID.
- TEI/OpenAI-compatible profiles must match the model loaded at the service endpoint. Keep endpoint secrets out of Qdrant and logs.
- Keep existing supported catalog IDs stable to preserve Navidrome-native collection search.

**Definition of Done:**

- [x] Profile lookup/resolution works without `config/` or `~/.config/resonance`.
- [x] Unknown profile errors list valid stable IDs before Qdrant mutation.
- [x] Ingest and search resolve the same profile, protocol, model, dimensions, and runtime URL.
- [x] `.env.example` and README document the active profile and URL; secret values remain redacted.
- [x] Packaged YAML is explicitly included by Hatchling wheel configuration.

**Verify:**

- `uv run ruff check src/` — no lint errors.
- `uv run ruff format --check src/` — formatting passes.
- `uv run ty check src/` — type check passes.
- Inspect built package contents only if build is available without installing dependencies.

### Task 2: Remove superseded local file/LRC implementation

**Objective:** Remove filesystem discovery and old file-based search compatibility while retaining the Navidrome lyric path and shared chunker.

**Dependencies:** None

**Files:**

- Modify: `src/resonance/models.py`, `src/resonance/application/search.py`, `src/resonance/application/indexing.py`, `src/resonance/routes/search.py`, `ui/index.html`
- Remove: `src/resonance/scanner.py`, `src/resonance/parser.py`, `src/resonance/chunks.py`
- Preserve: `src/resonance/chunker.py`, `LrcLine`, `LrcChunk`, Navidrome lyric parsing and track models

**Key Decisions / Notes:**

- Delete `SongData`, filename/audio path result fields, and legacy collection search branch.
- Collections without current Navidrome metadata fail clearly with `collection_incompatible` and a reingest instruction.
- Keep native Navidrome identity, payload, source binding, completeness, and vector-profile checks.
- No behavior change to gap or literal tag chunk algorithms.

**Definition of Done:**

- [x] No runtime imports or entry points reference scanner/parser/raw-LRC files.
- [x] `/api/search` and CLI search require supported Navidrome collection metadata.
- [x] Search results and UI no longer expose filename/audio-path fields.
- [x] Navidrome ingest still calls shared `chunk_song_data` on timestamped API lines.

**Verify:**

- `rg` over `src/`, `ui/`, and `pyproject.toml` shows no scanner/parser/raw-LRC runtime references.
- `uv run ruff check src/` and `uv run ty check src/` pass.

### Task 3: Remove M3U writer and stale references

**Objective:** Remove local M3U creation while preserving Navidrome playlist creation and operation status.

**Dependencies:** Task 2

**Files:**

- Modify: `src/resonance/app.py`, `pyproject.toml`, `README.md`, `CLAUDE.md`, `docs/prds/04-jellyfin-plugin.md`, `docs/prds/09-navidrome-semantic-playlists.md`, `tests/test_routes.py`, `tests/test_indexing.py`, and test files referencing removed classes/routes
- Remove: `src/resonance/routes/playlists.py`, `tests/test_playlists.py`, `tests/test_scanner.py`, `tests/test_models.py` if wholly exclusive to removed types; remove `mutagen` and `resonance-chunks` registration

**Key Decisions / Notes:**

- Keep `src/resonance/playlists.py` and `src/resonance/routes/navidrome.py`; these implement Navidrome playlist operations, not M3U.
- Remove only tests exclusive to removed features; update mixed route/indexing tests by deleting legacy-only cases/fixtures.
- Do not delete previously generated M3U files from user storage.
- Update PRD-09 current-state language and feature-scope references that say M3U/raw-LRC paths remain.

**Definition of Done:**

- [x] App no longer registers `/api/playlists`; `/api/navidrome/playlists` remains registered.
- [x] `resonance-playlist` remains available; `resonance-chunks` is removed.
- [x] No current product docs or dependencies claim filesystem scanning, raw-LRC tooling, or local M3U creation is supported.
- [x] User-created M3U files and local ignored memory deletions are untouched.

**Verify:**

- `rg` over source, docs, pyproject, Compose, and README finds no active references to removed commands/routes/dependency.
- `uv run ruff check src/`, `uv run ruff format --check src/`, and `uv run ty check src/` pass.
- User ran pytest and reported 86 passing tests; the agent did not rerun the suite.

## Testing Strategy

- Update stale test source to remove assertions for intentionally removed APIs/models. The user reports the resulting suite passes; the agent did not execute pytest.
- Run static lint, format, and type checks as scoped above.
- Use source/call-graph inspection to establish API and CLI wiring; no live Navidrome, embedding, or Qdrant calls.
- No UI end-to-end flow is added; confirm frontend search consumes only Navidrome result fields by source inspection.

## Risks and Mitigations

| Risk                                                                 | Likelihood | Impact | Concrete mitigation                                                                                  |
| -------------------------------------------------------------------- | ---------- | ------ | ---------------------------------------------------------------------------------------------------- |
| Existing native collections stop resolving profile config names      | Med        | High   | Keep current IDs and preserve the metadata key/meaning used by search.                               |
| Old file-based Qdrant collection is queried                          | Med        | Low    | Return a clear incompatible-collection response with Navidrome reingest guidance.                    |
| TEI model differs from selected catalog profile                      | Med        | High   | Check returned vector dimensions and refuse writes on mismatch; document startup model matching.     |
| Packaging omits catalog YAML                                         | Low        | High   | Add package data inclusion and inspect the built wheel contents.                                     |
| M3U route removal accidentally removes Navidrome playlist operations | Low        | High   | Keep separate router and CLI registrations; confirm route map by source inspection.                  |
| Section tags were assumed to arrive structurally from Navidrome      | Med        | Med    | Preserve existing literal-marker detection but document that no separate section metadata is mapped. |

## Removes

- `LibraryScanner`, raw LRC parser functions, `resonance-chunks`, `SongData`, file-based legacy search, `/api/playlists` local M3U writer, `mutagen` dependency, and exclusive tests.

### Removes (verify)

- `filename` and `audio_path` fields in `SearchResult`/UI and historical collection payload compatibility; confirm no Navidrome code depends on them.
- `lyrics_source` values used only by legacy file payloads; retain Navidrome-native provenance.

## ADR Reference

No ADR needed: this reduces speculative/obsolete interfaces and keeps the established Navidrome application boundary.

## Open Questions

- None. Keep only catalog entries with explicit, validated dimensions; do not advertise a profile with guessed dimensions.

### Deferred Ideas

- Settings UI, model-service lifecycle management, model switching without restart, section metadata beyond lyric text, Navidrome library refresh, and any newly supported model families.

## Verification Record

- Ruff lint: passed (`.venv/bin/ruff check src/`).
- Ruff formatting: passed (`.venv/bin/ruff format --check src/`).
- `ty` type check: passed (`.venv/bin/ty check src/`).
- `git diff --check`: passed.
- User-reported pytest: `86 passed in 4.47s`. The agent did not run pytest. Existing obsolete test cases/files were removed or updated to match deleted features.
- Wheel build: not run. Hatchling is not installed in the local virtualenv, and `uv run` attempted to fetch build requirements while network access was unavailable. The wheel force-include mapping is present but archive inclusion was not runtime-verified.
- Live API/E2E: not run; no Navidrome, embedding, or Qdrant calls were made.
- Manual requirement and code-quality review completed against the final diff. These passes were not independent.
