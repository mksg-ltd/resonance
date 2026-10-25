---
phase: discovery
status: draft
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [assistant, mcp, vue, api, playlists, navidrome]
---

# User Search and Playlist Experience: Vue UI and MCP

**Status**: Early draft — direct Vue experience and MCP use case recorded; workflows,
API contracts, authentication, and first-release scope remain open.

**Relationship to PRD-09**: PRD-09 is complete for the single-account Navidrome
backend and local operator search/ingestion PoC. This PRD captures the evolving direct
user experience, Vue UI, and MCP tools. It does not reopen or extend PRD-09.

## Product Intent

Let someone find songs in their Navidrome library that relate to a mood, theme, or
other context, review the matches, and create a private playlist. They can do this
directly in the Vue application or ask an LLM to do it through MCP tools. A compatible
music client or separate playback integration can then play that playlist. Resonance
does not stream or control playback.

In the direct UI, the user enters a theme or mood. In assistant use, the LLM may use
relevant conversation context and send a structured request through MCP. Both paths
use the same FastAPI contracts and return the same kind of grounded search results.
Search results are suggestions based on lyric similarity, not definitive
interpretations of a song's meaning.

## Product Boundary

- **Administration:** configure the Navidrome connection and embedding service; choose
  a library; create and ingest a search collection; later monitor and refresh ingestion.
- **User discovery:** search by theme, mood, seed song, or other user-approved context;
  receive distinct tracks with relevant lyric evidence.
- **Playlist action:** create a private Navidrome playlist from an explicit ordered
  selection after clear user intent/approval.
- **Playback:** hand off the resulting playlist to the user's existing music client or
  playback integration.

## Login and Library Authorization

The Navidrome username and password must not be a single global `.env` identity.
Keep `NAVIDROME_BASE_URL` in service configuration, but remove the configured global
Navidrome username/password. Each person signs in through Vue with their own Navidrome
account. FastAPI validates the credentials with Navidrome, creates a user-scoped
Resonance JWT for subsequent API calls, and resolves each request to the authenticated
Navidrome identity. All user-facing FastAPI endpoints require that authorization.
Never put passwords in a JWT, return Navidrome credentials or reusable upstream tokens
to the page, store them in browser storage, or include them in logs.

The login/session implementation must retain the user's Navidrome authorization for
upstream calls without falling back to the administrator's credentials. Prefer a
server-side session record for any upstream token or credential material; the
Resonance JWT should be short-lived and revocable. Admin-only endpoints additionally
check the authenticated Navidrome user's admin role. MCP calls must resolve the same
user identity and permissions as Vue rather than using a global service token.

**First PRD-12 milestone:** establish and verify this login-to-authorized-request
path before building the rest of the Vue or MCP experience. The spike must prove a
regular user can authenticate, receives only their permitted libraries, cannot search
an admin-only library by guessing a collection ID, and creates a private playlist
owned by their own Navidrome account.

Navidrome remains the authority for library and playlist permissions:

- Fetch the signed-in user's accessible libraries from Navidrome for each request or
  through a short-lived permission cache. Recheck permissions at playlist creation. Do
  not trust a library ID or collection name supplied by the browser without checking
  it against this user's permissions.
- An administrator can ingest libraries they can access and configure one or more
  collections for each library. A collection is an index variant, for example one
  model/provider profile; collection metadata binds it to the Navidrome server and
  library, not to the admin username used to ingest it. Remove the current username
  from the source fingerprint: login identity is authorization context, while source
  identity is the stable Navidrome server.
- For a normal user, expose only configured collections whose library IDs are in
  their Navidrome-visible library set. Apply this restriction in FastAPI/application
  code and Qdrant queries, not only by hiding options in Vue. A user with access to
  libraries B and C must never receive results from admin-only library A.
- Revalidate selected song IDs using the signed-in user's Navidrome identity before
  saving. Create the private playlist under that same user and verify its owner and
  contents. A playlist created by the admin account may not be playable or editable by
  the user who requested it.

Navidrome 0.64+ has an optional experimental Jellyfin-compatible login endpoint that
returns a Navidrome JWT and enforces the logged-in user's library permissions. Its
token lifecycle and compatibility with the Subsonic calls Resonance currently uses
need verification before selecting it. The standard Subsonic API also authenticates
individual users and scopes `getMusicFolders` and other calls, but uses its client
authentication scheme rather than an OAuth-style login flow. Compare these choices
and decide how FastAPI maintains the upstream user context. Do not depend on Navidrome
being an OIDC identity provider. See the official [multi-library
documentation](https://www.navidrome.org/docs/usage/features/multi-library/) and
[Jellyfin API documentation](https://www.navidrome.org/docs/usage/features/jellyfin/).

Administrative ingestion/configuration must be distinguished from ordinary user
search and playlist operations. FastAPI defines the shared HTTP API contracts. The Vue
application and FastMCP adapter both consume those endpoints; FastAPI routes delegate
to the transport-independent application operations established in PRD-09. Neither
client should spawn CLI subprocesses or duplicate product logic.

## Initial Direction

- Build a Vue application for direct user search, result review, and private playlist
  creation. Design it around the same theme/mood-to-playlist job an assistant can do.
- Define FastAPI endpoints as the stable contract consumed by both the Vue app and
  FastMCP. Provide structured inputs/results and preserve supporting lyric evidence.
- Expose corresponding user-oriented MCP tools for search, candidate review, and
  private playlist creation. The LLM may interpret conversational context, then call
  these tools with explicit structured arguments.
- Keep library ingestion and embedding configuration as operator/admin tasks. The
  current static HTML page remains an operator PoC, not the intended end-user UI.
- Start with one self-hosted Navidrome account/library. Avoid designing multi-tenant
  roles and enterprise identity before the single-user interaction is proven.
- Prefer the simplest practical sign-in and account setup for a self-hosted install.
  Delegate credential verification to Navidrome and derive the session identity and
  library access from the authenticated Navidrome account. Do not require external
  OIDC by default.
- Remove `NAVIDROME_USER_ID` and `NAVIDROME_USER_PASSWORD` from `.env`; retain
  `NAVIDROME_BASE_URL` as the configured Navidrome connection value. Do not bind
  indexed collection identity to whichever admin account ingested it.
- Keep Vue and MCP deployment details open while the workflows are explored.

## Candidate Direct UI Flow

1. An administrator signs in with their Navidrome account, configures an embedding
   endpoint/profile, and indexes the libraries they can access. They may configure
   multiple collections for a library.
2. A user signs in with their own Navidrome account. Vue shows only configured
   collections for libraries Navidrome grants to that user.
3. The user enters a theme, mood, seed song, or combination, with optional constraints.
4. Vue calls the FastAPI search/generation endpoints and displays ranked tracks with
   concise supporting lyric evidence.
5. The user reviews the candidate list, removes or reorders tracks, and explicitly
   chooses to create a playlist. Searching alone never writes a playlist.
6. Vue calls the FastAPI playlist endpoint with the approved Navidrome song IDs and
   order. FastAPI rechecks access as the user, creates a private playlist owned by that
   user, and returns its identity and verified status.
7. The user opens the playlist in a compatible playback client.

## Candidate Assistant Flow

1. A user talks with their LLM about a mood, theme, or personal context.
2. The LLM calls the MCP search tool with relevant context and optional constraints.
   FastMCP uses the same FastAPI contract as Vue.
3. The LLM presents grounded candidates; the user can ask for refinement or selection.
4. After clear user intent, the LLM calls the playlist tool with the approved ordered
   song IDs. The tool returns the verified playlist identity for playback elsewhere.

These flows are hypotheses to refine through use. Exact layouts, endpoint schemas,
tool names, approval UX, and playlist handoff are not fixed requirements yet.

## Non-Goals for the First User-Facing Slice

- Exposing ingestion, collection deletion, or embedding settings to ordinary MCP users.
- Having Resonance receive or retain full LLM conversation histories.
- Automatically generating or saving a playlist without a user-directed request.
- Playing or streaming audio from Resonance.
- Multi-account tenancy, shared/public playlists, social features, or broad role systems.
- Requiring a specific MCP transport or an external identity provider before validating
  the basic search-to-playlist flow.

## Open Questions

- Which direct Vue journey should be implemented first, and what minimum setup/admin
  controls belong in that application?
- Which FastAPI endpoints should form the shared Vue/FastMCP contract, and where should
  search and playlist operations be separate versus composed?
- Should sign-in use Navidrome's experimental Jellyfin login/JWT or the stable
  Subsonic authentication scheme? Which minimum Navidrome version/configuration should
  be supported?
- How should the Resonance session hold or refresh user-scoped Navidrome credentials
  without exposing them to Vue storage or MCP tool arguments?
- How should FastMCP receive the authenticated Resonance user context while preserving
  the same library-scoped API behavior as Vue?
- Which Navidrome role field/API should authorize admin-only ingestion and collection
  configuration?
- Which result fields and lyric excerpt limits give both the Vue user and an LLM enough
  grounding while minimizing unnecessary lyric disclosure?
- Does playlist creation need a separate confirmation call, or is an explicit create
  request with a fully specified ordered song list sufficient user intent?
- Should the first direct UI support seed-song search, theme-only search, or both?
- Which MCP transport and client compatibility targets matter for the first release?

## Readiness

This PRD is intentionally exploratory and not approved for implementation. Resolve the
first Vue user flow, shared FastAPI contract, Navidrome login/session method, MCP user
context, and playlist ownership contract before writing an implementation plan.
Ingestion progress, stop, restart, and full per-library refresh are separate
administrative work and may receive their own PRD after prioritization.

## References

- [PRD-09 — Navidrome backend and operator PoC](09-navidrome-semantic-playlists.md)
- [Shared application boundary ADR](../adr/001-navidrome-application-boundary.md)
- [Navidrome externalized authentication](https://www.navidrome.org/docs/usage/externalized-authentication/)
- [Navidrome experimental Jellyfin-compatible API](https://www.navidrome.org/docs/usage/features/jellyfin/)
