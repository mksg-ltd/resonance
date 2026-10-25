---
phase: foundation
status: draft
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [authentication, authorization, jwt, navidrome, security]
---

# PRD-12: User Authentication and Authorization Foundation

**Status**: Draft — the user-scoped auth direction is agreed; session credential
handling and the first implementation boundary need design.

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
- Configure a single Resonance administrator by username, for example
  `RESONANCE_ADMIN_USER=admin`. After successful Navidrome authentication, an exact
  match between the authenticated username and this configured value enables admin
  operations. Resonance does not maintain a separate admin account or role database.
- Restrict libraries, collections, search results, lyric reads, and playlist writes to
  the signed-in user's Navidrome permissions.
- Let the admin ingest libraries they can access and configure multiple index
  collections per library, such as different embedding model/provider profiles.
- Keep collection identity bound to the Navidrome server and library, not to the
  username that performed ingestion.

## Non-Goals

- OIDC, OAuth account linking, external identity providers, or a separate Resonance
  username/password database.
- Multi-tenant hosting or a Resonance-managed role and invitation system.
- Third-party media server plugins/APIs or playback control.
- Redesigning the Vue workflows or MCP tool semantics; those live in PRD-13.
- Persisting Navidrome passwords as application profile data.

## User and Admin Authorization Contract

### Login

1. Vue submits the Navidrome username/password to a protected-transport FastAPI login
   endpoint using POST.
2. FastAPI validates the credentials against the configured Navidrome `BASE_URL` using
   the standard Subsonic authentication scheme. A successful `getMusicFolders` call
   both verifies the credentials and returns the user's accessible libraries.
3. FastAPI issues a short-lived, signed Resonance JWT for later API requests. The JWT
   identifies the caller; it must not contain the password or serve as a Navidrome
   credential.
4. FastAPI returns the JWT in an `HttpOnly` cookie. The browser automatically sends it
   with later same-origin API requests; Vue does not read or store the JWT itself.
5. FastAPI retains only the upstream credential/session material it needs to call
   Navidrome as that user, in server-side session state with a bounded lifetime. Logout
   or expiry invalidates the Resonance session. Restart behavior and single-process vs
   shared session storage are design details to resolve before implementation.

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

All protected FastAPI endpoints accept the Resonance JWT as a bearer credential and
resolve a caller context containing the authenticated Navidrome identity, accessible
libraries, and admin capability. Route handlers must not infer caller identity from
request body fields. CLI remains a trusted local operator interface.

FastMCP must use the same authenticated caller context and authorization checks as the
Vue client. It must not use a global admin token for user search or playlist calls.
The details of how a user's Resonance JWT is configured or acquired by MCP clients are
part of PRD-13.

## Implementation Boundary

This PRD's first milestone is the authentication/security vertical slice, before the
full Vue or MCP experience:

1. Remove hard-coded Navidrome username/password settings and create a Navidrome
   client bound to a validated per-user session.
2. Add login/logout/current-session FastAPI endpoints and JWT verification for
   protected routes.
3. Add the configured admin username check and protect admin-only operations.
4. Enforce library/collection filtering on search and user-scoped playlist creation.
5. Prove a regular user cannot access an admin-only library or guessed collection and
   can create a private playlist that belongs to that user and plays in their client.

The first slice should use the Subsonic-compatible path already used by Resonance's
Navidrome client.

## Open Design Questions

- Where should the short-lived upstream user credentials live so every API request can
  authenticate to Navidrome without storing passwords durably? Is an in-memory session
  acceptable for the initial single-process self-hosted service, with re-login after
  restart?
- What signs the Resonance JWT, how long does it live, and how are logout and key
  rotation handled without introducing a large auth framework?
- How is the JWT signing key configured/generated securely with minimal setup?
- How should FastMCP clients obtain and send the same user-scoped Resonance JWT as an
  Authorization bearer token, since they cannot use the Vue browser cookie?
- What should happen when an admin username changes or the configured value is
  missing? Proposed behavior: no user is an admin until it is explicitly configured.
- How should collections be resolved when a user can see a library but the admin has
  indexed multiple profiles for it?

## Acceptance Criteria

- `.env` no longer needs a global Navidrome username or password; it retains the
  Navidrome base URL and a configured admin username.
- Invalid Navidrome credentials fail login and no Resonance JWT is issued.
- A valid login returns the accessible libraries for that Navidrome user and a
  Resonance JWT that protects subsequent API requests.
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
