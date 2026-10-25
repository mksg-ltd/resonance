---
phase: discovery
status: draft
created: 2026-10-25
updated: 2026-10-25
author: MK
tags: [assistant, mcp, ui, playlists, navidrome]
---

# Assistant Search and Playlist Experience

**Status**: Early draft — product direction recorded; interface, authentication, and
first-release scope remain open.

**Relationship to PRD-09**: PRD-09 is complete for the single-account Navidrome
backend and local operator search/ingestion PoC. This PRD captures the evolving
user-facing experience and MCP adapter. It does not reopen or extend PRD-09.

## Product Intent

Let someone ask an LLM for music related to what they are feeling or discussing. The
LLM may use relevant context from its conversation to call Resonance tools that search
the user's Navidrome library, inspect supporting lyric evidence, and create a private
playlist from the user's chosen tracks. A compatible music client or separate playback
integration can then play that playlist. Resonance does not stream or control playback.

The user supplies context to the LLM; Resonance receives only the structured search or
playlist request sent to its interface. Search results are suggestions based on lyric
similarity, not definitive interpretations of a song's meaning.

## Product Boundary

- **Administration:** configure the Navidrome connection and embedding service; choose
  a library; create and ingest a search collection; later monitor and refresh ingestion.
- **User discovery:** search by theme, mood, or other user-approved context; receive
  distinct tracks with relevant lyric evidence.
- **Playlist action:** create a private Navidrome playlist from an explicit ordered
  selection after clear user intent/approval.
- **Playback:** hand off the resulting playlist to the user's existing music client or
  playback integration.

Administrative ingestion/configuration must not be exposed as ordinary user tools.
The MCP server and any UI must call transport-independent application operations,
not spawn CLI subprocesses or route handlers.

## Initial Direction

- Build user-oriented MCP tools over the existing shared search and private playlist
  operations. Keep inputs and results structured so the calling LLM can pass a theme,
  present candidates, and act on the user's selection.
- Keep library ingestion and embedding configuration as operator/admin tasks. The
  current static HTML page remains an operator PoC, not the intended end-user UI.
- Start with one self-hosted Navidrome account/library. Avoid designing multi-tenant
  roles and enterprise identity before the single-user interaction is proven.
- Prefer the simplest practical sign-in and account setup for a self-hosted install.
  Do not assume Navidrome is an OIDC identity provider or require an external OIDC
  service by default. Decide whether the first experience uses the configured account,
  Navidrome's supported client authentication, or a small Resonance-owned login flow.
- Keep UI framework choice open. A small setup/review UI may complement MCP; Vue is
  not a requirement of this discovery draft.

## Candidate User Flow

1. An operator configures one Navidrome account, an embedding endpoint/profile, and
   indexes a selected library using the admin interface.
2. In a conversation, the user asks for music that relates to a theme or personal
   context.
3. The LLM calls Resonance search with the context and optional constraints. Resonance
   returns track identity, ranked relevance, and concise supporting lyric evidence.
4. The LLM presents a candidate list and asks for selection or confirmation when
   needed. Search alone never writes a playlist.
5. After user intent is clear, the LLM calls playlist creation with the chosen
   Navidrome song IDs and order. Resonance creates a private playlist and returns its
   identity and verified status.
6. The LLM or user opens that playlist in their compatible playback client/tool.

This is a hypothesis to refine through use; exact turns, approval UX, tool names, and
playlist handoff are not fixed requirements yet.

## Non-Goals for the First User-Facing Slice

- Exposing ingestion, collection deletion, or embedding settings to ordinary MCP users.
- Having Resonance receive or retain full LLM conversation histories.
- Automatically generating or saving a playlist without a user-directed request.
- Playing or streaming audio from Resonance.
- Multi-account tenancy, shared/public playlists, social features, or broad role systems.
- Requiring Vue, a specific MCP transport, or an external identity provider before
  validating the basic search-to-playlist flow.

## Open Questions

- Which surface should come first: MCP tools, a small direct UI, or both in a thin
  vertical slice? The assistant-led use case suggests MCP-first, with UI for setup and
  candidate review where it adds value.
- What is the simplest safe login for a self-hosted single-account installation? Can
  the first version use server-configured Navidrome credentials without making browser
  credentials or an operator bearer token available to the LLM?
- Should MCP connect directly to one configured Navidrome account, or should users
  authenticate their own Navidrome account? What deployment topologies must work?
- Which result fields and lyric excerpt limits give an LLM enough grounding while
  minimizing unnecessary lyric disclosure?
- Does the first playlist tool require a separate confirmation call, or is an explicit
  create call with a fully specified ordered song list sufficient user intent?
- What should the UI do beyond setup, library/ingestion status, and optional candidate
  review?
- Which MCP transport and client compatibility targets matter for the first release?

## Readiness

This PRD is intentionally exploratory and not approved for implementation. Resolve the
first-release user flow, authentication boundary, MCP deployment model, and playlist
approval contract before writing an implementation plan. Ingestion progress, stop,
restart, and full per-library refresh are separate administrative work and may receive
their own PRD after prioritization.

## References

- [PRD-09 — Navidrome backend and operator PoC](09-navidrome-semantic-playlists.md)
- [Shared application boundary ADR](../adr/001-navidrome-application-boundary.md)
- [Navidrome externalized authentication](https://www.navidrome.org/docs/usage/externalized-authentication/)
- [Navidrome experimental Jellyfin-compatible API](https://www.navidrome.org/docs/usage/features/jellyfin/)
