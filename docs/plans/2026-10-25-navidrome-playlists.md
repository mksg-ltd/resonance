---
status: verified
approved: true
iterations: 1
branch: spec/navidrome-playlists
base_branch: main
base_commit: 8c0d7754abfaf2de3c7c22020acfc197f7120f74
prd: docs/prds/09-navidrome-semantic-playlists.md
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [navidrome, ingestion, playlists]
---

# PRD-09: Staged Navidrome Backend Plan

Created: 2026-10-25
Status: Implementation complete — independent review and final verification pending
PRD: [Navidrome semantic playlists](../prds/09-navidrome-semantic-playlists.md)

## Direction and Scope

Use Navidrome as the source of library metadata, song identity, and synced lyrics.
Resonance owns lyric indexing, semantic discovery, and playlist generation. Shared
Python application operations serve CLI first, FastAPI next, and possibly FastMCP
later. Each adapter handles its transport; business logic lives behind one interface.

Single-account/library scope and moving ingestion away from music bind mounts are
confirmed. The existing code is a learning proof of concept: reuse useful chunking,
embedding, and Qdrant behavior while improving the product boundaries. Existing module
splits, filename assumptions, and CLI arguments need not constrain the new workflow.

The same flexibility applies to the embedder layout. TEI is the current deployment
direction, and its OpenAI-compatible interface already fits the existing client path.
Retain only the batch-embedding behavior and actual model/provenance needed for correct
indexing/search; the protocol class, provider factory, and file split may be simplified
when helpful. Do not turn an unrelated provider rewrite into an ingestion prerequisite.

The first milestones are read-only discovery, API-based ingestion/search, and then
verified private playlist creation from an explicit selection. Seed/theme generation,
Vue UI, FastMCP, public sharing, and general playlist updates are separate follow-ons.
Per-library refresh commands/APIs, scheduling, and full changed/deleted-song
reconciliation are also future scope. This feature only establishes their data and
repeat-safe write foundations; it does not implement the refresh workflow.

Navidrome song IDs, scoped to the configured server, replace separate recording UUIDs
and file-to-song mapping tables. SQLite remains an allowed, recommended option for a
transactional save-operation journal; search retries need no journal. It is not a
prerequisite for discovery or ingestion.

## Evidence and Current Implementation

- Existing code scans mounted audio files and reads embedded/sidecar lyrics. CLI and
  HTTP share `run_ingest`/`run_search`, but those functions currently live in routes.
- Collection names are currently supplied explicitly. Model/config metadata is stored
  in Qdrant; ingestion skips already indexed relative audio paths.
- The initial baseline has 80 passing tests with external APIs mocked, passing Ruff
  lint and `ty`, and an existing formatter issue in `parser.py`.
- A live probe verified Navidrome 0.64.2, listing of 4,187 English-library song IDs,
  sampled synced lyrics, initial private creation, and exact playlist readback. The
  user confirmed seeing the playlist and three entries. Browser playback/advancing is user-confirmed; exact client version/private UI indicator is not recorded.
  See the [validation record](2026-10-25-navidrome-validation.md).
- No production Navidrome client, application operations, ingestion migration, or save
  journal has been implemented. The protocol probe did not embed or reindex anything.
- The user has removed the music bind mount from `docker-compose.yml` and deleted
  `docker-compose.dev.yml`. Source ingestion still expects local files; it must be
  migrated before that path works again. `Makefile` still references the deleted
  development Compose file and needs corresponding command cleanup.

## Collection Identity

Each collection binds **one Navidrome instance + one library ID + one embedding profile**.

- Use configured server identity and `musicFolderId`, not a mount path or display name.
  English folder 2 is the initial tested library. Renaming the library does not change
  its identity; a server rebuild can require a new source generation/reindex.
- The embedding profile records provider, actual model/revision where available,
  dimensions, and relevant embedding settings. A mutable provider-config filename or
  equal vector dimensions alone does not establish compatible vector spaces.
- A readable name such as `home_english_bge_m3` is a label. Metadata is authoritative,
  and caller-selected names must pass the same source/model compatibility checks.
- Also record schema version, chunking/index settings, and index generation. Every
  lyric section carries source ID, folder ID, and Navidrome song ID.
- Do not append a new model's vectors or another library's songs to an incompatible
  collection. Build a separately named collection for the explicit source migration;
  keep old collections until the operator chooses to retire them.

## Incremental Ingestion Readiness — Current Foundation Only

Keep indexing state with the actual vectors in Qdrant. No SQLite track ledger or
separate metadata collection is needed for the first version. SQLite remains available
for playlist-save operations and, later, ingestion job coordination if justified.

The section payload contract must include:

| Field                                | Purpose                                                                      |
| ------------------------------------ | ---------------------------------------------------------------------------- |
| `source_id`, `library_id`, `song_id` | Stable source identity within this collection's scope                        |
| `lyrics_hash`                        | Detect changed selected lyric content/timing using versioned canonical input |
| `index_fingerprint`                  | Identify effective model, normalization, and chunking configuration          |
| `position`, `total_sections`         | Identify a section and verify that the expected complete set exists          |
| `indexed_at`                         | UTC audit time; not evidence of source modification or scan completion       |

Derive section point IDs deterministically from scoped song identity and section key/
position in a Qdrant-supported ID format. These are storage keys, not new recording
identities. Retrying unchanged input reuses the same IDs. Keep a versioned canonical
input/hash function so selection, timing, normalization, or chunking changes cannot
silently reuse incompatible index state. Metadata-only changes can later update
payloads without necessarily recomputing vectors.

Expose a small index-state lookup/helper behind the shared ingestion operation.
Initially derive completion from the expected section set and matching fingerprints;
one existing section or an `ingested=true` flag is insufficient after partial failure.
If a completion marker is used later, write it only after all sections are acknowledged;
do not claim atomicity across multiple writes. Missing-lyrics tracks have no successful
vector completion state and must remain eligible for a later refresh.

The future refresh feature can enumerate library IDs, add unindexed songs, and skip
unchanged complete songs. It must separately specify changed-song replacement and old-
section cleanup, metadata updates, deletion policy, checkpoints, and concurrent runs.
Never prune based on a partial scan. Do not depend on an unverified server delta feed.
These future orchestration details must not become prerequisites for this feature.

References: [Qdrant payloads](https://qdrant.tech/documentation/concepts/payload/) and
[stable-ID upserts](https://api.qdrant.tech/api-reference/points/upsert-points).

## Shared Interface and File Boundaries

| Operation            | Input                                                                    | Result                                              |
| -------------------- | ------------------------------------------------------------------------ | --------------------------------------------------- |
| `inspect_connection` | Configured server and trusted caller                                     | Server/version/capabilities                         |
| `list_tracks`        | Configured library and paging                                            | Song IDs and metadata                               |
| `ingest_library`     | Source/library, embedding profile, index options                         | Counts, lyric outcomes, collection identity         |
| `validate_selection` | Ordered song IDs and trusted caller                                      | Current scope/accessibility or actionable failures  |
| `create_playlist`    | Operation key, name, approved IDs, duplicate-name acknowledgment, caller | Verified, failed, or unresolved operation           |
| `get_operation`      | Operation key and trusted caller                                         | Persisted outcome; known-ID readback reconciliation |

Use typed DTOs/errors without FastAPI, argparse, or MCP dependencies. Trusted caller
context comes from adapter authentication/configuration, never an arbitrary account
field. Application policy enforces source scope, authorization, ordering, and retries.

Suggested boundaries, to refine during implementation:

- `application/ingest.py` and `application/playlists.py`: shared orchestration/policy.
- `navidrome/`: HTTP, authentication, response envelopes, metadata/lyric translation.
- `models.py`: filesystem-independent domain input and result data.
- `state.py`: transactional save journal, optionally SQLite; no file mapping tables.
- Existing CLI entry points and HTTP routes: thin adapters; preserve M3U as a separate
  legacy explicit-path operation rather than a native-playlist dependency.

### Domain Model Changes

Normalize the subset of Navidrome responses we use into our own domain objects; do
not mirror every API response field or pass raw response dictionaries through the
whole pipeline. The API adapter handles timestamp units, offsets, and lyric variants.

| Current concept                                  | Navidrome-native concept                                                                  |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| `SongData` requiring `audio_path` and `filename` | Track metadata, source/library/song IDs, and lyric lines; no required filesystem path     |
| `LrcLine` / `LrcChunk`                           | Generic lyric lines/sections with normalized timestamps; existing behavior remains useful |
| `LibraryScanner` plus mutagen/sidecars           | Paged API track discovery and structured-lyric retrieval                                  |
| `data_dir` / `--data-dir`                        | Explicit Navidrome library ID and embedding/index configuration                           |
| Path-based incremental ingestion                 | Song-ID/content-based index state                                                         |
| `files_processed`                                | Track-oriented ingestion counts, including missing/unsynced lyric outcomes                |
| Search results keyed by artist/title             | Results carrying source/library/song IDs, metadata, and lyric evidence                    |

Names such as `Track`, `LyricLine`, and `LyricSection` are options, not an additional
framework. Keep the existing chunking/vector behavior where useful. Treat lyrics as
Navidrome-supplied; do not invent embedded-versus-sidecar provenance that the API does
not report. Any server path is optional metadata, not a local path to open.

## Progress Tracking

- [x] Task 1: Reviewed contracts, migration inventory, and ADR.
- [x] Task 2: Domain models and read-only Navidrome adapter/CLI.
- [x] Task 3: Shared Navidrome ingestion/search and mount-free runtime.
- [x] Task 4: SQLite save journal and verified private creation.
- [x] Task 5: Thin save adapters, regression/runtime verification, acceptance evidence.

**Total Tasks:** 6 | **Completed:** 6 | **Remaining:** 0

## Implementation Tasks

### Task 1 — Settle Contracts and Record the Protocol Spike

**Objective:** Reconcile the existing conversational plan with the approved source
migration and make the implementation contracts reviewable. No dependencies.

**Files:** this plan; `docs/adr/001-navidrome-application-boundary.md`;
`docs/prds/09-navidrome-semantic-playlists.md`.

- [x] Confirm single-account/library deployment and API-based library source.
- [x] Use scoped Navidrome song IDs directly; remove the extra recording UUID design.
- [x] Verify authentication, form POST, listing, structured lyrics, and private creation.
- [x] Verify playlist ID/owner/name/privacy/count/order; user confirms client visibility.
- [x] Finalize the concrete contracts, inventory and risk table below; complete both
      independent plan reviews and record their findings before implementation.
- [x] Record the architecture decision and planning commit on the spec branch.

**Definition of Done:** Functional frontmatter and task counts validate; every old
capability maps to a destination or approved source-migration change; plan-verifier and
plan-challenger reviews have no unresolved must-fix/should-fix findings. Manual audible
playback is a later acceptance gate, not a prerequisite for this planning task.

**Verify:** parse YAML with `.venv/bin/python`; validate relative links; review saved
JSON findings; `git diff --check` and Markdown formatting checks pass.

### Task 2 — Domain Models and Read-Only Navidrome Adapter

**Files:** Create `src/resonance/errors.py`, `src/resonance/navidrome.py`,
`src/resonance/application/__init__.py`, `src/resonance/application/library.py`,
`src/resonance/library.py`, and `tests/test_navidrome.py`; modify `models.py`,
`config.py`, `pyproject.toml`, `uv.lock`, and `tests/test_config.py`.

**Definition of Done:** `resonance-library inspect/libraries/tracks/lyrics` calls shared
operations. Scoped pagination rejects repeated/missing IDs and bounded exhaustion;
lyric offset subtraction, language selection, missing/unsynced reporting, malformed
responses, timeout and redacted errors have behavioral tests. Legacy LRC/scanner/M3U
models stay available without imposing paths on the new Track model.

**Verify:** `uv run pytest tests/test_navidrome.py tests/test_config.py tests/test_models.py tests/test_chunker.py tests/test_scanner.py -q`.

Dependencies: source/DTO/caller contracts. This is the first code milestone.

- [x] Define/refactor the normalized track and lyric models described above: source,
      library/song IDs, metadata, and timed lyric lines, without required local paths.
      Reuse the useful existing line/section behavior. Limit this step to the models
      needed by the adapter; migrating ingestion/search consumers belongs to Task 3.
- [x] Add typed connection settings and lifecycle-managed HTTP access with timeouts,
      redacted errors/logs, and credentials loaded server-side from environment/.env.
- [x] Implement connection inspection, selected-library paging, exact song lookup, and
      structured lyrics. Check Subsonic envelopes even on successful HTTP status.
- [x] Translate synced timestamps/offsets and select lyric language/variants explicitly.
      Report absent or unsynced-only lyrics; do not invent times, download audio, or
      silently fall back to local files.
- [x] Add the first CLI adapter through shared operations, with machine-readable output.
- [x] Mock auth/errors, malformed payloads, paging/interruption/duplicate IDs, inaccessible
      songs, and lyric variants/offsets. Assert discovery cannot mutate playlists.

Done when the reusable adapter reproduces the read-only probe and returns the normalized
domain models through the CLI, without file access, embedding calls, or index writes.

### Task 3 — Navidrome-Native Ingestion, Search, and Mount Removal

**Files:** Create `src/resonance/application/indexing.py`,
`src/resonance/application/ingest.py`, `src/resonance/application/search.py`, and
`tests/test_indexing.py`; modify `chunker.py`, CLI `ingest.py`/`search.py`,
`routes/ingest.py`/`routes/search.py`/`routes/collections.py`, `embedders/` where needed,
`tests/test_routes.py`, `tests/test_embedders.py`, `ui/index.html`, `Makefile`,
`docker-compose.yml`, `README.md`, and `CLAUDE.md`. Keep the user-deleted dev Compose file deleted.

**Definition of Done:** Real local Qdrant with mocked external APIs indexes a scoped
track collection without reading audio files, skips complete unchanged inputs, repairs
partial identical inputs, rejects changed track revisions requiring future refresh,
and returns distinct server song IDs plus lyric evidence. Partial/mixed section groups
are excluded from search. Incompatible source/profile/schema fails before embedding or
writing, including search after mutable provider-config changes. No automatic collection
delete, prune, refresh endpoint, or bulk live reindex is introduced. Existing M3U and raw
LRC command tests pass; mount-free setup and Makefile commands use the remaining Compose file.

**Verify:** `uv run pytest tests/test_indexing.py tests/test_routes.py tests/test_playlists.py tests/test_embedders.py -q`; `make -n up run down clean`; Compose config validation without printing secrets.

Dependencies: Task 2. This milestone needs no SQLite or music filesystem.

- [x] Move ingestion orchestration behind the shared application interface; adapt CLI
      and FastAPI to call it using Task 2's domain models. Replace filesystem-based
      scanner/path inputs, incremental bookkeeping, and result fields in those consumers.
- [x] Apply the collection binding above in both ingest and search. Validate source,
      actual model, dimensions, and schema before embedding/appending to an index.
- [x] Reuse chunking/embedding and attach server/library/song IDs to each section.
      Implement deterministic point IDs and the refresh-readiness payload contract
      above. Keep index-state lookup independent of the CLI/HTTP transport. Do not
      add refresh endpoints, scheduling, automatic pruning, or a SQLite track ledger.
- [x] Simplify the TEI client/config boundary if the current provider abstraction gets
      in the way. Record the actual served model and validate returned vector dimensions;
      an API-compatible client name or protocol placeholder is not model identity.
- [x] Return song IDs from search and deduplicate by server/song identity, preserving
      distinct recordings with identical titles. Handle stale IDs after server rebuilds.
- [x] Expose the collection's library/model binding in collection responses, and adapt
      existing debug displays if required by the new result fields; a Vue rewrite is
      still outside this milestone.
- [x] Populate a new Navidrome-native collection only as an explicit migration; preserve
      existing collections. Do not guess song IDs from filenames or titles, or trigger
      an unrequested full embedding run.
- [x] Test ingestion with filesystem access unavailable and mocked Navidrome/embedder/
      Qdrant. Cover scope/model mismatch, repeated IDs, partial scans, lyric gaps, and
      local-only configuration without a cloud fallback.
- [x] Verify unchanged input yields the same point IDs/hashes, lyric or pipeline changes
      change the appropriate fingerprints, and partial section sets are not reported
      complete. Confirm songs without usable lyrics are not marked successfully indexed.
- [x] User removed Resonance's music bind mount and deleted the separate dev Compose file.
- [x] Make the API ingestion path work in that mount-free deployment. Remove obsolete
      mounted-folder setup and update Makefile commands that reference the deleted
      Compose file. Remove Makefile dotenv include/export so credentials are not parsed as
      Make syntax; Python settings and Compose own dotenv parsing. Keep separately needed
      config, Qdrant, model-cache, and optional
      save-journal storage. Pass Navidrome configuration into the container explicitly;
      Compose's interpolation `.env` is not automatically the container environment.
      Explain legacy M3U's separate path requirements.

Done when a new collection can be populated and searched using only Navidrome APIs,
the configured embedder, and Qdrant, with playable song IDs carried through results.

### Task 4 — Transactional Save Journal and Verified Private Creation

**Files:** Create `src/resonance/state.py`, `src/resonance/application/playlists.py`,
`tests/test_save_operations.py`; extend `navidrome.py`/`models.py` as required.

**Definition of Done:** Actual SQLite persistence and a mocked Navidrome transport prove
transactional same-key claims, prepared-to-submitting compare-and-set, payload conflict,
exact source/account binding, no duplicate create on concurrent callers/restart/timeout,
and known-ID XML reconciliation. Only a private create on validated Navidrome 0.64.2
is allowed; unsupported/malformed versions fail before create. Verify XML public/owner/
name/count/ordered IDs; mismatches remain unverified. Preflight re-enumerates selected
library membership and revalidates getSong; duplicate-name creation needs acknowledgment.

**Verify:** `uv run pytest tests/test_save_operations.py -q` against real temporary SQLite files, including independent connections/concurrent workers.

Dependencies: accepted source/search contract and the validated server behavior.

- [x] Revalidate every song's source/library scope and accessibility immediately before
      save. Reject duplicates, unknown IDs, and unacknowledged duplicate names; preserve
      exactly the submitted order without omissions or substitutions.
- [x] Use SQLite if it is the simplest transactional journal. Persist operation key,
      caller/server/account/library, canonical request hash, approved ordered song IDs,
      name/privacy, state, and any returned playlist ID. No lyrics or credentials.
- [x] Claim operation keys transactionally across processes. Persist `submitting` before
      the network call and the returned ID immediately afterward. A changed request
      with the same key is rejected; concurrent/repeated requests cannot both create.
- [x] Reconcile known IDs by readback. Unknown outcomes after timeout/crash remain
      unresolved and must not blindly create again or match by name. Save retries
      never regenerate search results.
- [x] Verify exact ID, owner, name, privacy, count, and song order. Navidrome 0.64.2
      omits false visibility in JSON; XML readback provides explicit `public=false`.
      Do not turn an omitted field on an unvalidated server into a universal default.
- [x] Test definitive rejection, failure/crash windows, double submission, restart,
      stale IDs, omitted JSON visibility, failed envelopes, and readback mismatch.

Suggested states: `prepared`, `submitting`, `verifying`, `verified`, `failed`,
`unresolved`. Distinguish failure before mutation from an unknown remote outcome.

### Task 5 — Save Adapters and Product Acceptance

**Files:** Create `src/resonance/routes/navidrome.py`, `src/resonance/playlists.py`,
`src/resonance/routes/auth.py`, and `tests/test_navidrome_routes.py`; modify `app.py`,
`config.py`, `pyproject.toml`, `Dockerfile`, Compose/README/instructions, validation record,
and plan/PRD metadata as appropriate.

**Definition of Done:** CLI native create/status and `/api/navidrome/...` call the same
application use cases. New native endpoints and changed ingestion endpoint fail closed
without a configured operator bearer token; unauthorized requests do not reach Navidrome.
Resource lifecycle closes HTTP/Qdrant clients; durable journal storage is writable by
Docker's appuser and normal dev cleanup does not delete it. A real-code HTTP/CLI flow
with actual local Qdrant/SQLite and mocked Navidrome/embedding transport covers success,
invalid input, missing/stale IDs, errors, duplicate keys, and mismatch. Production CLI
reproduces read-only live checks and, within prior test authorization, a bounded private
playlist create/readback; client-visible results and any manual playback limits are
recorded honestly. No deployment/push or whole-library embedding is authorized here.

**Verify:** `uv run pytest -q`; `uv run ruff check src/`; `uv run ruff format --check src/`;
`uv run ty check src/`; `uv build`; isolated local HTTP runtime smoke with fixture APIs,
plus controlled live read-only/playlist probe (never touch unrelated user playlists).

Dependencies: Task 4. Read-only and ingest adapters can ship earlier.

- [x] CLI accepts an approved ordered selection and reuses its operation key on retry.
- [x] Add protected FastAPI equivalents using the same operations, with application
      errors mapped to transport results. Do not duplicate policy/orchestration.
- [x] Verify identical validation/order/retry outcomes through both adapters and denial
      for unintended callers using a shared saving credential.
- [x] Reproduce the real private-create/readback/client-playback gate through production
      operations, recording server and client versions and actual failures.
- [x] Run focused new tests plus the existing suite, Ruff, and `ty`. Default logs omit
      secrets, prompts, lyrics, and paths. Saves/probes make no model calls; ingestion
      uses only the deliberately configured embedding provider.

After these contracts settle, scope semantic generation/evaluation and the frontend
PRD. Vue 3 with TypeScript/Vite remains the recommendation. General playlist updates,
public sharing, per-library ingestion refresh, FastMCP, and multi-account/server support
remain independent follow-ons.

## Context for Implementer

- Artifact directory: `/tmp/resonance-navidrome-20261025-a5z37ma5`.
- Full spec workflow requested on 2026-10-25. The supplied `docs/pl` path was incomplete;
  the existing Navidrome plan was selected explicitly from the preceding conversation.
- At plan authoring the repository was the original POC. The plan reviews and
  implementation phases are recorded in this spec branch; earlier conversation alone
  was not treated as completed plan work.
- Pre-existing unrelated changes: deletion of `memory/MEMORY.md`,
  `memory/feedback_teaching_style.md`, and `memory/user_profile.md`; never stage them.
- User Compose mount removal/dev-file deletion and the PRD/plan/validation documents
  belong to this feature. Preserve them while making necessary additions.
- FastAPI TestClient hangs under this sandbox; prior tests passed outside the sandbox.
  Use escalated test runs when needed, with mocked external APIs.

## Concrete Implementation Decisions

- Keep a small filesystem-independent `Track` with scoped IDs, artist/title/album and
  lyric lines/status/language; retain legacy `SongData`/scanner for raw LRC and M3U
  compatibility. Chunking accepts either input. No fake audio paths on API tracks.
- Normalize timestamps as `(start_ms - offset_ms) / 1000`; preserve negative early
  times and sort/check input deterministically. Prefer an explicitly configured synced
  main-language track, accepting unknown `und`/`xxx` explicitly; otherwise choose a
  deterministic synced main variant. Never invent timestamps for unsynced text.
- Use collection metadata schema 2 with source/server fingerprint, account fingerprint,
  library ID, effective embedder profile, chunking/normalization configuration and index
  generation. Model alias alone is insufficient. Cache embedders by effective config,
  validate returned vector dimensions, and keep credentials out of profile metadata.
- Use UUIDv5 point storage keys derived from scoped song, generation, content/index
  hashes and position. Completion requires exactly the expected unique positions,
  coherent hashes, and expected storage IDs. Native search validates candidate groups
  and overfetches within a fixed cap; report bounded shortfalls without padding.
- Initial ingestion is resumable for identical content. Existing changed/mixed song
  revisions fail with an actionable new-collection/refresh-required conflict; no old-
  section cleanup or changed/deleted-track synchronization is silently implemented.
- Keep existing search request shape/artist filtering and legacy collection reads.
  `/api/ingest` switches to required library ID/provider, optional collection name and
  optional bounded max_tracks. Remove obsolete mounted-directory/force-recreate input
  rather than silently accepting it. Return track-oriented counts and explicit lyric
  outcomes. Native profile validation applies before querying/appending native indices.
- `resonance-library` provides inspect/libraries/tracks/lyrics; `resonance-ingest` uses
  `--library`/`--provider` with optional `--collection`/`--max-tracks`/`--batch-size`;
  `resonance-search` can resolve the stored provider automatically. Raw LRC inspection
  and legacy M3U requests remain separate and available.
- Native playlist input is operation_id, library_id, name, ordered song_ids and
  allow_duplicate_name. Bound selections to 100 songs. The operator credential is a
  configured bearer token for new native HTTP endpoints and ingestion; CLI is a trusted
  local operator adapter. Missing token disables protected HTTP operations with 503;
  invalid/missing credentials fail before outbound calls. Existing read-only search,
  collection/config/health contracts and legacy M3U are retained.
- Use `NavidromeConfig` loaded from NAVIDROME_BASE_URL, NAVIDROME_USER_ID,
  NAVIDROME_USER_PASSWORD, and optional server_id/language/timeout. HTTPS is required
  unless NAVIDROME_ALLOW_HTTP=true explicitly declares a trusted-local HTTP setup;
  TLS verification remains enabled and redirects are not followed. Settings reads .env
  without shell evaluation. HTTP authentication uses random salt/token in POST bodies;
  reject cross-origin redirects and sanitize all transport/protocol failures.
- SQLite stores no track mapping. Make operation ID globally unique within the journal,
  and validate stored server/account/library/caller bindings plus the canonical request hash. Prepared retries can resume validation, but only one
  transactional compare-and-set may transition to submitting. Persist the exact ID
  before verification. An unknown-ID submitting operation never creates again; known-ID
  retries only read back. Cross-account/server reuse and changed payloads conflict.
- Production create is one direct ordered create, then exact-ID XML readback. The
  version-pinned 0.64.2 source proves private default independently of song count; test
  the direct create in controlled live acceptance. Never change a public-created
  playlist to private and call its initial creation safe.

## Runtime Environment

- Local start: `make up` starts Qdrant/TEI dependencies from the sole Compose file;
  `make run` starts the source checkout API on port 8000. Qdrant is 6333, TEI is 8085.
- Local isolated test runtime: uvicorn with fixture Navidrome/embedding transport and
  local Qdrant/SQLite; use an unused port and inspect imported module paths for identity.
- Docker build: `make build`; do not deploy/restart the user's running stack merely
  because the spec workflow was invoked. `make prod` remains an explicit operator action.
- Health: GET /health reports Qdrant connectivity. OpenAPI /docs requires serve_docs.
- Journal: local ignored data/ by default; container /app/state on durable named volume,
  created/chowned for appuser. Routine dev down/clean preserves journal storage.
- Native configuration is explicitly passed into the container; .env interpolation
  alone does not inject it. Never print resolved Compose secrets in tool output.

## Feature Inventory

| Old file/behavior                                    | Destination                                                                 | Task / disposition           |
| ---------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------- |
| models.py LrcLine/LrcChunk                           | Reused lyric primitives                                                     | 2–3                          |
| SongData local Path/filename                         | Retained for legacy tools; new Track for API ingestion                      | 2                            |
| scanner.py discovery and mutagen helpers             | Legacy scanner remains; production source replaced by Navidrome             | 2–3, agreed source migration |
| parser.py file/text LRC parsing                      | Remains for raw inspection/scanner                                          | Unchanged                    |
| chunker.py tags/gaps/min-lines/positions             | Reused by native ingestion                                                  | 3                            |
| routes/ingest.py run_ingest and ingest API           | application/ingest.py plus thin HTTP route                                  | 3                            |
| ingest CLI provider/collection/batch/gap settings    | Native CLI; --data-dir/force-recreate superseded by library/new-index scope | 3, agreed source migration   |
| routes/search.py and search CLI                      | Shared application/search.py, legacy reads retained                         | 3                            |
| embedder protocol/OpenAI/TEI/Ollama factories        | Retained small interface; effective-profile cache/dimension validation      | 3                            |
| /api/playlists M3U, filename sanitizer and overwrite | Existing route and scanner helper remain                                    | Unchanged, regression tests  |
| resonance-chunks raw LRC inspection                  | Existing CLI remains                                                        | Unchanged, regression tests  |
| health/config/collection listing/deletion/docs/CORS  | Retained; add source binding to collection listing                          | 3–5                          |
| ui/index.html debug search                           | Minimal new metadata display if required; no Vue rewrite                    | 3                            |
| Compose music mount/dev Compose removal              | Preserve user edits; fix Makefile/config forwarding/state ownership         | 3–5                          |
| memory/ deletions                                    | Unrelated user changes; never stage                                         | Excluded                     |

## Risks and Mitigations

| Failure                                  | Concrete behavior                                                                                             |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Mutable config changes model space       | Store/compare effective profile in ingest and search before model/index operations                            |
| Partial/mixed song section writes        | Derived completeness + deterministic IDs; exclude incomplete search groups; same-content retry repairs        |
| Wrong library/server song                | Scope metadata and membership enumeration plus exact-ID preflight; no artist/title matching                   |
| Duplicate create after timeout/crash     | SQLite unique claim + CAS; persist submitting before network; unknown stays unresolved                        |
| Omitted JSON privacy                     | Explicit XML visibility; only validated Navidrome product/version may create                                  |
| Readback mismatch                        | Persist unverified/unresolved state; never return verified or mutate user lists to hide mismatch              |
| Missing/unsynced/multiple lyric variants | Explicit deterministic language/variant policy and outcome counts; no fabricated timings/fallback             |
| Local journal unwritable/ephemeral       | Docker-owned persistent state volume; cleanup does not destroy it                                             |
| Source migration loses old tools         | Feature inventory plus unchanged scanner/chunker/raw LRC/M3U regression coverage                              |
| Hosted data leakage                      | Explicit configured provider only; no fallback; probe/save never calls a model; sanitized default errors/logs |

## Testing Strategy

Use actual local Qdrant (:memory:) and SQLite temp files with external HTTP transports
mocked for meaningful application/CLI/API integration. Test fixtures use original
synthetic lyrics. Check persisted points and DB states, not only call counts. TestClient
requires escalation in this environment. Live Navidrome/TEI checks remain bounded and
must not print lyrics/secrets or trigger a whole-library indexing migration.

## Removes

- Mounted-directory/force-recreate inputs in the new production ingestion interface,
  superseded by the user-approved Navidrome source migration and explicit new indices.
- docker-compose.dev.yml remains user-deleted; references are migrated to Compose.
- Old local-ingestion-specific route tests are adapted to native-source behavior.

### Removes (verify)

- None. Keep scanner/parser/SongData and embedder variants for remaining callers/tools.

## ADR Reference

`docs/adr/001-navidrome-application-boundary.md` records the source and shared-application
architecture departure, direct server identity, and Qdrant versus SQLite responsibilities.

## Remaining Acceptance Information

- Follow-on cleanup direction from the user: TEI does not switch to Ollama. For a
  TEI-only deployment, simplify the separate Ollama/type branch while retaining the
  OpenAI-compatible HTTP client and endpoint/model/dimension/revision settings.
- Use the supplied collection name as a namespace, then include normalized model and
  dimensions in new Qdrant collection names. Keep full profile/fingerprint metadata
  authoritative. Replacing the current metadata sentinel point with Qdrant collection
  metadata and migrating the naming convention are deferred; preserve existing indices.

- Browser playback/advancing is user-confirmed. The private UI indicator and exact
  client version are not recorded; API XML privacy was verified. It does not prevent implementation or mocked/runtime validation.
- Runtime publishing/deployment and bulk live reindexing remain outside this run.

## Plan Review Resolution

- Alignment review 1: HTTPS enforcement was underspecified. Added an explicit
  NAVIDROME_ALLOW_HTTP trusted-local exception, secure default, no redirect forwarding,
  TLS verification, Docker forwarding, and pre-request rejection tests to Task 2.

- Challenge review 1: removed Makefile dotenv include/export from the runtime design;
  add a synthetic quoted/dollar-containing credential test so Python/Compose parsing
  cannot be overridden by Make expansion.
- Challenge review 1: operation_id is globally unique within the single deployment's
  journal. Every retry validates stored source/account/library/caller and request hash;
  changed configuration conflicts instead of creating a new namespaced row. Test this
  with a persisted uncertain operation and a restarted service under another binding.

Task 2 evidence: focused tests passed (45), source Ruff/ty passed, and production module CLI inspect returned Navidrome 0.64.2 with expected capabilities. Full regression suite was also run.

Task 3 evidence: 103 tests passed, including actual in-memory Qdrant ingestion/search, partial-write repair, changed-profile rejection and legacy regression paths. Source Ruff/format/ty passed. Make dry run and quiet Compose validation passed. No live collection was changed.

Task 4 evidence: 35 focused transport/journal tests passed using actual SQLite and the production Navidrome adapter. Concurrent independent connections claim once; timeout/crash retries never recreate; known IDs reconcile and all privacy/order/owner mismatches stay unverified. Ruff/format/ty passed.

Task 5 evidence: full suite 132 passed; Ruff/format/ty and uv build passed. Quiet Compose validation passed. Production installed CLI inspect and one three-song direct private create/readback passed; same-key retry returned the same ID. Isolated real uvicorn HTTP runtime used on-disk Qdrant/SQLite and fixture HTTP to verify ingestion/search/save and failure cases. Exact browser version/private UI indicator remain unrecorded; earlier browser playback is user-confirmed. No deployment or bulk live indexing occurred.

## Task 6 — Verification Repairs (Review Pass 1)

Files: `config.py`, `embedders/openai.py`, `embedders/__init__.py`, `navidrome.py`,
`search.py`,
corresponding integration tests and documentation.

Definition of Done: native CLI prints selectable source/library/song IDs; the actual
OpenAI endpoint, cache key and stored profile agree when OPENAI_BASE_URL changes;
malformed XML snapshot counts persist known-ID unresolved outcomes and can recover
without another create. First-pass review findings were fixed; focused compliance re-review passed with no remaining issue.

- [x] Print IDs/scope in native CLI search and test a search-CLI-to-save-CLI handoff.
- [x] Resolve one effective endpoint for SDK/profile/cache; test environment changes
      and reject incompatible native collections before any embedding request.
- [x] Translate malformed playlist counts into safe protocol errors; test persisted
      known-ID unresolved state, no duplicate create and successful later readback.

Verification: all three repair behaviors are exercised in focused local tests. Full TestClient suite, final package build/runtime and review follow-up remain recorded under Verification Limitations below.

## Verification Limitations

The user additionally confirmed that ingestion and semantic search work in their
local setup; the run configuration/counts were not supplied. The current code passed
68 focused tests covering the three review repairs and 102 broader sandbox-compatible
tests. Ruff lint, format and `ty` are clean. The full suite
passed 132 tests before these small repairs; the original TestClient tests need the
sandbox's escalated execution and hang when run directly in the sandbox. A request for the required escalated full-suite rerun was rejected by the automatic
approval service because it reached its usage limit. The user reviewed the state of the
branch after this limit was disclosed and explicitly authorized the merge. The compliance
and quality follow-ups both passed with no remaining issues. Merge proceeds with the
full TestClient rerun recorded as an uncompleted check; this record does not claim that
the rerun passed. No code gap is known from the completed focused tests; this is an
execution/approval limitation accepted for this merge.
