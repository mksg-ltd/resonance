---
status: complete
approved: true
iterations: 0
branch: spec/admin-collection-creation
base_branch: spec/prd13-user-search-playlist
base_commit: 8e0b33247f1bd287d17ddcb54580b00d9da19a4c
prd: ""
created: 2026-10-26
updated: 2026-10-26
author: MK
tags: [admin, collections, ingestion, vue]
---

# Admin Collection Creation Implementation Plan

## Summary

**Goal:** Let the configured Resonance admin create a searchable collection from an
authorized Navidrome library and selected supported embedding profile in Vue.
**Architecture:** Treat collection creation as an explicit admin-triggered initial
ingestion through the existing `POST /api/ingest` application path. Add a protected
profile-catalog endpoint; do not create empty Qdrant collections or duplicate ingest
policy in the UI.
**Tech Stack:** FastAPI, existing AuthRuntime/`require_admin`, Vue 3, Qdrant, bundled
embedding-profile catalog.

## Scope

### In Scope

- Admin-only retrieval of supported embedding profile IDs and safe display metadata.
- Admin Vue form to select an available Navidrome library and profile, optionally name
  the Qdrant collection, and begin ingestion.
- Default to a bounded 10-track initial run; allow full-library ingestion only after
  explicit confirmation, with the existing synchronous/no-progress limitation stated.
- Display the resulting collection and ingestion counts, refresh accessible collections,
  and make a newly created collection selectable for search.
- Preserve current API authorization and `ensure_collection` compatibility checks.

### Out of Scope

- Background jobs, progress streaming, cancellation, pause/restart, or incremental
  refresh/reconciliation of changed/deleted tracks.
- Embedding endpoint/credential settings UI; deployment configuration remains in `.env`.
- Empty collection creation, collection deletion UI, or ordinary-user admin operations.
- FastMCP tools and PRD, and PRD-10 open-source readiness decisions.

## Prerequisites

- PRD-12 admin identity and the Vue authentication flow are implemented on the base
  branch.
- `POST /api/ingest` already creates or safely reuses a collection and enforces
  `require_admin`.
- Navidrome libraries are returned by `/api/auth/me`; embedding profiles ship in
  `resonance/data/embedding_profiles.yaml`.

## Context for Implementer

- **Patterns:** `src/resonance/routes/ingest.py` adapts the shared ingest operation;
  `src/resonance/routes/auth.py:204` enforces `require_admin`; `vue-ui/src/App.vue`
  owns authenticated same-origin requests and card patterns.
- **Conventions:** Use `/api` contracts and `credentials: "same-origin"`; never expose
  embedding API keys or Navidrome credentials. Reuse the session `is_admin` flag for
  visibility but rely on FastAPI for enforcement.
- **Key files:** `src/resonance/routes/config.py`, `src/resonance/embedding_profiles.py`,
  `src/resonance/routes/ingest.py`, `vue-ui/src/App.vue`, `vue-ui/src/style.css`.
- **Gotchas:** `run_ingest` creates the collection as part of ingestion and will reject
  an existing collection with incompatible library/profile/index metadata. The
  endpoint is synchronous. A response loss may occur after partial writes; retrying the
  same collection is safe only for unchanged/identical partial tracks. A changed lyric
  requires a new collection until refresh exists.
- **Domain context:** Admin status is determined by exact match with configured
  `RESONANCE_ADMIN_USER`. The admin's Navidrome session controls which libraries are
  selectable. Collections are scoped to server and library, and profile/model/index
  details are already stored in Qdrant metadata.
- **Artifact directory:** `/tmp/resonance-admin-collection-artifacts`
- **Test framework constraints:** Backend integration tests use FastAPI TestClient,
  in-memory Qdrant, and mocked Navidrome/embedder clients. Vue has no component-test
  harness. For this implementation run, do not add or execute tests; use static checks
  and record that live authenticated acceptance remains for the operator.

## Runtime Environment

- **Start command:** `make run`, plus `make ui` for Vite development.
- **Port:** FastAPI `http://127.0.0.1:8000`; Vite `http://127.0.0.1:5173`.
- **Deploy path:** The production image serves the Vue app from `/app/`.
- **Health check:** `GET /health`; it requires the configured Qdrant endpoint to be
  reachable for a healthy response.
- **Restart procedure:** Restart FastAPI after route changes and Vite after frontend
  changes; `make build` packages both.
- **Code identity:** Run the API and Vite from this worktree, or rebuild the image and
  verify the built `/app/` bundle and profile endpoint use this branch.

## Feature Inventory

| Existing behavior                                  | Function or route                    | New location                                  | Task      |
| -------------------------------------------------- | ------------------------------------ | --------------------------------------------- | --------- |
| Admin can start ingestion from operator HTML       | `ui/index.html` → `POST /api/ingest` | Vue admin collection panel uses same endpoint | Task 2    |
| Ingest can select profile through API/CLI          | `IngestRequest.profile`              | Profile catalog endpoint and Vue selector     | Task 1    |
| Collection created/reused with safe binding checks | `run_ingest` → `ensure_collection`   | Retain unchanged                              | Tasks 1–2 |
| Admin-only ingestion enforcement                   | `require_admin` on `/api/ingest`     | Retain and test unauthorized denial           | Task 1    |

## Progress Tracking

- [x] Task 1: Expose the supported embedding profile catalog to admins.
- [x] Task 2: Add the Vue admin create-and-ingest workflow with bounded defaults and clear outcomes.
- [x] Task 3: Document and verify the admin workflow and its operational limits.

**Total Tasks:** 3 | **Completed:** 3 | **Remaining:** 0

## Implementation Tasks

### Task 1: Admin profile catalog API

**Objective:** Let an authenticated admin retrieve profile IDs, model IDs, dimensions,
protocol, and current default without exposing secrets.

**Dependencies:** None

**Files:**

- Modify: `src/resonance/routes/config.py`, `src/resonance/app.py` only if router wiring is needed.
- No test files added or changed.

**Key Decisions / Notes:**

- Add a dedicated `GET /api/embedding-profiles` endpoint guarded by `require_admin`.
- Read the bundled catalog via `embedding_profiles()` and return sorted safe profile
  metadata plus `is_default`; never include runtime base URLs, API keys, or credentials.
- Keep ingest's existing selected-profile and admin authorization behavior.

**Definition of Done:**

- [x] Admin receives supported profile metadata with the configured default marked.
- [x] Regular and unauthenticated users cannot retrieve the admin catalog endpoint;
      the route uses the shared `require_admin` dependency.
- [x] Response contains no credential, base URL, or user secret values.

**Verify:**

- Source review confirms the endpoint depends on `require_admin` and returns only the
  bundled profile IDs/model metadata; test execution is intentionally omitted.

### Task 2: Vue admin collection workflow

**Objective:** Allow the admin to create a collection by starting ingestion using a
selected library/profile and an optional collection namespace.

**Dependencies:** Task 1

**Files:**

- Modify: `vue-ui/src/App.vue`, `vue-ui/src/style.css`.
- Reuse: `/api/auth/me`, `/api/embedding-profiles`, `/api/collections`, `/api/ingest`.
- Verify: production Vite build and authenticated browser workflow when operator tests.

**Key Decisions / Notes:**

- Show the form only when the authenticated principal has `is_admin`.
- Load profile choices from the protected API; default to the configured profile and
  display model/dimensions so the admin can distinguish embedding spaces.
- Use the signed-in user's returned Navidrome library list. No extra library read is
  needed because login already establishes those grants.
- Default the track limit to 10. Blank limit means full-library synchronous ingestion
  and requires a confirmation naming the selected library and that progress/cancel are
  unavailable.
- Submit to existing `/api/ingest`; do not add another collection-creation abstraction.
- On success refresh `/api/collections`, select the resulting collection for search,
  and show processed/unchanged/skipped counts plus whether enumeration completed.
- On failures show the API's safe detail and preserve form values for correction/retry.

**Definition of Done:**

- [x] Only admins see the workflow; API still independently rejects non-admin ingest.
- [x] Admin can choose a permitted library and profile, name or auto-name a collection,
      and request a bounded initial ingest.
- [x] Full-library ingest requires explicit confirmation; default request is limited to
      10 tracks.
- [x] Successful collection appears in search choices with its profile metadata and
      the result summary reports the server response counts.
- [x] Incompatible existing collection and embedding/provider errors remain visible and
      do not cause UI to claim creation succeeded.

**Verify:**

- `pnpm --dir vue-ui build` — production UI compiles.
- Browser/API smoke: admin sees form and can create a bounded collection; regular user
  sees no form and direct `POST /api/ingest` returns 403.

### Task 3: Documentation and acceptance evidence

**Objective:** Explain admin collection setup and the limits the operator should
expect during first ingestion.

**Dependencies:** Tasks 1–2

**Files:**

- Modify: `README.md` and this plan.

**Definition of Done:**

- [x] README distinguishes user discovery from admin collection creation, explains
      profile selection and 10-track default, and states synchronous/full-library limits.
- [x] Plan records source review, UI build, and the outstanding authenticated browser
      acceptance requirement.

**Verify:**

- `git diff --check` and repository lint/format/type checks pass.

**Implementation evidence (2026-10-26):** `ruff check src/`, `ruff format --check
src/`, and `ty check src/` passed. Vite production build passed using the lockfile-pinned
dependencies available in the primary checkout. `git diff --check` passed. Automated
tests were not added or run in this pass. The authenticated Navidrome browser flow and
actual Qdrant collection creation remain for operator acceptance; do not treat this
plan's source review/build checks as that end-to-end evidence.

## Testing Strategy

- Code review: verify the profile endpoint uses `require_admin`, emits no runtime
  credentials, and the Vue calls the existing protected ingestion route.
- UI: Build the Vue bundle. The authenticated browser flow and actual Navidrome/Qdrant
  collection creation remain for operator acceptance.
- Automated tests are not added or run in this implementation pass.

## Risks and Mitigations

| Risk                                                               | Likelihood | Impact | Concrete mitigation                                                                                   |
| ------------------------------------------------------------------ | ---------- | ------ | ----------------------------------------------------------------------------------------------------- |
| A non-admin reaches collection creation through direct API call    | Low        | High   | Keep `require_admin` on `/api/ingest` and verify 403 causes no Navidrome/embedder/Qdrant work.        |
| Admin selects a profile whose endpoint is not configured           | Med        | Med    | Return safe API error; preserve form selection and do not display a success state.                    |
| Admin starts an unexpectedly large synchronous ingest              | Med        | High   | Default to 10 tracks; require explicit confirmation for unlimited run and explain no progress/cancel. |
| Existing collection name belongs to a different profile or library | Med        | High   | Preserve `ensure_collection` metadata compatibility rejection; show error without overwrite.          |

## Removes

- None. The `/ui` operator PoC remains available; this adds the product-facing admin
  workflow to Vue.

### Removes (verify)

- None.

## ADR Reference

No ADR needed. Vue will invoke the existing admin-protected ingest contract and the
existing application layer remains the owner of collection creation and indexing.

## Open Questions

- None for this bounded create-and-ingest workflow. Progress/cancel and refresh are
  separate follow-on work.

### Deferred Ideas

- Ingestion progress, cancellation, pause/resume controls, and per-library refresh.
- Dedicated admin settings for endpoint URLs and credentials.
- Actual MCP search/playlist tools and PRD-10 open-source readiness work.
