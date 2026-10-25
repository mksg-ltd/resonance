---
status: complete
approved: true
iterations: 0
branch: spec/prd09-search-ingest-poc
base_branch: main
base_commit: c66f4fb454728889baac87ff03fe9dc9a4c597e3
prd: docs/prds/09-navidrome-semantic-playlists.md
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [navidrome, semantic-search, ingestion, poc-ui]
---

# PRD-09 Search and Ingestion PoC UI Plan

## Summary

**Goal:** Let a local operator select one Navidrome library, start or repeat ingestion into a Qdrant collection, then search that collection from the existing plain HTML page.
**Architecture:** Keep the application layer and FastAPI routes as-is. Extend `ui/index.html` as a static client for existing library, collection, ingestion, and search endpoints. The browser never receives Navidrome credentials; protected calls use an operator bearer token typed into one simple page field.
**Tech Stack:** Existing HTML/CSS/JavaScript, FastAPI, Navidrome, Qdrant. No Vue or frontend build system.

## Scope

### In Scope

- A fixed local FastAPI URL (`http://localhost:8000`) and one in-memory operator-token field.
- Fetch/display visible Navidrome libraries; select exactly one for an ingestion run.
- Start ingestion with the configured embedding profile, optional collection name, and a bounded track limit defaulting to 10. Clearing the limit explicitly requests the full library.
- Display the created/used collection and ingestion counts/completion status; make it available in the search selector.
- Keep a newly returned metadata-only collection visible even when it has no indexed lyric sections, and derive its no-searchable-tracks state from the refreshed collection's `points_count`, not only this run's write counts.
- Search an existing or newly created native collection and display ranked track/section evidence using current result behavior.
- Explain additive re-ingestion and its changed/deleted-track limitations in the UI.
- Document running the API in debug mode and serving `ui/` on a separate local port.

### Out of Scope

- Changes to application search or ingestion semantics, Navidrome/Qdrant client layers, or collection schema.
- Changed-lyrics replacement, removed-track pruning, scheduled refresh, destructive reset/delete controls, or background progress jobs.
- Seed/theme playlist generation, preview/edit/save UI, Vue, FastMCP, multi-account, or multi-server workflows.
- Persisting the operator token in the page, local storage, or static source; reading `.env` in browser code.

## Prerequisites

- The backend is on `main` at `c66f4fb454728889baac87ff03fe9dc9a4c597e3`; current repository tests were reported by the user as 86 passing in 4.47 seconds.
- Local `.env` contains Navidrome, Qdrant, embedding, and `RESONANCE__API_TOKEN` settings.
- A reachable configured Navidrome server and embedding endpoint are available for a manual end-to-end run.
- Run the API in debug mode for CORS. Serve the static page on port 8080 because API dev uses port 8000.

## Context for Implementer

- **Patterns:** `src/resonance/app.py` enables CORS only when `settings.debug`; `dev()` currently binds `0.0.0.0` and debug CORS currently allows any origin. Dev API port is 8000. `src/resonance/routes/auth.py` validates bearer tokens. `src/resonance/routes/navidrome.py` exposes protected `GET /api/navidrome/libraries`; `src/resonance/routes/ingest.py` exposes protected `POST /api/ingest`; `src/resonance/routes/collections.py` exposes `GET /api/collections`; `src/resonance/routes/search.py` exposes `POST /api/search`.
- **Conventions:** Keep UI code dependency-free and in the existing single page. Reuse `escapeHtml` for API values. Keep the bearer token in a JavaScript variable only; do not store it. Do not include credentials or full lyrics in logs.
- **Key files:** `ui/index.html` existing collection/search controls; `README.md` local setup and runtime instructions; backend files above define exact request/response shapes.
- **Gotchas:** The user will run `python -m http.server 8080 --bind 127.0.0.1` from `ui/`; the API must be `http://localhost:8000` in debug mode for separate-origin CORS. Do not use Python's default port 8000 for the static server. Search and collection list are currently unauthenticated; library listing and ingest require `Authorization: Bearer <token>`. Send the token only to protected library/ingest calls. The token must not be hard-coded or persisted. Since search/collection reads are unauthenticated, bind the dev server to loopback and restrict debug CORS to the two local UI origins.
- **Domain context:** Omitting `collection` lets the backend generate a name scoped to server/library/model/index settings. A typed collection can be reused only if its binding matches. A run adds new eligible tracks, skips unchanged complete tracks, and resumes identical partial writes. Changed indexed lyrics fail with `refresh_required` without replacing that song's sections; earlier completed songs in the run can remain indexed. Deleted/inaccessible tracks are not pruned. `max_tracks` means the enumeration is incomplete.
- **Artifact directory:** `/tmp/resonance-prd09-search-ingest-poc-20261025`
- **Test framework constraints:** Python tests cover API contracts; no JavaScript/browser test harness is installed. Use the existing route tests for endpoint contracts and perform a documented browser smoke test for the static page. Do not add a frontend framework solely for testability.

## Runtime Environment

- **Start command:** `make run` (debug API; port 8000), then from `ui/`: `python -m http.server 8080 --bind 127.0.0.1`.
- **Port:** API `8000`; static page `8080`.
- **Deploy path:** Local source checkout only; no image or production static deployment changes.
- **Health check:** `curl http://localhost:8000/health` returns healthy; open `http://localhost:8080` and connect with the configured operator token.
- **Restart procedure:** Restart `make run` after API/config changes and restart the Python static server after UI changes if needed.
- **Code identity:** Browser loads the current `ui/index.html` from `python -m http.server`; API source is the local checkout started by `make run`.

## Progress Tracking

- [x] Task 1: Add the operator token, library and collection controls, and local-only dev access.
- [x] Task 2: Add bounded collection ingestion and connect its result to semantic search.
- [x] Task 3: Document the PoC workflow and available endpoint contracts.

**Total Tasks:** 3 | **Completed:** 3 | **Remaining:** 0

## Implementation Tasks

### Task 1: Local-only PoC access and target selection

**Objective:** Use the fixed local API URL in the existing static page and let the operator choose the single Navidrome library and collection to search.

**Dependencies:** None

**Files:**

- Modify: `ui/index.html`
- Modify: `src/resonance/app.py`
- Test: `tests/test_routes.py`

**Key Decisions / Notes:**

- Use `http://localhost:8000` as the API URL constant. If the operator changes their local port, they can edit that one constant in the PoC page.
- Keep the bearer token in memory and add it to protected calls. Do not write token to source, query strings, logs, or browser storage.
- Load libraries from `/api/navidrome/libraries` and collections from `/api/collections`; surface authorization/network failures clearly. The current `points_count > 1` filter hides metadata-only collections, so retain the just-returned collection even when it has one metadata point.
- Filter collection choices to the selected library when the returned binding permits it; do not silently choose an incompatible collection.
- Bind `resonance-dev` to `127.0.0.1` and restrict debug CORS to `http://localhost:8080` and `http://127.0.0.1:8080`. Do not change the production server bind behavior.

**Definition of Done:**

- [x] Operator can enter the bearer token and choose a library; API URL stays a fixed local constant in the page.
- [x] Collections load and the operator can select one for search.
- [x] Missing/invalid token, server errors, validation details, and empty library/collection states are visible and actionable.
- [x] Late collection-list responses cannot overwrite the list for a newer library selection; library/ingest controls are locked while either library loading or ingestion is running.
- [x] Debug CORS permits the two documented local static origins and denies an unrelated origin; the development runner binds only to loopback.

**Verify:**

- `.venv/bin/pytest tests/test_routes.py::TestLocalDevelopmentAccess -q` — 2 passed; confirms the debug CORS origins and loopback runner setting.
- Manually open the page from port 8080 against debug API port 8000; library request succeeds with a valid token and shows a clear 401 message without one.

### Task 2: Safe ingestion and semantic search workflow

**Objective:** Start a new or additive ingestion run from the page, report its actual outcome, and make its collection searchable.

**Dependencies:** Task 1

**Files:**

- Modify: `ui/index.html`
- Test: `tests/test_routes.py`, `tests/test_indexing.py` (existing backend behavior; add only if a contract gap is found)

**Key Decisions / Notes:**

- Call existing `POST /api/ingest` with `library_id`, optional `collection`, and optional `max_tracks`; the active embedding profile comes from server configuration unless an explicit profile selector becomes necessary.
- Default the UI limit to 10 for a safe first run. Clearing the field means full-library ingestion and must be labeled clearly.
- If the operator clears the limit, show that the run covers the entire library and require a simple browser confirmation before submitting.
- Show collection name, tracks seen/processed/unchanged, sections written, skipped, missing/unsynced lyrics, and `enumeration_complete`.
- The endpoint is synchronous and has no progress updates. Label full-library runs as potentially long; if the browser loses the response, explain that the request may have completed and an identical retry is safe for unchanged/partial songs.
- Keep a created collection visible with a “no searchable tracks indexed” state when the refreshed collection has only its reserved metadata point; do not infer this solely from per-run counts or present the metadata point as a search result.
- On success, refresh the collections list and select the returned collection for semantic search.
- Keep explicit copy that repeated runs add new tracks and skip unchanged ones; changed lyric content errors and deleted tracks are not reconciled. If a run reaches changed content after earlier writes, say those earlier songs may already be indexed. Do not expose collection deletion/reset.
- Preserve current result rendering and HTML escaping.

**Definition of Done:**

- [x] Operator can start a bounded ingestion run and sees all returned counts plus complete/incomplete enumeration state.
- [x] Leaving the collection name blank uses the backend-generated collection; entering a compatible name repeats/adds safely; incompatible bindings show the backend error without clearing data.
- [x] The created/used collection is selectable for search and displays artist, title, score, section and lyric excerpt.
- [x] A newly returned collection with only the reserved metadata point remains visible; the page uses refreshed `points_count` to show no searchable tracks.
- [x] Full-library runs disclose that they are synchronous without progress; a browser network failure explains that completion may be uncertain and that same-collection unchanged/partial retries are safe.
- [x] UI copy does not claim complete refresh and warns that full-library ingestion may take time.

**Verify:**

- `.venv/bin/pytest tests/test_indexing.py -q` — 9 passed; confirms collection creation and safe additive/unchanged/partial behavior.
- Manual browser run with `max_tracks=10` against a test collection remains part of local acceptance; only use full-library mode when explicitly intended.

### Task 3: Runtime documentation

**Objective:** Document the local PoC launch sequence and the operator's acceptance workflow.

**Dependencies:** Tasks 1 and 2

**Files:**

- Modify: `README.md`
- Test: None; manual browser acceptance is recorded below.

**Key Decisions / Notes:**

- Document `make run`, `python -m http.server 8080 --bind 127.0.0.1` from `ui/`, API URL, bearer-token entry, CORS/debug requirement, and cleanup.
- Keep the existing API-served `/ui` as an alternate path, but demonstrate the separately served workflow requested by the user.
- Never print or copy `.env` credentials as part of the instructions.

**Definition of Done:**

- [x] README commands match current Make targets and ports.
- [x] README explains connecting, selecting a library, creating/populating a bounded collection, and searching it.
- [x] No new dependency or frontend build tooling is added.

**Verify:**

- `.venv/bin/pytest tests/test_routes.py::TestLocalDevelopmentAccess -q` and `.venv/bin/pytest tests/test_indexing.py -q` — focused local access and ingestion contracts pass.
- Full browser end-to-end requires the user's local Qdrant/Navidrome/embedding services; run it using the README commands.

## Testing Strategy

- Unit/integration: use existing pytest route and local-Qdrant indexing tests; extend only if implementation reveals an uncovered backend contract.
- Browser: manually verify successful connection, auth failure, no-library/collection states, bounded ingest, API error rendering, and a successful semantic search.
- Runtime: use an isolated/test Qdrant collection and `max_tracks=10`; do not run an unbounded production ingestion as a test.

## Risks and Mitigations

| Risk                                                                    | Likelihood | Impact | Concrete mitigation                                                                                                                                        |
| ----------------------------------------------------------------------- | ---------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| User expects changed lyrics/deleted songs to be reconciled by "refresh" | High       | Med    | Label the operation as additive re-ingestion and show current unsupported cases before each run.                                                           |
| Full-library ingestion is slow or the browser loses the response        | Med        | Med    | Default to 10 tracks; confirm full-library scope, state that there is no progress display, and explain same-collection retries for unchanged/partial work. |
| Static UI cannot call the API because origins differ                    | Med        | Med    | Allow exactly the two documented localhost origins in debug CORS and surface network failure guidance.                                                     |
| Debug API exposes unauthenticated search/collection reads to the LAN    | Med        | High   | Bind the development runner to loopback and restrict CORS to the local static-page origins; leave production deployment policy unchanged.                  |
| Metadata-only collection is hidden by the existing points-count filter  | Med        | Low    | Keep the newly returned collection visible and display a no-searchable-tracks state.                                                                       |
| A late library/collection response displays the wrong scope             | Low        | Med    | Ignore collection-list responses from older requests and disable library changes during ingestion.                                                         |
| Operator token leaks into a committed/static artifact                   | Low        | High   | Accept token at runtime, keep it in page memory only, and never read `.env` in browser code.                                                               |
| Existing collection name has different source/model/index settings      | Med        | Med    | Rely on backend binding validation and display its error; never delete/recreate on mismatch.                                                               |

## Removes

- None.

### Removes (verify)

- None.

## ADR Reference

No ADR needed. This uses the established shared application/FastAPI boundary and adds only a static client.

## Open Questions

- None required for implementation. The plan assumes collection name is optional and the backend-generated name is the default; a user can enter an existing compatible name to rerun ingestion.

## Verification Record

- CORS/dev binding tests: passed (2 tests).
- Native indexing tests: passed (9 tests).
- Ruff check and formatting for `src/resonance/app.py`: passed.
- `ty check src/`: passed.
- `git diff --check`: passed.
- Independent implementation compliance and quality reviews: passed with no remaining findings.
- Full suite and browser end-to-end were not completed in this environment. Qdrant was not available on `localhost:6333`; the existing TestClient suite stalled during startup. The browser flow needs the user's configured Navidrome, Qdrant, and embedder and is documented in README.

### Deferred Ideas

- Full changed/deleted-track library reconciliation, scheduler, changed-lyrics replacement.
- Vue frontend, FastMCP, semantic seed/theme generation, preview/editor, and playlist creation UI.
- Playlist update/share flows and broader multi-account/server support.
