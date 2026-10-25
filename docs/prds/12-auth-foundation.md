---
phase: foundation
status: complete
created: 2026-10-25
updated: 2026-10-26
completed: 2026-10-26
spec_branch: spec/prd12-auth-foundation
author: MK
tags: [authentication, authorization, jwt, navidrome, security]
---

# PRD-12: User Authentication and Authorization Foundation

**Status**: Complete — authentication, authorization, CLI credential prompts, and the
minimal Vue scaffold are implemented. Operator browser smoke passed; live multi-user
Navidrome restriction and playback acceptance remain an operational follow-up.

**Purpose**: Replace the single hard-coded Navidrome account and operator bearer token
with login using each user's Navidrome username/password and JWT authorization for
Resonance APIs. This is the foundation for both the Vue application and MCP in
[PRD-13](13-assistant-user-experience.md).

## Problem

Resonance currently calls Navidrome through credentials configured in `.env`. If those
credentials can see more libraries than the person using Resonance, search can return
tracks the person cannot play. A playlist created using the configured account may
also be owned by the wrong Navidrome user.

Resonance needs to identify each caller as their authenticated Navidrome user and
carry that user's permissions through every API operation.

## Goals

- Let a person log in using their own Navidrome username and password.
- Issue a Resonance JWT for subsequent FastAPI calls; all protected API requests use
  this JWT and resolve to the authenticated Navidrome user.
- Replace the single shared `RESONANCE__API_TOKEN` authorization model with
  user-specific JWT authorization for protected HTTP APIs.
- Use the standard Navidrome Subsonic/OpenSubsonic API for user authentication and
  authorization.
- Remove `NAVIDROME_USER_ID` and `NAVIDROME_USER_PASSWORD` from `.env`. Retain
  `NAVIDROME_BASE_URL` as the Navidrome server connection setting.
- Preserve Navidrome-dependent CLI operations by prompting for a Navidrome username
  and password at invocation time; do not add password flags or persistent CLI login
  storage. Search-only CLI operations should not prompt when they do not call Navidrome.
- Configure a single optional Resonance administrator by username, for example
  `RESONANCE_ADMIN_USER=admin`. After successful Navidrome authentication, an exact
  match between the authenticated username and this configured value enables admin
  operations. Resonance does not maintain a separate admin account or role database.
- Restrict libraries, collections, search results, lyric reads, and playlist writes to
  the signed-in user's Navidrome permissions.
- Include a minimal Vue/Vite scaffold to exercise login, session status/logout, and
  the signed-in user's accessible libraries and configured collections. Keep the
  existing static PoC available separately and update it to use the new login so its
  current admin ingest/search workflow remains usable during the transition.
- Let the admin ingest libraries they can access and configure multiple index
  collections per library, such as different embedding model/provider profiles.
- Keep collection identity bound to the Navidrome server and library, not to the
  username that performed ingestion.

## Non-Goals

- OIDC, OAuth account linking, external identity providers, or a separate Resonance
  username/password database.
- Multi-tenant hosting or a Resonance-managed role and invitation system.
- Third-party media server plugins/APIs or playback control.
- Full search, candidate review/editing, and playlist creation UI; those live in PRD-13.
- Persisting Navidrome passwords as application profile data.

## User and Admin Authorization Contract

### Login

1. Vue submits the Navidrome username/password to a protected-transport FastAPI login
   endpoint using POST. Browser login sets the JWT cookie and does not return the JWT
   in readable response data.
2. FastAPI validates the credentials against the configured Navidrome `BASE_URL` using
   the standard Subsonic authentication scheme. A successful `getMusicFolders` call
   both verifies the credentials and returns the user's accessible libraries.
3. FastAPI issues a short-lived, signed Resonance JWT for later API requests. The JWT
   identifies the caller; it must not contain the password or serve as a Navidrome
   credential.
4. Browser login sets the JWT in an `HttpOnly` cookie and does not include it in
   readable response data. The browser automatically sends it with later same-origin
   API requests; Vue does not read or store the JWT itself. `POST /api/auth/token`
   returns a JWT in JSON for bearer clients using the same credential validation and
   session rules; the endpoint cannot enforce client type, so Vue must not call it.
5. FastAPI retains only the upstream credential/session material it needs to call
   Navidrome as that user, in a bounded 12-hour process-local session store capped at
   128 active sessions. Logout or expiry invalidates the Resonance session. A service
   restart requires users to log in again; run one FastAPI worker until a shared
   session store is introduced. At capacity, reject new logins rather than evicting an
   active session.

Passwords and reusable upstream authentication values must not be returned to Vue,
placed in browser storage, embedded in JWT claims, or written to logs. Login attempts
must be rate-limited and credential submission must use HTTPS except for explicitly
trusted local development.

Set the browser cookie with `HttpOnly`, `Secure` in production, an explicit `SameSite`
policy, a narrow path, and a short expiration. Protect state-changing cookie-authenticated
requests against CSRF. Prefer serving the built Vue app and FastAPI from the same origin;
for local Vite development, proxy API paths through the Vite dev server. If the UI and
API must use different origins, configure credentialed CORS for the exact UI origin and
include CSRF protection.

### Admin recognition

After Navidrome accepts the login, Resonance compares the authenticated username to
`RESONANCE_ADMIN_USER`. A matching user may access admin-only library discovery,
collection configuration, and ingestion endpoints. Non-matching users receive a
forbidden response for those operations. The client cannot request or assert the admin
role itself.

This is intentionally a simple single-admin configuration, not a hidden service
account. The configured username grants Resonance's admin features only after the
caller proves control of that same Navidrome account by logging in successfully.

### Library and collection isolation

- Treat Navidrome as the authority for accessible libraries. Derive a user's library
  set from their authenticated `getMusicFolders` response, refreshing it per request
  or using a short-lived cache. Recheck immediately before playlist creation.
- Resolve user-visible collections server-side from their authorized library IDs.
  Never trust a submitted Qdrant collection name or library ID without checking its
  source/library metadata against the caller's access.
- Apply library constraints in the application/Qdrant search path. Hiding a collection
  selector in Vue is not authorization. Guessing an admin-only collection must not
  reveal its results, IDs, metadata, or lyric excerpts.
- Before saving a playlist, revalidate each selected Navidrome song ID as the logged-in
  user. Create the private playlist using that same user's Navidrome identity and
  verify playlist owner, visibility, and ordered contents.
- Bind save-operation records to the caller's Navidrome identity so one user cannot
  inspect or resume another user's operation.

### Shared API authorization

All protected FastAPI endpoints resolve a caller context containing the authenticated
Navidrome identity, accessible libraries, and admin capability. The Vue browser sends
the JWT cookie automatically; non-browser clients send the same JWT as a bearer token.
Both use the same JWT validation. Browser login is cookie-only so JavaScript never
receives the token. `POST /api/auth/token` returns a bearer token in its response body
and uses the same credential validation and session store. It cannot enforce a client
type; Vue must never call it. Route handlers must not infer caller identity from
request body fields. Public exceptions are limited to login, token exchange, and
liveness/health checks.

The CLI remains a trusted local interface but uses interactive Navidrome credentials
for commands that access Navidrome. It calls shared application operations directly
and does not need a Resonance HTTP JWT.

FastMCP must use the same authenticated caller context and authorization checks as the
Vue client. It must not use a global admin token for user search or playlist calls.
`POST /api/auth/token` establishes the PRD-12 bearer contract; it uses the same
credential validation, session creation, and rate limit as browser login, but returns
the JWT in JSON instead of a cookie. PRD-13 decides how FastMCP stores/configures the
user's Navidrome credentials and acquires that token.

## Implementation Boundary

This PRD's first milestone is the authentication/security vertical slice, before the
full Vue or MCP experience. It includes a minimal Vue client so the browser login and
cookie flow are exercised end to end:

1. Remove hard-coded Navidrome username/password settings and create a Navidrome
   client bound to a validated per-user session.
2. Add login/logout/current-session FastAPI endpoints and JWT verification for
   protected routes.
3. Add the configured admin username check and protect admin-only operations.
4. Enforce library/collection filtering on search and user-scoped playlist creation.
5. Prove a regular user cannot access an admin-only library or guessed collection and
   can create a private playlist that belongs to that user and plays in their client.
6. Add a Vue/Vite login scaffold that displays session state, accessible libraries,
   and the configured collections within those libraries; provide logout.
7. Update Navidrome-dependent CLI commands to prompt for credentials so removing the
   global `.env` account does not break existing operator workflows.
8. Adapt the existing static PoC to cookie login and preserve its ingestion/search
   workflow until the Vue app replaces it.

The first slice should use the Subsonic-compatible path already used by Resonance's
Navidrome client.

## Initial Session and Token Decisions

- Store upstream Navidrome credentials only in a bounded, process-local session store
  with a fixed 12-hour lifetime and capacity of 128 active sessions. At capacity,
  reject new logins with 503 and `Retry-After`; never evict a live session. Apply a
  shared limit of 5 failed attempts per source IP per rolling 5 minutes to login and
  token exchange. Return 429 with `Retry-After` when exceeded, and fail closed with
  503 if limiter storage is full. Use generic authentication errors for unknown users
  and wrong passwords. A service restart invalidates all sessions, requiring login
  again. Run one FastAPI worker until a shared session store is deliberately
  introduced; missing session state always fails closed.
- Sign short-lived JWTs using a random key generated at process startup. This avoids
  requiring another secret in `.env`; restarting rotates the key and invalidates prior
  tokens along with the in-memory sessions. Pin the accepted algorithm and validate
  issuer, audience, expiry, and session ID.
- Browser login sets an HttpOnly cookie and returns only safe user/session information.
  `POST /api/auth/token` returns the JWT in JSON for bearer clients; Vue uses the cookie
  flow and receives no token in response data. The endpoint cannot distinguish trusted
  MCP/CLI callers from browsers, so Vue's avoidance is a client rule.
- If `RESONANCE_ADMIN_USER` is unset or empty, no user is an admin. Admin status is
  recalculated from the authenticated session username, not stored in the JWT as an
  authority claim.
- Load `RESONANCE_ADMIN_USER` using an explicit environment alias because the current
  Pydantic settings prefix otherwise expects `RESONANCE__ADMIN_USER`.
- Require HTTPS for remote credential and protected API requests. Permit plaintext
  for local development only: in debug mode, bind the Compose-published API port to
  host loopback, accept Host `localhost`/`127.0.0.1`, and allow only the exact local
  origins `http://localhost:8000`, `http://127.0.0.1:8000`, `http://localhost:5173`,
  and `http://127.0.0.1:5173`. Behind a TLS-terminating reverse proxy, accept the
  forwarded HTTPS scheme only from Uvicorn's explicitly configured trusted proxy IPs;
  require the proxy to preserve an accepted Host and reject unknown Host values. In
  production, require Origin to match the effective HTTPS scheme and accepted Host;
  ignore forwarded headers from other peers.
- Migrate existing playlist-save journal bindings only when the legacy operator,
  library/source ID, and exact old username-derived fingerprint are proven to match
  the configured admin. Preserve all operation data/status. If an unresolved legacy
  operation cannot be proven, leave it intact and block new saves with a clear conflict
  until it is reconciled; never retry it under a new operation ID automatically.
- A library may have multiple collections; list each accessible collection under its
  library with its embedding profile/provider label. The backend filters this response.

## Acceptance Criteria

- `.env` no longer needs a global Navidrome username or password; it retains the
  Navidrome base URL and may include `RESONANCE_ADMIN_USER` to grant one authenticated
  Navidrome user admin features.
- Invalid Navidrome credentials fail login and no Resonance JWT is issued.
- A valid browser login returns the accessible libraries for that Navidrome user and
  sets a Resonance JWT cookie that protects subsequent API requests. A bearer token is
  returned only by `POST /api/auth/token`.
- The Vue scaffold can log in, request current session/libraries/collections without
  reading the HttpOnly JWT, and log out. The build is served through a same-origin path
  in the application; Vite proxies API requests during development.
- The existing `/ui` PoC uses the login cookie instead of the removed operator token
  and still supports its current library, ingestion, and search workflow.
- Navidrome-dependent CLI commands prompt securely for credentials; they neither read
  a global Navidrome username/password from `.env` nor accept passwords in command-line
  arguments. Search-only CLI use does not prompt for Navidrome credentials.
- A user whose username matches `RESONANCE_ADMIN_USER` gains admin operations only
  after successful Navidrome authentication. A different authenticated username
  cannot access admin routes by submitting a role or username in request data.
- A regular user with access to libraries B and C sees only configured collections
  for B and C, even if an admin has indexed library A too.
- Direct requests naming an inaccessible library or collection return an authorization
  failure without disclosing whether hidden tracks exist.
- Search, lyrics, and playlist operations use the authenticated user's Navidrome
  identity; playlist readback confirms that user is the owner and the playlist is
  private with the approved ordered song IDs.
- A revoked or expired Resonance JWT cannot access protected API endpoints.
- Remote HTTP requests to credential and protected API endpoints are rejected. Local
  Compose HTTP is available only on a loopback-bound host port with the explicit
  localhost Host/Origin and debug mode; forwarded HTTPS is trusted only from configured
  proxy IPs.
- Existing save-journal rows migrate only when the former operator/source binding is
  proven to match the configured admin. Operation IDs, statuses, request data, and
  playlist IDs are preserved. An unproven unresolved operation remains intact and
  blocks new playlist saves with a clear conflict until reconciled.
- A proven legacy Qdrant collection migration changes only metadata point `id=0`;
  section/vector point IDs and counts remain unchanged, the migration is idempotent,
  and an unproven fingerprint returns a conflict without changing the collection.
- Passwords and reusable upstream credentials do not appear in JWT claims, browser
  storage, request logs, or error responses.

## Dependencies and Follow-On Work

- [PRD-09](09-navidrome-semantic-playlists.md) supplies the Navidrome ingestion,
  per-library collection metadata, search, and private playlist operations to secure.
- [PRD-13](13-assistant-user-experience.md) consumes the login/session and
  authorization foundation for its Vue and FastMCP clients.
- Ingestion progress, cancellation, restart, and full per-library refresh are separate
  admin workflow work.

## References

- [Navidrome multi-library permissions](https://www.navidrome.org/docs/usage/features/multi-library/)
- [Navidrome Subsonic API compatibility](https://www.navidrome.org/docs/developers/subsonic-api/)
