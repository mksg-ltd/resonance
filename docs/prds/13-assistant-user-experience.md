---
author: MK
created: 2026-10-25
phase: discovery
status: in-progress
tags:
  - assistant
  - mcp
  - vue
  - api
  - playlists
  - navidrome
  - vue-first-slice-complete
  - mcp-tools-next
title: "User Search and Playlist Experience: Vue UI and MCP"
updated: 2026-10-27
---

# User Search and Playlist Experience: Vue UI and MCP

**Status**: Phase 1, direct Vue search/review/private-playlist workflow, is implemented.
Phase 2 is the design and implementation of user-facing MCP tools; it has not started.
The authenticated, tool-free FastMCP foundation is tracked separately in PRD-14.
Authentication is implemented in [PRD-12](12-auth-foundation.md).

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

## Authentication Dependency

PRD-12 defines the login and authorization foundation: Navidrome username/password
login, Resonance JWTs for API authorization, the configured admin username, and
Navidrome-enforced library permissions. PRD-13 depends on that work and must not
reimplement authentication or use a global operator token for user search or playlist
creation. Vue receives the JWT as an HttpOnly cookie; FastMCP sends it as a bearer
token. Both resolve to the same authenticated user context in FastAPI.

Admin ingestion/configuration and ordinary user search/playlist operations remain
separate capabilities. FastAPI defines the shared HTTP API contracts. The Vue
application and FastMCP adapter both consume those endpoints; FastAPI routes delegate
to the transport-independent application operations established in PRD-09. Neither
client should spawn CLI subprocesses or duplicate product logic.

## Initial Direction

- First ship the direct Vue journey: search by a theme or mood, review lyric-grounded
  results, select and order tracks, and explicitly save a private playlist.
- Reuse the authenticated FastAPI APIs as the product contract. Search and playlist
  operations already exist; extend them only if the browser workflow exposes a
  concrete contract gap.
- Add a minimal FastMCP scaffold as an intermediate step after browser search and
  playlist quality are validated. Use the existing Nool and Obsidian MCP projects as
  implementation references, but adapt their authentication to Resonance's
  Navidrome-verified user identity.
- Add corresponding user-oriented FastMCP tools over the same API contracts after
  defining how MCP clients obtain, store, and renew each user's bearer identity. Do
  not pass Navidrome passwords through model-visible tool arguments.
- Keep library ingestion and embedding configuration as operator/admin tasks. The
  current static HTML page remains an operator PoC, not the intended end-user UI.
- Support multiple users on one self-hosted Navidrome server, each with the libraries
  Navidrome grants to their account. Do not add a separate Resonance user/role database.
- Use PRD-12's configured admin username for admin operations; do not add a hidden
  service account. Do not bind indexed collection identity to the admin username.
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

The first direct Vue workflow is fixed for this increment. Exact layout remains open
to implementation judgment. The assistant flow, MCP tool names, and MCP login/token
lifecycle remain follow-on design work. A thin FastMCP application scaffold is the
planned bridge after this workflow is tested and before the MCP tools are implemented.

## Non-Goals for the First User-Facing Slice

- Exposing ingestion, collection deletion, or embedding settings to ordinary MCP users.
- Having Resonance receive or retain full LLM conversation histories.
- Automatically generating or saving a playlist without a user-directed request.
- Playing or streaming audio from Resonance.
- Multi-account tenancy, shared/public playlists, social features, or broad role systems.
- Requiring a specific MCP transport or an external identity provider before validating
  the basic search-to-playlist flow.
- Implementing the FastMCP server or MCP authentication/token lifecycle in the first
  direct Vue increment.

## Open Questions

- What minimum setup/admin controls belong in a later Vue increment?
- Which FastAPI endpoints should form the shared Vue/FastMCP contract, and where should
  search and playlist operations be separate versus composed?
- How should FastMCP obtain and renew the authenticated Resonance user context without
  exposing Navidrome credentials to the model or relying on a permanent token?
- Which result fields and lyric excerpt limits give both the Vue user and an LLM enough
  grounding while minimizing unnecessary lyric disclosure?
- Does playlist creation need a separate confirmation call, or is an explicit create
  request with a fully specified ordered song list sufficient user intent?
- Should the first direct UI support seed-song search, theme-only search, or both?
- Which MCP transport and client compatibility targets matter for the first release?

## Readiness

The first direct Vue slice is ready for implementation: the API contract,
authentication prerequisite, playlist ownership policy, and user flow are established.
After match quality is evaluated, add a minimal FastMCP scaffold using Nool and
Obsidian MCP as references, then resolve user token lifecycle before building tools.
The requested `~/dev/mksg/obsidian-mcp` path is not present in this checkout; the
related repository was found at `~/dev/mk/obsidian-mcp`. Ingestion progress, stop,
restart, and full per-library refresh are separate administrative work and may receive
their own PRD after prioritization.

## References

- [PRD-09 — Navidrome backend and operator PoC](09-navidrome-semantic-playlists.md)
- [Shared application boundary ADR](../adr/001-navidrome-application-boundary.md)
- [PRD-12 — User Authentication and Authorization Foundation](12-auth-foundation.md)
