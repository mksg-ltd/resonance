---
status: pending
approved: true
iterations: 0
branch: spec/prd13-user-search-playlist
base_branch: spec/prd12-auth-foundation
base_commit: 8347f95d0eec50d6a64004b3b1c05ba840b4123d
prd: docs/prds/13-assistant-user-experience.md
created: 2026-10-26
updated: 2026-10-26
author: MK
tags: [vue, search, playlists, navidrome]
---

# PRD-13 Vue Search and Playlist Workflow Implementation Plan

## Summary

**Goal:** Let an authenticated Navidrome user search an authorized semantic collection, review and order grounded song candidates, and explicitly save them as a verified private playlist.

**Architecture:** Extend the existing Vue 3/Vite application to consume the same-origin FastAPI APIs. Reuse `POST /api/search`, `POST /api/navidrome/playlists`, and `GET /api/navidrome/operations/{operation_id}`. Keep search and save policy in the existing transport-independent application layer; add no CLI subprocesses or duplicate business logic.

**Tech Stack:** Vue 3, Vite, existing FastAPI/Pydantic APIs, Navidrome, Qdrant, SQLite save journal.

## Scope

### In Scope

- Build on the existing login/session and authorized library/collection display.
- Search one accessible collection using a user-written theme or mood query.
- Show ranked distinct tracks and their matched lyric evidence.
- Let the user select, remove, and reorder up to 100 tracks.
- Require an explicit playlist name and save action before creating a private Navidrome playlist.
- Display verified, failed, and unresolved save states from the existing operation journal.
- Preserve operation IDs and exact request bodies across uncertain responses; never silently retry with a fresh key.

### Out of Scope

- FastMCP server/tools or MCP login and token lifecycle in this implementation slice. After the user validates search and match quality, add a thin FastMCP scaffold based on the Nool and Obsidian MCP examples, then design authentication before exposing tools.
- Seed-song search, LLM generation, conversation ingestion, automatic candidate selection, or automatic playlist creation.
- Changes to admin ingestion, collection management, embedding settings, or the `/ui` operator PoC.
- Playback, streaming, public playlists, or shared playlist collaboration.
- New search/save backend behavior unless implementation demonstrates a concrete contract gap.

## Prerequisites

- PRD-12 authentication is implemented on the base branch `spec/prd12-auth-foundation` at `8347f95d0eec50d6a64004b3b1c05ba840b4123d`.
- Existing API endpoints enforce caller library permissions and create/read back private playlists as the authenticated Navidrome user.
- A logged-in Navidrome account has access to at least one configured collection for browser acceptance.

## Context for Implementer

- **Patterns:** `vue-ui/src/App.vue` owns the current same-origin cookie-authenticated page; `ui/index.html` has search UI patterns but must remain an operator PoC. `src/resonance/routes/search.py` authorizes collection access before calling `application.search.run_search`. `src/resonance/routes/navidrome.py` exposes create/status operations.
- **Conventions:** Use the existing `request()` helper and `credentials: "same-origin"`; do not read the HttpOnly cookie or call `/api/auth/token`. Vue interpolation escapes lyric content by default; do not use `v-html` for lyrics.
- **Key files:** `vue-ui/src/App.vue`, `vue-ui/src/style.css`, `src/resonance/application/search.py`, `src/resonance/application/playlists.py`, `src/resonance/routes/search.py`, `src/resonance/routes/navidrome.py`, `src/resonance/state.py`.
- **Gotchas:** Search results are one row per complete song and include the matched lyric chunk. Playlist save is idempotent only for the exact caller, operation ID, and request body. A changed request under the same key conflicts. `prepared` and `operation_not_found` can replay the exact request with the same ID because no Navidrome side effect has started. If `submitting` or `unresolved` has no playlist ID, stop and direct the user to manual inspection; never retry under a new ID. When a playlist ID exists, query status for readback reconciliation. A known duplicate-name rejection can be acknowledged by the user and submitted as a new explicit operation.
- **Domain context:** A successful search does not imply playlist consent. The user explicitly chooses and orders song IDs. The server rechecks current library membership and verifies private visibility, owner, name, count, and order before reporting `verified`.
- **Artifact directory:** `/tmp/resonance-prd13-search-playlist-20261026`
- **Test framework constraints:** There is no Vue component test harness. Existing Python route and save-journal integration tests cover API authorization and idempotency. Browser acceptance is required for the Vue workflow. Do not claim live playlist verification unless exercised against Navidrome.

## Runtime Environment

- **Start command:** `make run` in one terminal; `make ui` in another.
- **Port:** FastAPI at `http://localhost:8000`; Vite at `http://127.0.0.1:5173`.
- **Deploy path:** Vue is served by Vite in development and by FastAPI under `/app/` in the production image.
- **Health check:** `curl http://localhost:8000/health`; open `http://127.0.0.1:5173` and authenticate.
- **Restart procedure:** Restart Vite after frontend changes and FastAPI after backend changes. In-memory authentication sessions are lost on FastAPI restart.
- **Code identity:** For packaged acceptance, rebuild the image and verify `/app/` assets come from that image; for local acceptance, Vite serves files from `vue-ui/` and proxies `/api` to port 8000.

## Feature Inventory

| Existing file                       | Function, class, route, or behavior                           | New location                                            | Task or agreed retention |
| ----------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------- | ------------------------ |
| `vue-ui/src/App.vue`                | Login, session refresh, authorized library/collection display | Same component, expanded to discovery workflow          | Tasks 1–3                |
| `vue-ui/src/style.css`              | Existing auth scaffold styles                                 | Extend for search, evidence, selection, and save status | Tasks 1–3                |
| `src/resonance/routes/search.py`    | Caller-authorized semantic search                             | Retain; extend only for a demonstrated contract gap     | Task 1 if required       |
| `src/resonance/routes/navidrome.py` | Caller-scoped playlist create and status                      | Retain; extend only for a demonstrated contract gap     | Task 3 if required       |
| `ui/index.html`                     | Admin ingestion/search PoC                                    | Retain unchanged for this user-workflow slice           | Out of scope             |

## Progress Tracking

- [x] Task 1: Add collection-scoped semantic search and lyric evidence to Vue.
- [x] Task 2: Add explicit candidate selection and ordering.
- [x] Task 3: Add safe private-playlist save and operation reconciliation.
- [/] Task 4: Document and verify the direct user workflow; production build/server smoke passed after final UI changes, full authenticated browser and Navidrome save acceptance awaits operator testing.

**Total Tasks:** 4 | **Completed:** 3 | **Remaining:** 1

## Implementation Tasks

### Task 1: Search an authorized collection

**Objective:** Let the signed-in user search a configured collection with a theme or mood query and inspect ranked matches.

**Dependencies:** None

**Files:**

- Modify: `vue-ui/src/App.vue`, `vue-ui/src/style.css`
- Modify only if needed: `src/resonance/routes/search.py`, `src/resonance/application/search.py`
- Verify: browser workflow against authenticated FastAPI

**Key Decisions / Notes:**

- Use collections already loaded for Navidrome libraries returned by the current session.
- Submit query, collection, optional exact artist, and bounded limit to `POST /api/search`.
- Display title, artist, album when present, score, matched lyric evidence, and section position. Provide clear loading, empty, error, and expired-session states.
- Keep theme/mood text search as the only search mode in this increment; no seed-song semantics or generated query layer.

**Definition of Done:**

- [x] The user can choose only an authorized collection and search with a nonempty theme/mood query.
- [x] Search results show distinct tracks and the matched lyric section without unsafe HTML rendering.
- [x] Empty results, API errors, and expired sessions produce understandable UI states.

**Verify:**

- Existing API route tests remain green if route code changes.
- Browser smoke: log in, search a known query in an authorized collection, inspect evidence, and exercise empty/error states.

### Task 2: Select and order candidates

**Objective:** Give the user control over exactly which search results and order are saved.

**Dependencies:** Task 1

**Files:**

- Modify: `vue-ui/src/App.vue`, `vue-ui/src/style.css`

**Key Decisions / Notes:**

- Track candidates by Navidrome `song_id`, not title/artist, because recordings can share metadata.
- Allow add/remove and move-up/move-down controls; prevent duplicate song IDs and selections beyond the API's 100-track limit.
- Keep selection state separate from search ranking so users may refine a query without silently changing an already selected order.
- Bind the candidate list to its Navidrome `library_id`. Preserve selection across query/collection changes within that library; when switching libraries, require explicit confirmation to clear the old selection before loading results from the new library.
- Require at least one selected candidate and a nonempty playlist name before save is enabled.

**Definition of Done:**

- [x] A user can select, remove, and reorder distinct results and the displayed order matches the pending playlist order.
- [x] The UI prevents empty, duplicate, and over-100 selections before submission.
- [x] Searching again does not silently replace the user's selected playlist candidates.
- [x] A selection cannot mix songs from different libraries; switching libraries requires explicit confirmation before clearing the previous library's selection.

**Verify:**

- Browser smoke: select multiple results, change order, remove one, and confirm the pending order shown before save.

### Task 3: Save and reconcile a private playlist safely

**Objective:** Create a playlist only after explicit user action and accurately handle uncertain outcomes.

**Dependencies:** Task 2

**Files:**

- Modify: `vue-ui/src/App.vue`, `vue-ui/src/style.css`
- Modify only if needed: `src/resonance/routes/navidrome.py`, `src/resonance/application/playlists.py`
- Verify: browser workflow using authenticated Navidrome account

**Key Decisions / Notes:**

- Generate an operation ID for the exact approved request and persist the operation ID plus immutable request in `sessionStorage` before submitting, so a page reload cannot lose an uncertain operation. Never store the auth cookie/token or Navidrome password there.
- Namespace persisted operation state by authenticated username and verify its owner after `/api/auth/me` before restoring it. Never query one user's operation while another user is signed in.
- Post ordered song IDs to `/api/navidrome/playlists`; display verified, failed, submitting, and unresolved states from the response.
- Poll `GET /api/navidrome/operations/{operation_id}?library_id=...` to reconcile a pending operation. Replay the exact request with the same ID only for `prepared` or `operation_not_found`; those states precede any Navidrome create side effect. If a `submitting`/`unresolved` operation has no playlist ID, stop and direct the user to inspect Navidrome manually. Never invent a replacement ID for an unknown outcome. If an operation has a playlist ID, use status readback to reconcile it.
- On a known duplicate-name rejection, explain the collision and require explicit acknowledgement; a changed request uses a new operation ID because the old key is bound to its original payload.
- Disable duplicate submission while a request is active. Do not infer success from an HTTP 200 alone; require `status == "verified"`.

**Definition of Done:**

- [x] No playlist is created until the user explicitly submits a named, ordered selection.
- [x] A verified response shows the resulting operation/playlist identity and selected order.
- [x] A reload or uncertain network response restores the same operation ID/request and checks status before allowing another save.
- [x] Restored operation state is shown only to the Navidrome username that created it; an account switch cannot submit or query the prior user's operation.
- [x] Unknown or unresolved outcomes never trigger a fresh operation automatically; a known duplicate name requires explicit user acknowledgement.

**Verify:**

- Existing `tests/test_navidrome_routes.py` and `tests/test_save_operations.py` cover backend authorization, exact-request idempotency, and reconciliation if backend code changes.
- Browser smoke: create one private playlist from a small explicit selection, confirm verified status and server readback, and exercise duplicate-name and uncertain-operation states where practical.
- Browser smoke: verify selections cannot cross libraries and pending save state from one account is not restored under a second account.

### Task 4: Document and verify the direct user workflow

**Objective:** Make the first-run workflow understandable and capture end-to-end acceptance evidence.

**Dependencies:** Tasks 1–3

**Files:**

- Modify: `README.md`, PRD-13 and this plan
- Verify: packaged frontend build and browser smoke

**Key Decisions / Notes:**

- Document `make run` plus `make ui`; keep admin ingest instructions separate from user discovery.
- Keep FastMCP auth/tool work as a follow-on in PRD-13; do not add a password-taking tool or duplicate search/save policy.

**Definition of Done:**

- [x] README explains login, collection selection, semantic search, candidate ordering, explicit save, and unresolved operation handling.
- [x] Docker production build packages the same workflow under `/app/`.
- [ ] Browser acceptance confirms a verified private playlist owned by the signed-in Navidrome user and containing the approved ordered song IDs.

**Verify:**

- `docker compose build resonance` — production Vue build succeeds.
- Browser acceptance against local FastAPI/Vite and a configured Navidrome account — complete search, review, save, and operation status.

## Testing Strategy

- Existing Python integration tests are the authority for caller/library authorization and playlist operation/reconciliation behavior; add backend tests only if API contracts change.
- Manual browser verification covers login/session continuity, collection scoping, query/result rendering, candidate order, explicit save, and terminal/interrupted operation states.
- Verify at least one actual private playlist by Navidrome readback. Do not claim playback behavior; Resonance does not play audio.
- The frontend has no component test harness. Avoid adding a framework solely for this slice unless implementation reveals a complex behavior that cannot be checked through browser smoke.
- `./node_modules/.bin/vite build` — passed using the installed, lockfile-pinned frontend dependencies.
- `docker compose build resonance` — passed after final reviewer-driven cross-tab identity and completion-summary refinements; Docker's Node 22.13.1/pnpm 9.15.4 stage packaged the current Vue bundle.
- Final production image smoke passed: `GET /app/` returned 200, the referenced compiled JavaScript asset returned 200 (80,822 bytes), and `/app/search` returned 200 through SPA fallback.
- `make ui` local server smoke — Vite started at `127.0.0.1:5173`; a local GET of `/` returned 200 and served the current Vite entry page. Full cookie-authenticated browser interaction and actual playlist save were not performed in this environment.

## Risks and Mitigations

| Risk                                                                       | Likelihood | Impact | Concrete mitigation                                                                                                                  |
| -------------------------------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| UI creates a playlist without clear user approval                          | Low        | High   | Require an explicit named ordered selection and an explicit save action; search never writes.                                        |
| Network loss after Navidrome created the playlist causes a duplicate retry | Med        | High   | Persist exact operation ID/request before POST, reconcile via status endpoint, and block a fresh operation for unresolved outcomes.  |
| User can select a song no longer accessible                                | Low        | Med    | API revalidates exact song IDs against the caller's current library before creation.                                                 |
| Similar titles/artists conflate separate recordings                        | Med        | Med    | Key selected candidates by opaque `song_id`; display album/other metadata where present.                                             |
| MCP adapter later bypasses user library permissions                        | Med        | High   | Keep MCP out of this slice and require its auth design to use the same bearer-authenticated FastAPI contracts before implementation. |

## Removes

- None. The existing `/ui` administrator PoC and API/CLI behavior remain in place.

## Removes (verify)

- None.

## Follow-on FastMCP Scaffold

- The user selected Vue search/review/playlist as the first deliverable so match quality can be tested before MCP tools.
- After that validation, create a minimal FastMCP scaffold using Nool's `FastMCP(..., auth=...)`, tool registration, and ASGI app pattern, and the related Obsidian MCP repository's OAuth-provider structure as references.
- Nool calls its service layer directly and uses a persistent device token; Obsidian MCP has an OAuth 2.1 provider with an interactive personal-token login. Neither auth implementation should be copied unchanged: Resonance must keep Navidrome user identity and library scoping, and must not introduce a shared static user credential.
- The requested path `~/dev/mksg/obsidian-mcp` was absent; the related repository was found at `~/dev/mk/obsidian-mcp`.
- This scaffold is intentionally after the current Vue slice and before full FastMCP search/save tools. Resolve per-user token acquisition and renewal before registering those tools.

## ADR Reference

No ADR anticipated. This extends the existing Vue client and FastAPI contract without changing the shared application architecture. The FastMCP scaffold is a later milestone; user-token acquisition remains a requirement before registering tools.

## Open Questions

- MCP follow-on: how will each MCP host authenticate and renew a user's Resonance identity without exposing Navidrome credentials to the model? The existing token endpoint issues a 12-hour bearer after credential validation but does not define host-side storage or renewal.

### Deferred Ideas

- FastMCP server and user tools, until per-user MCP authentication/token renewal is designed. A minimal scaffold follows user validation of this Vue workflow.
- Seed-song search, LLM-generated queries, conversational context, and automatic playlist generation.
- Admin collection/ingestion workflows, ingestion progress/restart, and full library refresh.
- Playback links or control.
