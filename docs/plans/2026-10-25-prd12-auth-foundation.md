---
status: verified
approved: true
iterations: 0
branch: spec/prd12-auth-foundation
base_branch: main
base_commit: 95539fd0e92bf594318188bda266758be5a36b44
prd: docs/prds/12-auth-foundation.md
created: 2026-10-25
updated: 2026-10-26
author: MK
tags: [authentication, jwt, navidrome, vue, security]
---

# PRD-12 Authentication Foundation Implementation Plan

## Summary

**Goal:** Replace the single global Navidrome login and static operator token with Navidrome-verified user login, caller-scoped Resonance JWT authorization, a configured username-based admin gate, and a small Vue auth scaffold.

**Architecture:** FastAPI validates a user's Subsonic credentials with Navidrome, issues a short-lived Resonance JWT in an HttpOnly cookie for browser calls, and maintains a bounded server-side session for the upstream credential needed by Subsonic. Browser login returns no JWT in JSON; a separate non-browser token exchange returns a bearer token. Both transports resolve the same session. Navidrome remains authoritative for per-user libraries and playlist ownership. The CLI prompts for credentials when a command calls Navidrome. Vue and the existing `/ui` PoC use cookie login.

**Tech Stack:** Existing FastAPI/Pydantic application, Navidrome Subsonic client, Qdrant, Vue 3/Vite, pnpm, Docker multi-stage asset build.

## Scope

### In Scope

- Remove global `NAVIDROME_USER_ID`, `NAVIDROME_USER_PASSWORD`, and `RESONANCE__API_TOKEN` as runtime authorization mechanisms.
- Keep the configured Navidrome base URL; add `RESONANCE_ADMIN_USER` as the sole Resonance admin grant.
- Add cookie-only browser login, a non-browser bearer-token exchange, logout/current-session endpoints, signed Resonance JWT validation, and cookie/bearer authorization.
- Keep user Navidrome credential material server-side only for the bounded session lifetime; do not persist it in JWTs, browser storage, logs, or durable user profiles.
- Apply authentication to protected FastAPI endpoints. Keep browser login, non-browser token exchange, and liveness/health checks public.
- Enforce the logged-in user's accessible library IDs when resolving collections, searching, inspecting tracks/lyrics, and creating playlists. Admin-only operations require the configured username after successful Navidrome login.
- Decouple Qdrant collection source identity from the ingesting username while retaining server/library/profile binding.
- Preserve Navidrome-dependent CLI commands by prompting for credentials at invocation; search-only CLI use does not prompt.
- Add a minimal Vue/Vite app for login, current-session display, accessible libraries and collections, and logout. Keep full search, candidate editing, playlist UI, and MCP implementation in PRD-13.
- Build/serve Vue from the FastAPI origin while migrating the existing static PoC to cookie login and keeping its admin ingest/search workflow available.

### Out of Scope

- OIDC, OAuth, a separate Resonance user/role database, invitations, or multi-tenant hosting.
- Jellyfin API/plugin support, playback, full semantic-generation UI, or MCP server implementation.
- Ingestion job progress/cancellation/restart and full library reconciliation.
- Persistent Navidrome password storage or a durable Resonance login database.
- Removing the existing PoC page or its operator workflow.

## Prerequisites

- PRD-09 is merged to `main`; the current base commit is `95539fd0e92bf594318188bda266758be5a36b44`.
- The configured Navidrome server supports the Subsonic `getMusicFolders` and standard token/salt authentication already used by `NavidromeClient`.
- The operator configures `NAVIDROME_BASE_URL` and optionally `RESONANCE_ADMIN_USER`; no separate Navidrome server-ID environment setting is required. If the admin username is unset, no account has admin access.
- A regular Navidrome account with a restricted library set is available for end-to-end acceptance; a separate multi-user test library/account may be needed.
- Docker is available to run the Vue/Vite build because Node/npm are not installed in the current host environment.

## Context for Implementer

- **Patterns:** `src/resonance/routes/auth.py` currently validates one static bearer token; `src/resonance/navidrome.py` computes Subsonic token/salt and fetches libraries; `src/resonance/application/playlists.py` already revalidates IDs and checks playlist owner/readback.
- **Conventions:** Keep transport policy in `routes/`, orchestration in `application/`, and Navidrome HTTP details in `navidrome.py`. Never accept caller identity, admin capability, collection ownership, or library grants from request bodies.
- **Key files:** `src/resonance/config.py`, `src/resonance/app.py`, `src/resonance/routes/auth.py`, `routes/search.py`, `routes/collections.py`, `routes/ingest.py`, `routes/navidrome.py`, `navidrome.py`, `application/indexing.py`, `application/search.py`, `application/playlists.py`, `state.py`, `ingest.py`, `library.py`, `playlists.py`, `Dockerfile`, `docker-compose.yml`, `ui/index.html`, and current route/client tests.
- **Gotchas:** `/api/search`, `/api/collections`, and `/api/config` are currently unauthenticated; collection deletion is also unprotected. `source_binding()` currently includes the login username. The save journal uses a globally unique operation ID. API routes and CLIs currently construct the Navidrome client from environment credentials. Vite and production assets need a separate path from the current `/ui` mount.
- **Domain context:** Admin ingestion may index libraries the admin can access. Each Qdrant collection is bound to one Navidrome library and embedding/index profile. Any user can see only collections for libraries returned by their own `getMusicFolders`; their searches, lyric reads, and playlist saves must use their own Navidrome identity. Admin recognition is an exact username comparison after Navidrome authentication, not a role database.
- **Artifact directory:** `/tmp/resonance-prd12-auth-foundation-20261025`
- **Verification constraints:** Existing checks use pytest, FastAPI TestClient, mocked Navidrome HTTP, in-memory Qdrant, and SQLite. No browser automation exists. Host Node/npm are absent; Docker is available for the frontend build. Do not claim live multi-user Navidrome acceptance unless the regular account/library permissions are actually exercised.

## Runtime Environment

- **Start command:** `make run` starts FastAPI/Qdrant on port 8000; use the Vue Vite dev server on its configured port with `/api` proxied to FastAPI.
- **Port:** FastAPI 8000; Vite dev server explicitly configured at 5173.
- **Deploy path:** Vue production assets served by FastAPI at `/app/`; existing PoC remains under `/ui`.
- **Health check:** `curl http://localhost:8000/health` returns healthy; `/app/` loads Vue, `/ui` loads the migrated PoC, and browser login stays same-origin through Vite proxy or packaged serving.
- **Restart procedure:** Restart FastAPI and Vite after config/source changes; process restart invalidates any in-memory Navidrome credential sessions, requiring login again.
- **Code identity:** Confirm API responses and asset hashes/content are served from the current checkout/Docker build; do not rely on an old container or the `/ui` bind mount for the Vue bundle.

## Feature Inventory

| Old file                                                | Function, class, route, or behavior                                              | New location                                                                            | Task or agreed removal |
| ------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ---------------------- |
| `src/resonance/config.py`                               | Global `NAVIDROME_USER_ID`, password, and static `RESONANCE__API_TOKEN` settings | Base URL + server config, admin username, JWT config/session                            | Task 1                 |
| `src/resonance/routes/auth.py`                          | `require_operator()` static-token auth and singleton `get_navidrome()`           | Login/session/JWT dependencies and per-user Navidrome client                            | Tasks 1–2              |
| `src/resonance/routes/search.py`                        | Unauthenticated arbitrary-collection search                                      | Authenticated caller and authorized-collection resolution                               | Task 3                 |
| `src/resonance/routes/collections.py`                   | Unauthenticated global list/delete                                               | Caller-filtered collection listing; admin-only deletion                                 | Task 3                 |
| `src/resonance/routes/ingest.py`                        | Static-token operator ingestion                                                  | Configured-admin-only ingestion using the logged-in source                              | Task 3                 |
| `src/resonance/routes/navidrome.py`                     | All native operations behind operator token                                      | User-scoped read/playlist routes; admin-only library/ingest management                  | Task 3                 |
| `src/resonance/navidrome.py`                            | Credential config and source fingerprint include username                        | Explicit user-scoped request client; source identity excludes login username            | Task 1                 |
| `src/resonance/search.py`                               | Search CLI derives source binding from credential-bearing Navidrome config       | Use base-URL-only stable source binding without prompting or requiring user credentials | Task 1                 |
| `src/resonance/ingest.py`, `library.py`, `playlists.py` | CLI reads `.env` Navidrome user/password                                         | Interactive username/password prompt for Navidrome-dependent commands                   | Task 4                 |
| `ui/index.html` and `/ui` mount                         | Existing operator ingestion/search PoC using a static token                      | Replace token entry with cookie login while retaining ingest/search workflows           | Task 6                 |
| Docker build                                            | Copies Python sources only                                                       | Build Vue assets and serve with FastAPI                                                 | Task 7                 |

## Progress Tracking

- [x] Task 1: Refactor Navidrome client and stable collection identity around explicit user credentials.
- [x] Task 2: Add user login/session/JWT cookie and bearer authorization.
- [x] Task 3: Protect routes and enforce per-user library/collection access and admin username policy.
- [x] Task 4: Preserve Navidrome-dependent CLI behavior with secure prompts.
- [/] Task 5: Add minimal Vue/Vite login and accessible-library/collection scaffold; browser interaction smoke remains.
- [/] Task 6: Migrate the existing HTML PoC to cookie authentication; browser interaction smoke remains.
- [x] Task 7: Build and serve Vue assets same-origin while retaining `/ui` PoC.
- [x] Task 8: Update configuration and operator documentation for the new auth flow.

**Total Tasks:** 8 | **Completed:** 8 | **Remaining:** 0

## Implementation Tasks

### Task 1: User-scoped Navidrome client and stable source identity

**Objective:** Decouple Navidrome credentials from global settings and collection identity from the user who indexed it.

**Dependencies:** None

**Files:**

- Modify: `src/resonance/config.py`, `src/resonance/navidrome.py`, `src/resonance/application/indexing.py`, `src/resonance/search.py`
- Test: `tests/test_config.py`, `tests/test_navidrome.py`, `tests/test_indexing.py`

**Key Decisions / Notes:**

- Make user identity/password explicit input to a request-scoped Navidrome client.
- Validate login by calling `getMusicFolders`; use returned libraries as the Navidrome authorization source.
- Change source identity to a canonicalized `NAVIDROME_BASE_URL`, independent of username. Keep library/profile identity in separate metadata fields. For existing collections, migrate only the reserved metadata point when its exact legacy fingerprint can be reproduced from the configured base URL and prior admin username (`SHA-256(base_url + NUL + username)`). Preserve vector points; when proof is unavailable or mismatched, return a clear reingest/new-collection conflict without changing data.

**Definition of Done:**

- [x] Navidrome client requests use explicitly authenticated user credentials and no longer require user/password from `.env`.
- [x] Source binding is stable across users on the same Navidrome instance and still distinguishes server/library/profile.
- [x] The search CLI can resolve that binding with `NAVIDROME_BASE_URL` alone and makes no Navidrome credential prompt or HTTP request.
- [x] A bad username/password is rejected by Navidrome before a caller session is created; route tests verify generic 401 and no session/cookie.
- [x] A proven legacy collection migration updates only metadata point `id=0`; section/vector point IDs and count remain unchanged, repeat migration is idempotent, and an unproven legacy fingerprint returns 409 without changing any point.

**Verify:**

- `UV_CACHE_DIR=/tmp/resonance-uv-cache uv run pytest tests/test_config.py tests/test_navidrome.py tests/test_indexing.py tests/test_save_operations.py -q` — 52 passed, including stable identity and proof-gated metadata migration with unchanged point IDs/count.

### Task 2: JWT login, cookie session, and caller context

**Objective:** Establish browser cookie authentication and bearer authentication for non-browser API clients.

**Dependencies:** Task 1

**Files:**

- Modify: `pyproject.toml`, `src/resonance/config.py`, `src/resonance/app.py`, `src/resonance/routes/auth.py`
- Create: `src/resonance/auth.py` or `src/resonance/application/auth.py`
- Test: `tests/test_auth.py`, `tests/test_auth_routes.py`

**Key Decisions / Notes:**

- Add `POST /api/auth/login`, `POST /api/auth/token`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Browser login accepts username/password in the POST body and sets a short-lived HttpOnly JWT cookie. It never includes the JWT in its JSON response. `/api/auth/token` is a credential-authenticated bearer-token issuance route available to any HTTP client; it returns the JWT in its response body. Client type cannot be enforced by the server, so Vue must never call this route.
- Keep upstream credential material in a bounded process-local session store with a fixed 12-hour lifetime and 128 active-session capacity, never JWT claims. Logout removes/revokes that session. At capacity, do not evict active sessions; return 503 with `Retry-After` and create no session. Generate a random signing key at process startup, pin the algorithm, and validate issuer, audience, expiry, and session ID. Require one worker; restart invalidates sessions and requires login again. Make session-store operations safe under concurrent requests.
- Return the same generic authentication failure for unknown users and wrong passwords. Apply one shared rate limiter to failed credential attempts on both credential endpoints: 5 failures per source IP per rolling 5 minutes, return 429 with `Retry-After`, and cap limiter state (evict expired buckets; return 503 with `Retry-After` rather than bypassing the limit if full). Use the ASGI peer address unless a trusted proxy is explicitly configured; ignore arbitrary forwarded-IP headers.
- Use `Secure` in production, `SameSite=Lax`, cookie path `/api`, and Origin validation for login and unsafe cookie-authenticated requests. Reject cross-origin credentialed calls. Bearer-authenticated calls do not use cookie CSRF checks.
- Reject credential and protected API requests unless the effective request scheme is HTTPS, except explicit local-development requests while debug mode is enabled. For Compose local HTTP, bind the published API port to host `127.0.0.1`, allow Host `localhost`/`127.0.0.1`, and allow only these exact origins: `http://localhost:8000`, `http://127.0.0.1:8000`, `http://localhost:5173`, and `http://127.0.0.1:5173`. Behind a TLS-terminating proxy, trust forwarded scheme only from explicitly configured Uvicorn `forwarded-allow-ips`; require the proxy to preserve an accepted Host and reject unknown Host values. In production, allow cookie requests only when Origin exactly matches the effective HTTPS scheme and accepted Host. Never honor arbitrary forwarded headers.
- Load `RESONANCE_ADMIN_USER` through an explicit Pydantic environment alias (the application settings prefix otherwise expects `RESONANCE__...`).

**Definition of Done:**

- [x] Invalid Navidrome credentials receive the same generic 401 and no cookie/session; both credential endpoints share the 5-failures/5-minute per-IP limit and return 429 with `Retry-After` when exceeded. Limiter saturation fails closed with 503.
- [x] Remote plaintext HTTP login/token and protected API requests are rejected; host-published Compose HTTP is reachable only through `127.0.0.1` with one of the four documented local origins and debug enabled; reverse-proxy HTTPS works only when the proxy address is trusted and its Host is accepted.
- [x] At 128 active sessions, further valid logins fail with 503 and `Retry-After` without evicting a live session.
- [x] The exact `RESONANCE_ADMIN_USER` environment key loads; an unset/empty value grants no admin capability.
- [x] Valid login returns user identity/libraries and sets the cookie without exposing it to Vue JavaScript.
- [x] Cookie and bearer calls resolve the same caller; expired, revoked, or logged-out tokens fail. Browser login returns no token in readable JSON; `/api/auth/token` returns a token to any caller that authenticates successfully, and Vue never calls it.
- [x] Password, upstream credential, and session material are absent from JWT claims, errors, and logs.

**Verify:**

- `uv run pytest tests/test_auth.py -q` — login/cookie/session cases pass.

### Task 3: Per-user route authorization and admin username gate

**Objective:** Ensure every protected API response and write respects the authenticated Navidrome user.

**Dependencies:** Task 2

**Files:**

- Modify: `src/resonance/routes/search.py`, `routes/collections.py`, `routes/config.py`, `routes/ingest.py`, `routes/navidrome.py`, `application/search.py`, `application/playlists.py`, `state.py`
- Test: `tests/test_routes.py`, `tests/test_navidrome_routes.py`, `tests/test_save_operations.py`

**Key Decisions / Notes:**

- Public endpoints are browser login, bearer-token exchange, and liveness/health checks; static app assets are public, data/config endpoints are authenticated.
- Compare authenticated username to `RESONANCE_ADMIN_USER` for admin operations; never trust a client-supplied role.
- Resolve visible collections server-side and filter by current Navidrome library grants. Reject guessed inaccessible collection/library identifiers without revealing contents.
- Use the logged-in Navidrome client for lyrics, exact song revalidation, playlist creation, and playlist readback.
- Include caller identity in save-operation binding; preserve existing idempotency/readback behavior.
- Resolve existing account-bound collection metadata without deleting/re-embedding vectors; perform an idempotent metadata-point-only migration only when the exact prior hash can be proven. Otherwise return a precise reingestion/new-collection message.
- Migrate existing SQLite save-journal bindings only when `caller == "operator"`, source ID/library match, and the legacy source fingerprint exactly matches `SHA-256(base_url + NUL + RESONANCE_ADMIN_USER)`. Preserve operation IDs, request data/hash, status, playlist ID, and reason while changing only caller/source binding. If an unresolved legacy operation cannot be proven, block new playlist-save operations with a clear 409 requiring reconciliation; do not discard or retry it with a new ID.

**Definition of Done:**

- [x] Unauthenticated requests to search, collections, config, Navidrome reads, ingest, and playlist routes fail before external side effects.
- [x] Only authenticated username matching `RESONANCE_ADMIN_USER` can ingest/delete collections.
- [x] A user granted libraries B/C sees only collections for B/C and cannot get results/metadata from library A by guessing identifiers.
- [x] A user playlist is created and verified as owned/private under that user's Navidrome identity.
- [x] One user's operation ID/status cannot disclose or resume another user's operation.
- [x] Proven legacy save rows migrate idempotently without changing status/playlist ID; an unproven unresolved row remains intact and blocks new playlist saves with a clear conflict.

**Verify:**

- `uv run pytest tests/test_routes.py tests/test_navidrome_routes.py tests/test_save_operations.py -q` — route permission and save behavior pass.

### Task 4: CLI credential prompts

**Objective:** Keep Navidrome-dependent CLI commands usable after removing global credentials.

**Dependencies:** Task 1

**Files:**

- Modify: `src/resonance/ingest.py`, `src/resonance/library.py`, `src/resonance/playlists.py`
- Create/Modify: shared terminal credential prompt helper under `src/resonance/`
- Test: existing CLI tests and new prompt cases as needed

**Key Decisions / Notes:**

- Use masked password input and username input at invocation time; do not accept a password argument.
- A non-interactive invocation without another secure credential source fails with a clear message.
- Preserve CLI/application boundary; no HTTP calls or subprocess calls are introduced to authenticate local CLI operations.

**Definition of Done:**

- [x] Ingest/library/playlist commands authenticate as the prompted Navidrome user.
- [x] Search-only command does not request Navidrome credentials.
- [x] Credentials are not written to logs, shell history, or files.

**Verify:**

- `uv run pytest tests/test_search_cli.py` plus focused CLI invocations — search remains non-interactive and native commands request credentials.

### Task 5: Minimal Vue authentication scaffold

**Objective:** Provide the browser login/session client needed to exercise PRD-12.

**Dependencies:** Task 2 and Task 3 API contracts

**Files:**

- Create: `vue-ui/package.json`, `vue-ui/pnpm-lock.yaml`, Vite config, Vue app/components/styles
- Modify: `.gitignore`
- Test: manual browser smoke flow; no existing JS test harness

**Key Decisions / Notes:**

- Keep this scaffold limited to login, current user/admin indicator, permitted libraries and their configured collections, and logout.
- Use same-origin `/api` requests; browser must not read the JWT cookie.
- Show multiple collections per authorized library with provider/model labels.
- Use Vite on port 5173, proxy `/api` to FastAPI port 8000, and never call `/api/auth/token` from Vue. Treat this as client behavior; the API cannot identify a trusted client type.
- Do not add semantic search, candidate editing, ingestion controls, or playlist authoring here.

**Definition of Done:**

- [x] Login succeeds/fails with clear feedback; refresh preserves session if cookie is valid.
- [x] Current session view shows the authenticated username and admin capability.
- [x] Library/collection choices include only server-authorized entries.
- [x] Logout clears the cookie/session and protected data is no longer accessible.

**Verify:**

- `pnpm --dir vue-ui build` — production Vue assets compile.
- Browser smoke against the configured local server — login, session refresh, library/collection display, logout.

### Task 6: Migrate the existing HTML PoC to cookie authentication

**Objective:** Keep the current admin ingestion/search workflow usable after static-token authorization is removed.

**Dependencies:** Task 2 and Task 3

**Files:**

- Modify: `ui/index.html`
- Verify: Existing `/ui` behavior against the authenticated API

**Key Decisions / Notes:**

- Replace the operator-token field/storage/header with login/logout using the HttpOnly cookie.
- Keep existing library selection, ingestion, and search interactions; remove no current PoC workflow.
- Use same-origin requests and surface expired-session responses by returning the user to login.

**Definition of Done:**

- [x] The page has no static API-token entry or localStorage token handling.
- [x] After cookie login, existing library, ingest, and search actions call the protected API successfully.
- [x] Logout and expired sessions make protected actions inaccessible until another login.

**Verify:**

- Browser smoke against `/ui`: login, list libraries, ingest a small selected set, search, logout.

### Task 7: Same-origin Vue build and serving

**Objective:** Integrate the Vue bundle without disrupting the existing `/ui` PoC.

**Dependencies:** Task 5

**Files:**

- Modify: `Dockerfile`, `src/resonance/app.py`, `docker-compose.yml`, `.dockerignore`
- Test: Docker build and health/UI smoke checks

**Key Decisions / Notes:**

- Add a Node/pnpm build stage with lockfile-pinned Node/pnpm versions, copy built assets into the runtime image, and serve at `/app/`.
- Keep `/ui` static PoC mounted separately.
- Configure Vite proxy for `/api` in development and avoid credentialed cross-origin CORS for the Vue flow.
- Ensure SPA fallback handles app routes but does not swallow `/api` or `/health`.

**Definition of Done:**

- [x] Production image serves Vue assets and FastAPI API from one origin.
- [x] Existing `/ui` PoC remains available; Compose publishes local debug HTTP only on host loopback, while production deployments can use a separately configured HTTPS reverse proxy.
- [x] `/app/*` frontend paths fall back to Vue entry while `/api`, `/ui`, and `/health` routes retain their own responses.

**Verify:**

- `docker compose build resonance` — image builds with lockfile-pinned frontend dependencies.
- Container smoke — `/app/` returns Vue HTML, `/ui` returns PoC HTML, `/health` returns healthy.

### Task 8: Configuration and operator documentation

**Objective:** Document login and retire global credential instructions.

**Dependencies:** Tasks 1–7

**Files:**

- Modify: `.env.example`, `README.md`, `CLAUDE.md`, PRD-12
- Test: docs/link/config review

**Definition of Done:**

- [x] `.env.example` documents the base URL, optional admin username, and no global Navidrome credentials or persistent JWT signing secret. The JWT key is generated at startup and rotates on restart.
- [x] README documents Vue dev and packaged workflows, login, admin username matching, CLI prompts, and session restart/logout behavior.
- [x] Docs distinguish cookie login, non-browser token exchange, protected data endpoints, public health checks, and cookie CSRF behavior.

**Verify:**

- `git diff --check` and repository formatting hooks pass.

## Testing Strategy

- Unit: JWT signing/expiry/claims and session-store expiry/revocation.
- Integration: mocked Navidrome authentication, per-user `getMusicFolders`, Qdrant collection resolution, playlist owner/readback, and save-journal isolation.
- Execution: use two Navidrome accounts with overlapping/different libraries; verify admin collection availability and user access boundaries.
- E2E: Vue login/session/logout in browser; verify HttpOnly cookie behavior and same-origin calls. Manual real-server playlist test only with explicit test playlist/account.
- Frontend build: Docker Node 22.13.1 + pnpm 9.15.4 lockfile build passed. Runtime smoke returned 200 for `/app/`, both referenced `/app/assets/*` files, `/ui/`, and `/health`; unauthenticated `/api/auth/me` and `/api/collections` returned 401.
- Final full suite: `docker run --rm resonance-prd12-tests uv run pytest -q` — 102 passed. It ran in a temporary Python 3.14 container because the host sandbox's TestClient threadpool hangs.
- Static checks: Ruff passed on `src/resonance` and new/changed auth-focused tests; `ty check src/resonance` passed; `git diff --check` passed.
- Operator-reported browser smoke on 2026-10-26 passed: Vue login/session refresh/authorized library and collection display/logout, plus `/ui` login/library selection/small ingestion/search/logout.
- Live access restriction with a separate non-admin Navidrome account and a real private playlist playback check were not separately exercised. Automated route tests cover restricted-library filtering and private playlist ownership/readback under a mocked Navidrome server.
- Compliance and quality reviews found no implementation blocker; the compliance review's two browser-smoke findings are resolved by the operator-reported run.

## Risks and Mitigations

| Risk                                                                                      | Likelihood | Impact | Concrete mitigation                                                                                                                                                                                                        |
| ----------------------------------------------------------------------------------------- | ---------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Session JWT identifies user but API uses admin Navidrome client                           | Med        | High   | Build per-request Navidrome client from server-side authenticated session and test source calls under each account.                                                                                                        |
| Cookie auto-sent cross-site request causes CSRF                                           | Med        | High   | Same-origin deployment, explicit SameSite, CSRF token/Origin checks on mutations.                                                                                                                                          |
| Credentials or bearer tokens travel over plaintext HTTP                                   | Med        | High   | Reject remote HTTP based on effective ASGI scheme; allow Compose debug HTTP only on a loopback-bound host port with a local Host/Origin, and honor forwarded HTTPS only from Uvicorn's explicitly trusted proxy addresses. |
| Legacy pending playlist operations become unreachable after caller/source binding changes | Low        | High   | Migrate rows only from proven legacy source/admin bindings; preserve unknown rows and block new saves if any unresolved row cannot be proven.                                                                              |
| In-memory session disappears on restart or mismatches multi-worker deployment             | High       | Med    | Document single-process mode, short TTL, require re-login; fail closed if `jti` session missing.                                                                                                                           |
| User guesses another library's collection name                                            | Med        | High   | Resolve collection/library authorization server-side before Qdrant access and return non-disclosing 404/403.                                                                                                               |
| Existing collections fail new account-independent source binding                          | Med        | Med    | Add safe metadata migration for matching source/library; never silently delete/re-embed; provide explicit reingestion guidance if unprovable.                                                                              |
| No Node/npm on implementation host                                                        | High       | Med    | Build Vue through pinned Node/pnpm Docker stage; report if image build cannot fetch dependencies.                                                                                                                          |
| CLI breaks after environment credential removal                                           | Med        | Med    | Add secure per-invocation username/password prompts and explicit non-TTY errors.                                                                                                                                           |

## Removes

- Global `NAVIDROME_USER_ID` and `NAVIDROME_USER_PASSWORD` settings.
- Static `RESONANCE__API_TOKEN` as the protected API authorization mechanism.
- Insecure unauthenticated access to search, collection/config reads, or collection deletion.

### Removes (verify)

- Existing account-bound collection fingerprint behavior; preserve or migrate all currently valid native collections.

## ADR Reference

No ADR anticipated: this keeps the established shared application boundary and chooses Navidrome Subsonic authentication. Reconsider if auth requires a separate identity service or durable session backend.

## Open Questions

- Live multi-user acceptance requires the user's restricted Navidrome account/library setup; do not claim this unless exercised.

### Deferred Ideas

- Persistent user sessions across app restarts or multiple workers.
- Multiple Resonance administrators, role tables, invitations, OIDC, OAuth, or multi-server support.
- PRD-13 search/theme generation, candidate review/editing, full playlist UI, and MCP transport.
- Ingestion progress, cancellation, and full refresh/reconciliation.
